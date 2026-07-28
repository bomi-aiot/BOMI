# robot/ai_chat/src/llm/client.py
"""SSAFY GMS를 경유한 Gemini API 클라이언트."""

import os
import re
from datetime import datetime
import requests

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 각종 이모지 블록
    "\U00002600-\U000027BF"  # 기타 심볼(☀, ✨ 등)
    "]+",
    flags=re.UNICODE,
)

WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

SYSTEM_PROMPT = (
    "당신의 이름은 보미입니다."
    "당신은 노인 돌봄 로봇의 대화 친구입니다. "
    "실제 사람이 옆에서 대화하듯 짧게 답합니다. "
    "반드시 한국어로만 답변합니다."
    "모든 답변은 예외 없이 한 문장에서 최대 두 문장, 80자 이내로만 작성합니다. "
    "목록, 예시, 번호, 별표(*), 이모지, 강조 표시(**)는 절대 사용하지 않습니다. "
    "정보가 부족하면 딱 한 문장으로만 되묻습니다. "
    "모르는 것을 절대 지어내지 말고, 모르면 모른다고 답하거나 되묻습니다.\n\n"
    "오늘 날짜와 현재 시각은 매 요청마다 아래에 직접 제공되므로, "
    "그것에 대해서는 그 값을 그대로 사용합니다. "
    "날씨 정보가 [날씨 정보]로 제공된 경우에는 그 데이터를 바탕으로 자연스럽게 답합니다. "
    "날씨를 물었는데 [날씨 정보]가 없다면, 어느 지역인지 되묻습니다. "
    "그 외의 실시간 정보는 알 수 없으므로 지어내지 말고 모른다고 답하세요.\n\n"
    "다음은 반드시 지켜야 할 출력 형식의 예시입니다.\n"
    "사용자: 오늘 날씨 알려줘\n"
    "답변: 어디 지역의 날씨를 알려드릴까요?\n\n"
    "사용자: 서울 날씨 알려줘\n"
    "[날씨 정보] 기온: 29도, 하늘상태: 맑음, 강수확률: 10%\n"
    "답변: 서울은 맑고 기온은 29도, 비 올 확률은 낮아요.\n\n"
    "사용자: 점심 뭐 먹을까?\n"
    "답변: 오늘은 어떤 음식이 당기세요?\n\n"
    "사용자: 심심해\n"
    "답변: 같이 이야기 나눌까요? 요즘 어떤 게 재밌으셨어요?"
    "위 예시는 출력 형식을 보여주기 위한 것일 뿐이며, [날씨 정보]가 실제로 주어지지 않았다면 반드시 지역을 되물어야 하고 임의의 수치를 지어내면 안 됩니다."
)

SKY_MAP = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY_MAP = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}


def current_time_info() -> str:
    now = datetime.now()
    return (
        f"[현재 정보] 오늘은 {now.strftime('%Y년 %m월 %d일')} "
        f"{WEEKDAYS[now.weekday()]}, 현재 시각은 {now.strftime('%H시 %M분')}입니다."
    )


def format_weather(weather_data: dict) -> str:
    """WeatherClient가 반환한 딕셔너리를 사람이 읽기 쉬운 문자열로 변환."""
    sky = SKY_MAP.get(weather_data.get("하늘상태"), weather_data.get("하늘상태"))
    pty = PTY_MAP.get(weather_data.get("강수형태"), weather_data.get("강수형태"))
    return (
        f"[날씨 정보] 기온: {weather_data.get('기온')}도, "
        f"하늘상태: {sky}, 강수형태: {pty}, "
        f"강수확률: {weather_data.get('강수확률')}%"
    )


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