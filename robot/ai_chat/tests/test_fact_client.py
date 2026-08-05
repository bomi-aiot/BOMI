"""사실 후보 제출 클라이언트(backend_client/fact_client.py) 검증 (S15P11E102-255).

이 파일이 검증하는 것
    1. 성공하면 예외 없이 끝나고, 페이로드가 서버 계약(FactCandidateIntakeRequest)
       대로 실린다 — 사실 하나당 요청 하나.
    2. 실패하면(네트워크, HTTP 오류 둘 다) FactSubmissionError 를 올린다 —
       conversation_client 와 반대 방향(예외를 삼키지 않는다).
    3. 빈 facts 는 아예 호출하지 않는다.
    4. 401 은 다른 실패와 구분되는 AUTH FAILURE 경고를 남긴다.
    5. 건강 관련 발화는 CARE_RECORD 로 간다 — MEMORY 로 새면 서버가 확인 없이
       저장해버린다(S15P11E102-255 계약 정합).

참고
    CLAUDE.md §8, §12 / backend_client/fact_client.py 모듈 docstring
"""

from __future__ import annotations

import pytest

from bomi_ai_chat.backend_client.fact_client import (
    BackendFactClient,
    FactSubmissionError,
)
from tests.http_fakes import StubResponse, StubSession

SENIOR = "senior-1"


def test_successful_submission_sends_the_expected_payload(settings_factory):
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
    )

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://backend.example/api/v1/robot/fact-candidates"
    # 서버의 FactCandidateIntakeRequest 는 필수 필드가 여덟 개다. 하나라도 빠지면
    # bean validation 이 400 으로 거절하고, 그 400 은 재시도해도 낫지 않는다.
    assert call["json"] == {
        "seniorId": SENIOR,
        "conversationId": "conv-1",
        "sourceMessageId": "msg-1",
        "targetDomain": "MEMORY",
        "factType": "PERSONAL_RELATIONSHIP",
        "operation": "CREATE",
        "proposedValue": {"content": "손자가 자주 놀러 온다."},
        "riskLevel": "NORMAL",
    }


def test_each_fact_becomes_its_own_request(settings_factory):
    """서버는 요청 하나당 후보 하나를 만든다 — 묶음으로 보내면 나머지를 잃는다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}), StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[
            {"factType": "FAMILY", "content": "손자가 자주 놀러 온다."},
            {"factType": "HOBBY", "content": "화분 가꾸기를 좋아한다."},
        ],
    )

    assert len(session.calls) == 2
    assert session.calls[0]["json"]["factType"] == "PERSONAL_RELATIONSHIP"
    assert session.calls[1]["json"]["factType"] == "HOBBY"


def test_health_facts_go_to_care_record_not_memory(settings_factory):
    """건강 발화가 MEMORY 로 새면 서버가 안전한 사실로 보고 확인 없이 저장한다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "HEALTH", "content": "이제 아침 약을 안 먹는다."}],
    )

    payload = session.calls[0]["json"]
    assert payload["targetDomain"] == "CARE_RECORD"
    assert payload["factType"] == "HEALTH_CONDITION"
    assert payload["riskLevel"] == "SENSITIVE"


def test_unknown_fact_type_falls_back_to_an_other_memory(settings_factory):
    """모델이 목록 밖 값을 뱉어도 내용을 잃지 않는다 — 분류만 OTHER 로 떨어진다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "WEATHER_CHAT", "content": "비 오는 날을 싫어한다."}],
    )

    payload = session.calls[0]["json"]
    assert payload["targetDomain"] == "MEMORY"
    assert payload["factType"] == "OTHER"
    assert payload["proposedValue"] == {"content": "비 오는 날을 싫어한다."}


def test_empty_facts_does_not_call_the_backend(settings_factory):
    settings = settings_factory()
    session = StubSession()
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR, conversation_id="conv-1", source_message_id="msg-1", facts=[])

    assert session.calls == []


def test_network_failure_raises_fact_submission_error(settings_factory):
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(ConnectionError("no route to host"))
    client = BackendFactClient(settings=settings, session=session)

    with pytest.raises(FactSubmissionError):
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )


def test_http_error_raises_fact_submission_error(settings_factory):
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(500, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    with pytest.raises(FactSubmissionError):
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )


def test_auth_failure_logs_a_distinct_warning_then_raises(settings_factory, caplog):
    """(완료 조건과 같은 원칙, S15P11E102-307) 401 은 구분되는 경고를 남긴다."""
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(401, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    raised = False
    with caplog.at_level("WARNING"):
        try:
            client.submit_fact_candidates(
                SENIOR,
                conversation_id="conv-1",
                source_message_id="msg-1",
                facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
            )
        except FactSubmissionError:
            raised = True

    assert raised is True
    assert "AUTH FAILURE" in caplog.text
