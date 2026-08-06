"""외부 HTTP 공통 timeout, retry, 오류 분류 테스트."""

import pytest
import requests

from bomi_ai_chat.http import (
    ExternalServiceError,
    InvalidResponseError,
    decode_json_object,
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
