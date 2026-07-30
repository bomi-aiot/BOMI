"""일반 Gemini timeout, retry, 응답 구조 테스트."""

import pytest

from bomi_ai_chat.http import ExternalServiceError, InvalidResponseError
from bomi_ai_chat.llm.client import LLMClient
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
