"""SSAFY GMS를 경유한 Gemini API 클라이언트."""

import os
import requests

from .common import SYSTEM_PROMPT, current_time_info, format_weather


class LLMClient:
    """GMS를 통해 Gemini 모델을 호출하는 클라이언트."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.url = (
            "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com"
            "/v1beta/models/gemini-2.5-flash-lite:generateContent"
        )

    def generate(self, text: str, weather_data: dict | None = None) -> str:
        full_system_prompt = SYSTEM_PROMPT + "\n\n" + current_time_info()

        user_content = text
        if weather_data:
            user_content = f"{text}\n{format_weather(weather_data)}"

        response = requests.post(
            self.url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json={
                "system_instruction": {"parts": [{"text": full_system_prompt}]},
                "contents": [{"parts": [{"text": user_content}]}],
                "generationConfig": {"maxOutputTokens": 60},
            },
        )
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]