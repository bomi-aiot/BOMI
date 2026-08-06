"""외부 HTTP 클라이언트 단위 테스트용 최소 응답과 세션."""

from __future__ import annotations

from typing import Any

_UNSET = object()


class StubResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        json_data: Any = _UNSET,
        json_error: Exception | None = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error
        self.content = content

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        if self._json_data is _UNSET:
            return {}
        return self._json_data


class StubSession:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.outcomes:
            raise AssertionError("준비된 HTTP 응답이 없습니다.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
