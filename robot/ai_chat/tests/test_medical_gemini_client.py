"""의료 Gemini가 공통 HTTP 정책과 사용자 안전 문구를 사용하는지 검증한다."""

import logging

import pytest

from bomi_ai_chat.http import ExternalServiceError
from bomi_ai_chat.llm import medical_flow
from tests.http_fakes import StubResponse, StubSession


def medical_settings(settings_factory):
    return settings_factory(
        GEMINI_API_KEY="gemini-key",
        HTTP_TIMEOUT_SECONDS="8",
        HTTP_MAX_ATTEMPTS="2",
        HTTP_BACKOFF_SECONDS="0.3",
        HTTP_MAX_BACKOFF_SECONDS="0.3",
    )


def test_medical_gemini_retries_429(settings_factory):
    session = StubSession(
        StubResponse(429),
        StubResponse(json_data={"candidates": []}),
    )
    delays = []

    result = medical_flow._call_gemini(
        [{"role": "user", "parts": [{"text": "질문"}]}],
        settings=medical_settings(settings_factory),
        session=session,
        sleep=delays.append,
    )

    assert result == {"candidates": []}
    assert delays == [0.3]
    assert session.calls[0]["timeout"] == 8.0


def test_medical_gemini_401_fails_without_retry(settings_factory):
    session = StubSession(StubResponse(401), StubResponse(200))

    with pytest.raises(ExternalServiceError) as error:
        medical_flow._call_gemini(
            [],
            settings=medical_settings(settings_factory),
            session=session,
        )

    assert error.value.status_code == 401
    assert len(session.calls) == 1


def test_medical_flow_logs_detail_but_returns_generic_message(
    monkeypatch,
    caplog,
):
    def fail_call(contents):
        raise ExternalServiceError(
            "Gemini 의료",
            "HTTP 401",
            category="http",
            status_code=401,
        )

    monkeypatch.setattr(medical_flow, "_call_gemini", fail_call)

    with caplog.at_level(logging.ERROR):
        response = medical_flow.handle_medical_query("병원 알려줘")

    assert response == medical_flow.SERVICE_UNAVAILABLE_MESSAGE
    assert "401" not in response
    assert "의료 Gemini 첫 번째 호출 실패" in caplog.text
