from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from api_client import OperatorApiClient, OperatorApiError


class _Response:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._raw


class OperatorApiClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OperatorApiClient("https://example.test/", "secret-value")

    @patch("api_client.urlopen")
    def test_runtime_state_uses_authenticated_operator_path(self, opener) -> None:
        opener.return_value = _Response({"currentMode": "IDLE"})

        result = self.client.runtime_state("bomi-AA001")

        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://example.test/api/v1/operator/robots/bomi-AA001/runtime-state",
        )
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-operator-shared-secret"), "secret-value")
        self.assertEqual(result["currentMode"], "IDLE")

    @patch("api_client.urlopen")
    def test_cancel_sends_safety_confirmation_and_reason(self, opener) -> None:
        opener.return_value = _Response({"disposition": "CANCELLED"})

        self.client.cancel_active_scenario("bomi-AA001", "physical check complete")

        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data),
            {"physicalSafetyConfirmed": True, "reason": "physical check complete"},
        )

    @patch("api_client.urlopen")
    def test_backend_error_is_sanitized_for_ui(self, opener) -> None:
        opener.side_effect = HTTPError(
            "https://example.test", 409, "Conflict", {},
            io.BytesIO(b'{"message":"An active scenario exists"}'),
        )

        with self.assertRaisesRegex(OperatorApiError, "active scenario") as raised:
            self.client.recover_to_idle("bomi-AA001", "checked")

        self.assertEqual(raised.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
