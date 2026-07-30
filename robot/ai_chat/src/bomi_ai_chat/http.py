"""외부 HTTP 서비스의 공통 timeout, retry, 오류 변환 정책."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503})
RETRYABLE_EXCEPTIONS = (requests.Timeout, requests.ConnectionError)


class ExternalServiceError(RuntimeError):
    """외부 서비스 실패의 개발자 정보와 사용자 안내를 분리한다."""

    def __init__(
        self,
        service: str,
        detail: str,
        *,
        category: str,
        status_code: int | None = None,
        user_message: str | None = None,
    ) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.category = category
        self.status_code = status_code
        self.user_message = user_message or (
            f"{service} 연결이 원활하지 않습니다. 잠시 후 다시 시도해주세요."
        )


class InvalidResponseError(ExternalServiceError):
    """성공 HTTP 응답의 본문 구조가 계약과 다를 때 발생한다."""

    def __init__(self, service: str, detail: str) -> None:
        super().__init__(
            service,
            detail,
            category="invalid_response",
            user_message=(
                f"{service} 응답을 확인하지 못했습니다. 잠시 후 다시 시도해주세요."
            ),
        )


def _retry_delay(
    *,
    attempt: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    return min(backoff_seconds * (2 ** (attempt - 1)), max_backoff_seconds)


def request_with_retry(
    method: str,
    url: str,
    *,
    service: str,
    timeout_seconds: float,
    max_attempts: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
    session: Any = requests,
    sleep: Callable[[float], None] = time.sleep,
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    **kwargs: Any,
) -> requests.Response:
    """허용된 일시 장애만 제한적으로 재시도하고 나머지는 즉시 실패한다."""

    for attempt in range(1, max_attempts + 1):
        request_timeout = timeout_seconds
        if deadline is not None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ExternalServiceError(
                    service,
                    "request deadline exceeded",
                    category="deadline",
                )
            request_timeout = min(request_timeout, remaining)

        try:
            response = session.request(
                method,
                url,
                timeout=request_timeout,
                **kwargs,
            )
        except RETRYABLE_EXCEPTIONS as exc:
            if deadline is not None and monotonic() >= deadline:
                raise ExternalServiceError(
                    service,
                    "request deadline exceeded",
                    category="deadline",
                ) from exc
            if attempt >= max_attempts:
                raise ExternalServiceError(
                    service,
                    f"{type(exc).__name__} after {attempt} attempts",
                    category="timeout"
                    if isinstance(exc, requests.Timeout)
                    else "connection",
                ) from exc
            delay = _retry_delay(
                attempt=attempt,
                backoff_seconds=backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
            )
            if deadline is not None:
                delay = min(delay, max(0.0, deadline - monotonic()))
            LOGGER.warning(
                "%s transient %s; retrying attempt %s/%s in %.2fs",
                service,
                type(exc).__name__,
                attempt + 1,
                max_attempts,
                delay,
            )
            sleep(delay)
            continue
        except requests.RequestException as exc:
            raise ExternalServiceError(
                service,
                type(exc).__name__,
                category="request",
            ) from exc

        status_code = response.status_code
        if deadline is not None and monotonic() > deadline:
            raise ExternalServiceError(
                service,
                "request deadline exceeded",
                category="deadline",
            )
        if 200 <= status_code < 300:
            return response

        if (
            status_code in RETRYABLE_STATUS_CODES
            and attempt < max_attempts
        ):
            delay = _retry_delay(
                attempt=attempt,
                backoff_seconds=backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
            )
            if deadline is not None:
                delay = min(delay, max(0.0, deadline - monotonic()))
            LOGGER.warning(
                "%s returned HTTP %s; retrying attempt %s/%s in %.2fs",
                service,
                status_code,
                attempt + 1,
                max_attempts,
                delay,
            )
            sleep(delay)
            continue

        raise ExternalServiceError(
            service,
            f"HTTP {status_code}",
            category="http",
            status_code=status_code,
        )

    raise AssertionError("unreachable")


def decode_json_object(
    response: requests.Response,
    *,
    service: str,
) -> dict[str, Any]:
    """JSON object 응답만 허용하고 파싱 상세 오류는 외부로 노출하지 않는다."""

    try:
        data = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise InvalidResponseError(service, "response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise InvalidResponseError(service, "JSON root must be an object")
    return data
