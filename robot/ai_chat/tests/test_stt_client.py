"""RTZR STT 토큰 캐시, 업로드, 제한 폴링 테스트."""

import pytest

from bomi_ai_chat.http import ExternalServiceError, InvalidResponseError
from bomi_ai_chat.stt.client import STTClient
from tests.http_fakes import StubResponse, StubSession


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def stt_settings(settings_factory, **overrides):
    values = {
        "RTZR_CLIENT_ID": "client-id",
        "RTZR_CLIENT_SECRET": "client-secret",
        "HTTP_TIMEOUT_SECONDS": "2",
        "HTTP_MAX_ATTEMPTS": "2",
        "HTTP_BACKOFF_SECONDS": "0.1",
        "HTTP_MAX_BACKOFF_SECONDS": "0.2",
        "STT_POLL_INTERVAL_SECONDS": "0.5",
        "STT_POLL_TIMEOUT_SECONDS": "2",
        "STT_TOKEN_TTL_SECONDS": "60",
    }
    values.update(overrides)
    return settings_factory(**values)


def test_transcribe_caches_token_and_returns_joined_utterances(
    settings_factory,
):
    session = StubSession(
        StubResponse(json_data={"access_token": "token"}),
        StubResponse(json_data={"id": "job-1"}),
        StubResponse(json_data={"status": "processing"}),
        StubResponse(
            json_data={
                "status": "completed",
                "results": {
                    "utterances": [{"msg": "안녕"}, {"msg": "보미야"}],
                },
            }
        ),
        StubResponse(json_data={"id": "job-2"}),
        StubResponse(
            json_data={
                "status": "completed",
                "results": {"utterances": [{"msg": "다시 안녕"}]},
            }
        ),
    )
    clock = FakeClock()
    client = STTClient(
        stt_settings(settings_factory),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert client.transcribe(b"wav") == "안녕 보미야"
    assert client.transcribe(b"wav") == "다시 안녕"

    auth_calls = [
        call for call in session.calls if call["url"].endswith("/authenticate")
    ]
    assert len(auth_calls) == 1
    assert clock.sleeps == [0.5]


def test_empty_audio_fails_before_external_request(settings_factory):
    session = StubSession()
    client = STTClient(stt_settings(settings_factory), session=session)

    with pytest.raises(ValueError, match="비어 있지 않은 bytes"):
        client.transcribe(b"")

    assert session.calls == []


def test_expired_token_is_refreshed(settings_factory):
    session = StubSession(
        StubResponse(json_data={"access_token": "token-1"}),
        StubResponse(json_data={"id": "job-1"}),
        StubResponse(
            json_data={
                "status": "completed",
                "results": {"utterances": []},
            }
        ),
        StubResponse(json_data={"access_token": "token-2"}),
        StubResponse(json_data={"id": "job-2"}),
        StubResponse(
            json_data={
                "status": "completed",
                "results": {"utterances": []},
            }
        ),
    )
    clock = FakeClock()
    client = STTClient(
        stt_settings(
            settings_factory,
            STT_TOKEN_TTL_SECONDS="1",
        ),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert client.transcribe(b"wav") == ""
    clock.now = 1.0
    assert client.transcribe(b"wav") == ""

    auth_calls = [
        call for call in session.calls if call["url"].endswith("/authenticate")
    ]
    assert len(auth_calls) == 2


def test_polling_deadline_stops_pending_job(settings_factory):
    session = StubSession(
        StubResponse(json_data={"access_token": "token"}),
        StubResponse(json_data={"id": "job-1"}),
        StubResponse(json_data={"status": "processing"}),
        StubResponse(json_data={"status": "processing"}),
    )
    clock = FakeClock()
    client = STTClient(
        stt_settings(
            settings_factory,
            STT_POLL_TIMEOUT_SECONDS="1",
        ),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    with pytest.raises(ExternalServiceError) as error:
        client.transcribe(b"wav")

    assert error.value.category == "polling_timeout"
    assert clock.now == 1.0


def test_completed_response_requires_utterance_list(settings_factory):
    session = StubSession(
        StubResponse(json_data={"access_token": "token"}),
        StubResponse(json_data={"id": "job-1"}),
        StubResponse(json_data={"status": "completed", "results": {}}),
    )
    clock = FakeClock()
    client = STTClient(
        stt_settings(settings_factory),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    with pytest.raises(InvalidResponseError, match="utterances"):
        client.transcribe(b"wav")


# ── 인식 설정 (S15P11E102 / 2026-08-10) ──────────────────────────────────────
#
# 왜 이 절이 생겼는가
#   config 가 '{"model_name": "sommers", "language": "ko"}' 문자열로 박혀 있었다.
#   같은 오디오로 A/B 한 결과 키워드 부스팅 하나로 "고미야 관절 영양"이
#   "보미야 관절염 약"이 됐다 — 웨이크워드 이름이 틀리면 그 뒤 대화가 다 어긋난다.


def _sent_config(session):
    """업로드 요청에 실린 config 를 dict 로 꺼낸다."""
    import json

    upload = session.calls[1]
    return json.loads(upload["data"]["config"])


def _run_transcribe(settings_factory, **overrides):
    session = StubSession(
        StubResponse(json_data={"access_token": "token"}),
        StubResponse(json_data={"id": "job-1"}),
        StubResponse(json_data={
            "status": "completed",
            "results": {"utterances": [{"msg": "안녕하세요"}]},
        }),
    )
    clock = FakeClock()
    client = STTClient(
        stt_settings(settings_factory, **overrides),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    client.transcribe(b"audio")
    return _sent_config(session)


def test_model_and_language_are_unchanged(settings_factory):
    """기존 계약은 그대로다 — 이 두 값이 바뀌면 인식 품질이 통째로 달라진다."""
    config = _run_transcribe(settings_factory)
    assert config["model_name"] == "sommers"
    assert config["language"] == "ko"


def test_keywords_are_sent_for_boosting(settings_factory):
    config = _run_transcribe(settings_factory, STT_KEYWORDS="보미,관절염약")
    assert config["keywords"] == ["보미", "관절염약"]


def test_empty_keywords_omit_the_field_entirely(settings_factory):
    """빈 배열을 보내는 것이 무해하다는 근거가 없다. 안 보내면 예전과 같다."""
    config = _run_transcribe(settings_factory, STT_KEYWORDS="")
    assert "keywords" not in config


def test_disfluency_filter_is_off_unless_asked(settings_factory):
    """실측에서 이득을 확인하지 못했다. 기본값이 조용히 켜지면 안 된다."""
    config = _run_transcribe(settings_factory)
    assert "use_disfluency_filter" not in config


def test_disfluency_filter_can_be_turned_on(settings_factory):
    config = _run_transcribe(settings_factory, STT_DISFLUENCY_FILTER="true")
    assert config["use_disfluency_filter"] is True
