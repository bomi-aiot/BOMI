# robot/ai_chat/src/bomi_ai_chat/llm/client.py
"""SSAFY GMS를 경유한 Gemini API 클라이언트."""

import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests

from bomi_ai_chat.clock import clock
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    InvalidResponseError,
    decode_json_object,
    request_with_retry,
)

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
    # ★ 아래 금지가 없으면 모델이 뼈대를 그대로 베껴 출력한다. 233 실기 점검에서
    #   로봇이 "[현재 정보] 오늘은 ... 어르신: 밖에 니가 오나 바로." 를 소리 내어
    #   말했다. 대괄호 라벨과 화자 표시는 모델에게 '읽으라고' 준 것이지
    #   '말하라고' 준 것이 아니다 (CLAUDE.md §17.9).
    "당신의 답변은 그대로 음성으로 읽힙니다. 그래서 다음을 절대 출력하지 않습니다.\n"
    "- 대괄호로 감싼 표시([현재 정보], [날씨 정보], [의료 조회 결과] 등)\n"
    "- '어르신:', '사용자:', '답변:' 같은 화자 표시\n"
    "- 사용자가 방금 한 말을 그대로 되풀이하는 문장\n"
    "이 표시들은 참고용으로 주어질 뿐이며, 답변에는 사람에게 들려줄 말만 담습니다.\n\n"
    # ★ 예시에 '데이터 줄'을 넣지 않는다 (233 실기 후속)
    #   예전 예시에는 "[날씨 정보] 기온: 29도, 하늘상태: 맑음, 강수확률: 10%" 라는
    #   데이터 줄이 그대로 들어 있었다. 그 결과 실기에서, 날씨 정보가 주어지지 '않은'
    #   턴에 모델이 예시의 서식과 숫자를 흉내 내 "[날씨 정보] 기온: 25도, 하늘상태:
    #   구름 많음, 강수확률: 30%" 를 지어냈다 — 라벨은 정제기가 떼어내지만 지어낸
    #   수치는 그대로 음성으로 나간다. 예시는 '답변 문장'만 보여준다.
    "다음은 답변 말투의 예시입니다. "
    "'사용자:'와 '답변:'은 예시를 구분하려고 붙인 것이며, 실제 답변에는 쓰지 않습니다.\n"
    "사용자: 오늘 날씨 알려줘\n"
    "답변: 어디 지역 날씨를 알려드릴까요?\n\n"
    "사용자: 서울 날씨 알려줘 (서울 날씨 데이터가 함께 주어진 경우)\n"
    "답변: 서울은 맑은데 좀 쌀쌀해요. 나가실 때 겉옷 하나 걸치세요.\n\n"
    "사용자: 점심 뭐 먹을까?\n"
    "답변: 오늘은 어떤 음식이 당기세요?\n\n"
    "사용자: 심심해\n"
    "답변: 같이 이야기 나눌까요? 요즘 어떤 게 재밌으셨어요?\n\n"
    "날씨 데이터가 실제로 주어지지 않았다면 반드시 지역을 되물어야 하고, "
    "임의의 수치를 지어내면 안 됩니다. "
    "날씨는 수치 나열이 아니라 행동으로 말합니다(예: 비 올 것 같으니 우산 챙기세요). "
    # 같은 대답을 토씨까지 반복하면 기계처럼 들린다. 같은 질문이 또 와도 내용은
    # 같게, 문장은 조금 다르게 — 반복 질문에 짜증을 내지 않는 것과 함께 §17.4/§17.8.
    "바로 앞 대화에서 자신이 한 말과 토씨까지 똑같은 문장은 피하고, 조금씩 다르게 표현합니다. "
    # §14: 한 번에 한 가지. 실기에서 "3 sentences -> 2" 절단 경고가 반복됐다.
    "그리고 답변은 어떤 경우에도 두 문장을 넘기지 않습니다."
)

def current_time_info() -> str:
    # 시계는 clock 을 통해서만 읽는다(CLAUDE.md §15). datetime.fromtimestamp 는
    # clock.now() 의 POSIX 초를 로컬 벽시계로 변환한다 — 실제 시계에서는 기존
    # datetime.now() 와 같은 값이고, SimClock 을 끼우면 이 안내 문구도 함께 흐른다.
    now = datetime.fromtimestamp(clock.now())
    return (
        f"[현재 정보] 오늘은 {now.strftime('%Y년 %m월 %d일')} "
        f"{WEEKDAYS[now.weekday()]}, 현재 시각은 {now.strftime('%H시 %M분')}입니다."
    )


def format_weather(weather_data: dict) -> str:
    """WeatherClient 결과를 레거시 프롬프트에 실을 문자열로 바꾼다.

    변환은 weather/client.py 의 describe_forecast 하나로 통일한다 (S15P11E102-333).
    예전처럼 여기서 라벨-값 나열("기온: 25도, 하늘상태: 구름많음")을 만들면 모델이
    그 모양 그대로 소리 내어 읽는다 — 233 실기에서 실제로 그랬다. [날씨 정보]
    라벨은 시스템 프롬프트가 참조하는 표지라 남기되, 정제기가 음성에서는 떼어낸다.
    """
    from bomi_ai_chat.weather.client import describe_forecast

    return f"[날씨 정보] {describe_forecast(weather_data)}"


class LLMClient:
    """GMS를 통해 Gemini 모델을 호출하는 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: Any = requests,
        sleep: Callable[[float], None] = time.sleep,
    ):
        settings = settings or get_settings()
        self.api_key = settings.gemini_api_key
        self.timeout_seconds = settings.http_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session
        self._sleep = sleep
        self.url = (
            "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com"
            "/v1beta/models/gemini-2.5-flash-lite:generateContent"
        )

    def generate(self, text: str, weather_data: dict | None = None) -> str:
        full_system_prompt = SYSTEM_PROMPT + "\n\n" + current_time_info()

        user_content = text
        if weather_data:
            user_content = f"{text}\n{format_weather(weather_data)}"

        response = request_with_retry(
            "POST",
            self.url,
            service="Gemini",
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds,
            max_backoff_seconds=self.max_backoff_seconds,
            session=self._session,
            sleep=self._sleep,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json={
                "system_instruction": {"parts": [{"text": full_system_prompt}]},
                "contents": [{"parts": [{"text": user_content}]}],
                # maxOutputTokens 를 60 으로 두었을 때 한국어 두 문장(80자)이 토큰
                # 상한에 먼저 걸려 "…잠시 쉬세요. 다" 처럼 문장이 중간에 잘린 채
                # 음성으로 나갔다(233 실기). 길이는 프롬프트("두 문장 이내")와
                # response_shaper(MAX_SENTENCES)가 잡는다 — 토큰 상한은 폭주
                # 방지용 여유값으로만 둔다.
                #   올리면 -> 잘림은 없지만 폭주 시 낭비가 커진다.
                #   내리면 -> 다시 문장이 중간에 끊기기 시작한다.
                "generationConfig": {"maxOutputTokens": 256},
            },
        )
        result = decode_json_object(response, service="Gemini")
        candidates = result.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise InvalidResponseError("Gemini", "response has no candidates")

        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise InvalidResponseError("Gemini", "candidate must be an object")
        content = first_candidate.get("content")
        if not isinstance(content, dict):
            raise InvalidResponseError("Gemini", "candidate has no content object")
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise InvalidResponseError("Gemini", "content has no parts")

        texts = [
            part["text"].strip()
            for part in parts
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and part["text"].strip()
        ]
        if not texts:
            raise InvalidResponseError("Gemini", "response has no text")
        return "".join(texts)
