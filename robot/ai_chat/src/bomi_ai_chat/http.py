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

# 백엔드 공유 시크릿 필터(S15P11E102-307)가 헤더 누락/불일치에 응답하는 상태코드.
# 401 이 재시도 대상(RETRYABLE_STATUS_CODES)에 없는 이유: 같은 요청을 몇 번을
# 더 보내도 시크릿이 저절로 맞아지지 않는다. 재시도는 낭비고, 필요한 건 경고다.
AUTH_FAILURE_STATUS_CODES = frozenset({401, 403})


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


def is_auth_failure(error: BaseException) -> bool:
    """예외가 공유 시크릿 인증 실패(401/403)로 인한 것인지 판별한다.

    왜 필요한가
        네 백엔드 클라이언트는 실패를 서로 다르게 처리한다 — 캐시로 내려가거나,
        예외를 올리거나, 그냥 그 턴을 포기한다. 그런데 원인이 "네트워크가
        끊겼다"인지 "시크릿이 틀렸다/없다"인지는 처리 방식과 무관하게 항상
        구분해서 로그에 남아야 한다. 안 그러면 배포 때 시크릿을 안 맞춰 넣은
        설정 오류가, 흔한 오프라인 폴백처럼 조용히 지나간다(S15P11E102-307).

    누가 호출하는가
        backend_client/ 의 네 클라이언트. ExternalServiceError 를 잡은 자리에서
        이 함수로 한 번 더 나눠, 인증 실패만 별도의 경고 문구를 남긴다.
    """
    return (
        isinstance(error, ExternalServiceError)
        and error.status_code in AUTH_FAILURE_STATUS_CODES
    )


# 다시 보내도 결과가 같은 상태 코드. 4xx 는 "우리가 보낸 것이 틀렸다"는 뜻이라
# 같은 요청을 몇 번 더 보내도 같은 답이 온다.
#
# 408(Timeout)과 429(Too Many Requests)는 뺀다 — 둘은 4xx 지만 "지금은 안 되니
# 나중에 다시"라는 뜻이라 재시도가 맞다.
_RETRYABLE_CLIENT_ERROR_STATUS_CODES = frozenset({408, 429})


def is_permanent_rejection(error: BaseException) -> bool:
    """다시 보내도 소용없는 거부인가.

    왜 필요한가 (2026-08-10)
        추출 큐는 제출 실패를 전부 "일시적"으로 보고 그 행을 남겨 다음 틱에 다시
        보냈다. 그런데 뷰어의 삭제 버튼이 서버의 conversation 을 지우자, 그 대화를
        참조하는 큐 행이 매번 400 "unknown conversationId" 를 받게 됐다. 그 대화는
        영원히 돌아오지 않으므로 이 재시도는 영원히 실패한다 — 큐가 막히고,
        LLM 호출과 네트워크만 계속 쓰며, 로그에는 같은 경고가 무한히 쌓인다.

        로컬 큐와 서버 DB 는 서로 다른 저장소이고 함께 지워지지 않는다. 그 어긋남을
        '못 고치는 것'으로 인정하고, 못 고칠 실패는 재시도 대상에서 빼는 것이 맞다.

    왜 401/403 은 여기 포함해도 되는가
        시크릿이 틀린 것은 배포를 고쳐야 풀리지 재시도로는 안 풀린다. 다만 호출부는
        is_auth_failure 로 그 경우를 먼저 걸러 별도 경고를 남긴다 — 조용히 버려지지
        않게 하려는 것이고, 이 함수와 목적이 다르다.
    """
    if not isinstance(error, ExternalServiceError):
        return False
    status = error.status_code
    if status is None:
        return False
    return 400 <= status < 500 and status not in _RETRYABLE_CLIENT_ERROR_STATUS_CODES


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
