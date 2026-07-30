"""RTZR Sommers API를 이용한 STT(Speech-to-Text) 클라이언트."""

import time
from collections.abc import Callable
from typing import Any

import requests

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    ExternalServiceError,
    InvalidResponseError,
    decode_json_object,
    request_with_retry,
)

AUTH_URL = "https://openapi.vito.ai/v1/authenticate"
TRANSCRIBE_URL = "https://openapi.vito.ai/v1/transcribe"
PENDING_STATUSES = frozenset({"waiting", "queued", "transcribing", "processing"})


class STTClient:
    """오디오를 텍스트로 변환하는 RTZR API 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: Any = requests,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        settings = settings or get_settings()
        self.client_id = settings.rtzr_client_id
        self.client_secret = settings.rtzr_client_secret
        self.timeout_seconds = settings.http_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self.poll_interval_seconds = settings.stt_poll_interval_seconds
        self.poll_timeout_seconds = settings.stt_poll_timeout_seconds
        self.token_ttl_seconds = settings.stt_token_ttl_seconds
        self._session = session
        self._sleep = sleep
        self._monotonic = monotonic
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float | None = None,
        deadline: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        return request_with_retry(
            method,
            url,
            service="RTZR STT",
            timeout_seconds=timeout_seconds or self.timeout_seconds,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds,
            max_backoff_seconds=self.max_backoff_seconds,
            session=self._session,
            sleep=self._sleep,
            deadline=deadline,
            monotonic=self._monotonic,
            **kwargs,
        )

    def _get_token(self) -> str:
        if self._token and self._monotonic() < self._token_expires_at:
            return self._token

        response = self._request(
            "POST",
            AUTH_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        data = decode_json_object(response, service="RTZR STT")
        token = data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise InvalidResponseError(
                "RTZR STT",
                "authentication response has no access_token",
            )

        self._token = token.strip()
        self._token_expires_at = self._monotonic() + self.token_ttl_seconds
        return self._token

    @staticmethod
    def _completed_text(data: dict[str, Any]) -> str:
        results = data.get("results")
        if not isinstance(results, dict):
            raise InvalidResponseError(
                "RTZR STT",
                "completed response has no results object",
            )
        utterances = results.get("utterances")
        if not isinstance(utterances, list):
            raise InvalidResponseError(
                "RTZR STT",
                "completed response has no utterances list",
            )

        messages = []
        for utterance in utterances:
            if not isinstance(utterance, dict):
                raise InvalidResponseError(
                    "RTZR STT",
                    "utterance must be an object",
                )
            message = utterance.get("msg")
            if not isinstance(message, str):
                raise InvalidResponseError(
                    "RTZR STT",
                    "utterance has no text message",
                )
            if message.strip():
                messages.append(message.strip())
        return " ".join(messages)

    def transcribe(self, audio: bytes) -> str:
        """오디오 바이트를 받아서 인식된 텍스트를 반환한다."""
        if not isinstance(audio, bytes) or not audio:
            raise ValueError("STT 입력 오디오는 비어 있지 않은 bytes여야 합니다.")

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = self._request(
            "POST",
            TRANSCRIBE_URL,
            headers=headers,
            files={"file": ("audio.wav", audio)},
            data={"config": '{"model_name": "sommers", "language": "ko"}'},
        )
        upload_data = decode_json_object(response, service="RTZR STT")
        transcribe_id = upload_data.get("id")
        if not isinstance(transcribe_id, str) or not transcribe_id.strip():
            raise InvalidResponseError(
                "RTZR STT",
                "upload response has no transcription id",
            )

        deadline = self._monotonic() + self.poll_timeout_seconds
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ExternalServiceError(
                    "RTZR STT",
                    "polling deadline exceeded",
                    category="polling_timeout",
                )

            try:
                result_response = self._request(
                    "GET",
                    f"{TRANSCRIBE_URL}/{transcribe_id}",
                    deadline=deadline,
                    headers=headers,
                )
            except ExternalServiceError as exc:
                if exc.category == "deadline":
                    raise ExternalServiceError(
                        "RTZR STT",
                        "polling deadline exceeded",
                        category="polling_timeout",
                    ) from exc
                raise
            result = decode_json_object(result_response, service="RTZR STT")
            status = result.get("status")
            if not isinstance(status, str):
                raise InvalidResponseError(
                    "RTZR STT",
                    "polling response has no status",
                )

            if status == "completed":
                return self._completed_text(result)
            if status == "failed":
                raise ExternalServiceError(
                    "RTZR STT",
                    "transcription processing failed",
                    category="processing",
                )
            if status not in PENDING_STATUSES:
                raise InvalidResponseError(
                    "RTZR STT",
                    f"unexpected transcription status: {status!r}",
                )

            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ExternalServiceError(
                    "RTZR STT",
                    "polling deadline exceeded",
                    category="polling_timeout",
                )
            self._sleep(min(self.poll_interval_seconds, remaining))
