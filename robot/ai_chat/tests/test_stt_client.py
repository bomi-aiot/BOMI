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
