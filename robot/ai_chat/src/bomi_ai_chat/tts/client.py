"""Typecast API를 이용한 TTS(Text-to-Speech) 클라이언트."""

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    InvalidResponseError,
    request_with_retry,
)
from bomi_ai_chat.turn_timer import current_stage

logger = logging.getLogger(__name__)


class TTSClient:
    """텍스트를 음성으로 변환하는 Typecast API 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: Any = requests,
        sleep: Callable[[float], None] = time.sleep,
    ):
        settings = settings or get_settings()
        self.api_key = settings.typecast_api_key
        self.voice_id = settings.typecast_voice_id
        self.timeout_seconds = settings.http_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session
        self._sleep = sleep
        self.base_url = "https://api.typecast.ai/v1/text-to-speech"

    def synthesize(self, text: str) -> bytes:
        started_at = time.monotonic()
        try:
            with current_stage("tts"):
                return self._synthesize(text)
        finally:
            logger.info(
                "tts latency %.3fs chars=%d",
                time.monotonic() - started_at,
                len(text) if isinstance(text, str) else 0,
            )

    def _synthesize(self, text: str) -> bytes:
        """텍스트를 받아서 음성 오디오 바이트를 반환한다."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("TTS 입력 텍스트는 비어 있지 않은 문자열이어야 합니다.")

        response = request_with_retry(
            "POST",
            self.base_url,
            service="Typecast TTS",
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds,
            max_backoff_seconds=self.max_backoff_seconds,
            session=self._session,
            sleep=self._sleep,
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": self.api_key,
            },
            json={
                "voice_id": self.voice_id,
                "text": text,
                "model": "ssfm-v30",
                "language": "kor",
                "output": {"audio_format": "wav"},
            },
        )
        audio = response.content
        if (
            not isinstance(audio, bytes)
            or len(audio) < 12
            or audio[:4] != b"RIFF"
            or audio[8:12] != b"WAVE"
        ):
            raise InvalidResponseError(
                "Typecast TTS",
                "response is not a WAV payload",
            )
        return audio
