"""외부 HTTP 공통 timeout, retry, 오류 분류 테스트."""

import pytest
import requests

from bomi_ai_chat.http import (
    ExternalServiceError,
    InvalidResponseError,
    decode_json_object,
    is_permanent_rejection,
    request_with_retry,
)
from tests.http_fakes import StubResponse, StubSession


def request(session, sleep):
    return request_with_retry(
        "GET",
        "https://service.example/resource",
        service="테스트 서비스",
        timeout_seconds=7.0,
        max_attempts=3,
        backoff_seconds=0.5,
        max_backoff_seconds=1.0,
        session=session,
        sleep=sleep,
    )


def test_retryable_statuses_use_bounded_exponential_backoff():
    session = StubSession(
        StubResponse(429),
        StubResponse(503),
        StubResponse(200),
    )
    delays = []

    response = request(session, delays.append)

    assert response.status_code == 200
    assert delays == [0.5, 1.0]
    assert [call["timeout"] for call in session.calls] == [7.0, 7.0, 7.0]


@pytest.mark.parametrize("status_code", [400, 401, 403, 500])
def test_permanent_http_errors_fail_without_retry(status_code):
    session = StubSession(StubResponse(status_code), StubResponse(200))
    delays = []

    with pytest.raises(ExternalServiceError) as error:
        request(session, delays.append)

    assert error.value.category == "http"
    assert error.value.status_code == status_code
    assert len(session.calls) == 1
    assert delays == []


def test_timeout_is_retried_and_classified_after_limit():
    session = StubSession(
        requests.Timeout(),
        requests.Timeout(),
        requests.Timeout(),
    )
    delays = []

    with pytest.raises(ExternalServiceError) as error:
        request(session, delays.append)

    assert error.value.category == "timeout"
    assert len(session.calls) == 3
    assert delays == [0.5, 1.0]


def test_deadline_bounds_status_retry_backoff():
    session = StubSession(
        StubResponse(503),
        StubResponse(503),
        StubResponse(200),
    )
    now = 0.0
    delays = []

    def monotonic():
        return now

    def sleep(seconds):
        nonlocal now
        delays.append(seconds)
        now += seconds

    with pytest.raises(ExternalServiceError) as error:
        request_with_retry(
            "GET",
            "https://service.example/resource",
            service="테스트 서비스",
            timeout_seconds=5.0,
            max_attempts=3,
            backoff_seconds=0.5,
            max_backoff_seconds=1.0,
            session=session,
            sleep=sleep,
            deadline=0.75,
            monotonic=monotonic,
        )

    assert error.value.category == "deadline"
    assert delays == [0.5, 0.25]
    assert [call["timeout"] for call in session.calls] == [0.75, 0.25]
    assert len(session.calls) == 2


def test_invalid_json_is_normalized_without_body_details():
    response = StubResponse(json_error=ValueError("secret response body"))

    with pytest.raises(InvalidResponseError) as error:
        decode_json_object(response, service="테스트 서비스")

    assert error.value.category == "invalid_response"
    assert "secret response body" not in str(error.value)


# ── 영구 거부는 재시도하지 않는다 (2026-08-10) ───────────────────────────────
#
# 왜 이 절이 생겼는가
#   뷰어의 삭제 버튼이 서버의 conversation 을 지우자, 그 대화를 참조하는 큐 행이
#   매번 400 "unknown conversationId" 를 받게 됐다. 재시도의 전제("다음엔 될 수도
#   있다")가 깨진 경우인데 코드는 계속 재시도했고, 큐가 막힌 채 LLM 호출과
#   네트워크만 계속 썼다.


def _permanent_error(status: int) -> ExternalServiceError:
    return ExternalServiceError(
        "robot-fact-candidates", f"HTTP {status}",
        category="http", status_code=status,
    )


def test_client_error_is_permanent():
    """4xx 는 우리가 보낸 것이 틀렸다는 뜻이라 다시 보내도 같다."""
    assert is_permanent_rejection(_permanent_error(400)) is True
    assert is_permanent_rejection(_permanent_error(404)) is True
    assert is_permanent_rejection(_permanent_error(422)) is True


def test_server_error_stays_retryable():
    """5xx 는 서버 사정이라 기다리면 될 수 있다."""
    assert is_permanent_rejection(_permanent_error(500)) is False
    assert is_permanent_rejection(_permanent_error(503)) is False


def test_timeout_and_rate_limit_stay_retryable():
    """408·429 는 4xx 지만 '지금은 안 되니 나중에'라는 뜻이다."""
    assert is_permanent_rejection(_permanent_error(408)) is False
    assert is_permanent_rejection(_permanent_error(429)) is False


def test_auth_failure_is_not_permanent():
    """인증 설정은 사람이 복구할 수 있으므로 대기 중인 기억을 폐기하지 않는다."""
    assert is_permanent_rejection(_permanent_error(401)) is False
    assert is_permanent_rejection(_permanent_error(403)) is False


def test_network_failure_is_not_permanent():
    """상태 코드가 없는 실패(연결 끊김)는 영구 거부로 볼 근거가 없다."""
    assert is_permanent_rejection(OSError("connection reset")) is False
    assert is_permanent_rejection(
        ExternalServiceError("s", "d", category="network")) is False
