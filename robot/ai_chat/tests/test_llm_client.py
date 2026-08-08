"""일반 Gemini timeout, retry, 응답 구조 테스트."""

import pytest

from bomi_ai_chat.http import ExternalServiceError, InvalidResponseError
from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.turn_timer import TurnTimer
from tests.http_fakes import StubResponse, StubSession


def llm_settings(settings_factory):
    return settings_factory(
        GEMINI_API_KEY="gemini-key",
        HTTP_TIMEOUT_SECONDS="4",
        HTTP_MAX_ATTEMPTS="2",
        HTTP_BACKOFF_SECONDS="0.25",
        HTTP_MAX_BACKOFF_SECONDS="0.25",
    )


def gemini_response(text="안녕하세요"):
    return StubResponse(
        json_data={
            "candidates": [
                {"content": {"parts": [{"text": text}]}},
            ]
        }
    )


@pytest.mark.parametrize("retry_status", [429, 503])
def test_retryable_gemini_status_recovers(
    settings_factory,
    retry_status,
):
    session = StubSession(StubResponse(retry_status), gemini_response())
    delays = []
    client = LLMClient(
        llm_settings(settings_factory),
        session=session,
        sleep=delays.append,
    )

    assert client.generate("안녕") == "안녕하세요"
    assert len(session.calls) == 2
    assert delays == [0.25]
    assert session.calls[0]["timeout"] == 4.0


def test_gemini_401_fails_without_retry(settings_factory):
    session = StubSession(StubResponse(401), gemini_response())
    client = LLMClient(llm_settings(settings_factory), session=session)

    with pytest.raises(ExternalServiceError) as error:
        client.generate("안녕")

    assert error.value.status_code == 401
    assert len(session.calls) == 1


def test_gemini_empty_candidates_is_invalid(settings_factory):
    session = StubSession(StubResponse(json_data={"candidates": []}))
    client = LLMClient(llm_settings(settings_factory), session=session)

    with pytest.raises(InvalidResponseError, match="candidates"):
        client.generate("안녕")


def test_gemini_invalid_json_is_normalized(settings_factory):
    session = StubSession(
        StubResponse(json_error=ValueError("invalid json")),
    )
    client = LLMClient(llm_settings(settings_factory), session=session)

    with pytest.raises(InvalidResponseError):
        client.generate("안녕")


def test_gemini_call_is_recorded_in_the_active_turn(settings_factory):
    client = LLMClient(
        llm_settings(settings_factory),
        session=StubSession(gemini_response()),
    )
    timer = TurnTimer()

    with timer.activate():
        client.generate("안녕")

    assert timer.stages["llm"] >= 0


def test_current_time_is_marked_as_internal_context(settings_factory):
    session = StubSession(gemini_response())
    client = LLMClient(llm_settings(settings_factory), session=session)

    client.generate("오늘 산책하고 왔어")

    system_prompt = session.calls[0]["json"]["system_instruction"]["parts"][0]["text"]
    assert "사용자가 날짜, 요일 또는 현재 시각을 직접 질문한 경우에만" in system_prompt
    assert "일상 대화, 안부 대화, 건강 대화에서는 날짜와 시각을 먼저 말하지 않습니다" in system_prompt
