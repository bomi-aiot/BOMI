"""Typecast API를 이용한 TTS(Text-to-Speech) 클라이언트."""

import requests

from bomi_ai_chat.config import Settings, get_settings


class TTSClient:
    """텍스트를 음성으로 변환하는 Typecast API 클라이언트."""

    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.api_key = settings.typecast_api_key
        self.voice_id = settings.typecast_voice_id
        self.base_url = "https://api.typecast.ai/v1/text-to-speech"

    def synthesize(self, text: str) -> bytes:
        """텍스트를 받아서 음성 오디오 바이트를 반환한다."""
        response = requests.post(
            self.base_url,
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
        response.raise_for_status()
        return response.content
