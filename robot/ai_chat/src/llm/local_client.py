"""젯슨 로컬 LLM(Ollama) 클라이언트."""

import re
import requests

from .common import SYSTEM_PROMPT, current_time_info, format_weather, clean_response, fix_incomplete_ending


def is_mostly_korean(text: str, threshold: float = 0.3) -> bool:
    """영문자 비율이 threshold 이상이면 비정상 출력으로 간주."""
    letters = re.sub(r"[^a-zA-Z가-힣]", "", text)
    if not letters:
        return True
    english_ratio = len(re.findall(r"[a-zA-Z]", letters)) / len(letters)
    return english_ratio < threshold


class LocalLLMClient:
    def __init__(self, model: str = "exaone3.5:2.4b"):
        self.model = model
        self.url = "http://localhost:11434/api/chat"

    def _call_model(self, messages: list) -> str:
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 40, "temperature": 0.3},
            },
        )
        raw = response.json()["message"]["content"]
        result = clean_response(raw)
        return fix_incomplete_ending(result)

    def generate(self, text: str, weather_data: dict | None = None) -> str:
        full_system_prompt = SYSTEM_PROMPT + "\n\n" + current_time_info()

        user_content = text
        if weather_data:
            user_content = f"{text}\n{format_weather(weather_data)}"

        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": user_content},
        ]

        result = self._call_model(messages)

        if not is_mostly_korean(result):
            result = self._call_model(messages)  # 한 번 재시도

        return result