"""Server-side client for BOMI's authenticated operator API."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class OperatorApiError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


class OperatorApiClient:
    def __init__(self, base_url: str, shared_secret: str, timeout: float = 8.0) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("BOMI_BACKEND_URL must not be blank")
        if not shared_secret or not shared_secret.strip():
            raise ValueError("OPERATOR_SHARED_SECRET must not be blank")
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret
        self._timeout = timeout

    def runtime_state(self, device_id: str) -> dict[str, Any]:
        return self._request("GET", self._path(device_id, "runtime-state"))

    def cancel_active_scenario(self, device_id: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            self._path(device_id, "active-scenario-cancellations"),
            {"physicalSafetyConfirmed": True, "reason": reason},
        )

    def recover_to_idle(self, device_id: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            self._path(device_id, "mode-recoveries"),
            {"physicalSafetyConfirmed": True, "reason": reason},
        )

    def _path(self, device_id: str, operation: str) -> str:
        normalized = device_id.strip()
        if not normalized:
            raise ValueError("Robot device ID must not be blank")
        return f"/api/v1/operator/robots/{quote(normalized, safe='')}/{operation}"

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            self._base_url + path,
            data=payload,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Operator-Shared-Secret": self._shared_secret,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return self._decode(response.read())
        except HTTPError as error:
            detail = self._decode(error.read())
            message = detail.get("message") or detail.get("error") or str(error)
            raise OperatorApiError(error.code, str(message)) from error
        except URLError as error:
            raise OperatorApiError(None, f"Backend connection failed: {error.reason}") from error

    @staticmethod
    def _decode(raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OperatorApiError(None, "Backend returned an invalid JSON response") from error
        if not isinstance(value, dict):
            raise OperatorApiError(None, "Backend returned a non-object JSON response")
        return value
