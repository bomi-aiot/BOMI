"""기상청 단기예보 API를 이용한 날씨 조회 클라이언트."""

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import requests

from bomi_ai_chat.clock import clock
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    InvalidResponseError,
    decode_json_object,
    request_with_retry,
)

# 주요 도시 격자 좌표 (nx, ny) - 필요한 지역은 이후 추가
CITY_GRID = {
    "서울": (60, 127),
    "부산": (98, 76),
    "대구": (89, 90),
    "인천": (55, 124),
    "광주": (58, 74),
    "대전": (67, 100),
    "울산": (102, 84),
    "수원": (60, 121),
    "제주": (52, 38),
}


# 기상청 코드 → 사람이 듣는 말. (S15P11E102-333)
#
# 왜 여기 있는가
#   코드값의 뜻은 이 API 의 계약이므로, 그것을 아는 곳은 이 클라이언트 하나여야
#   한다. 예전에는 llm/client.py 가 자기 변환표를 따로 들고 있었고, 그래프 경로
#   (graph/context.py)는 변환 없이 원시 코드를 그대로 참고 자료에 실어서
#   "하늘상태 3" 이 모델 프롬프트에 들어갔다 — 두 경로의 말이 갈라지는 전형이다.
_SKY_SPOKEN = {"1": "하늘은 맑습니다", "3": "구름이 많습니다", "4": "하늘이 흐립니다"}
_PTY_SPOKEN = {
    "1": "지금 비가 옵니다",
    "2": "지금 비나 눈이 옵니다",
    "3": "지금 눈이 옵니다",
    "4": "지금 소나기가 옵니다",
}


def describe_forecast(forecast: dict) -> str:
    """조회 결과를 사람이 들을 수 있는 서술형 문장으로 바꾼다. (S15P11E102-333)

    무엇을 하는가
        {"기온": "21", "하늘상태": "1", "강수형태": "0", "강수확률": "10"} 를
        "기온은 21도입니다. 하늘은 맑습니다. 비 올 확률은 10%입니다." 로 바꾼다.

    왜 존재하는가
        233 실기에서 로봇이 "기온: 25도, 하늘상태: 구름 많음" 식의 라벨-값
        나열을 소리 내어 읽었다. 라벨-값 모양은 모델에게 그대로 읽으라고
        유도하는 모양이고, 숫자 코드("하늘상태 1")는 모델이 뜻을 몰라 최악에는
        "1등급입니다" 같은 없는 개념을 지어낸다. 서술형으로 미리 바꿔 주면
        모델은 그 위에서 행동 중심의 답("우산 챙기세요")을 만들기만 하면 된다.

    누가 호출하는가
        graph/context.py 의 날씨 참고 자료, llm/client.py 의 레거시 프롬프트.
        두 경로가 반드시 이 한 함수를 쓴다 — 한쪽만 고치면 말투가 갈라진다.

    주의사항
        - 모르는 코드값은 말하지 않는다. 예외도 던지지 않는다. 기상청이 낯선
          값을 돌려줘도 그 항목만 조용히 빠진다.
        - 지금 비가 오면 하늘 상태와 강수확률은 굳이 말하지 않는다. "비가 오고
          강수확률 80%" 는 사람이 하지 않는 말이다.
    """
    sentences: list[str] = []

    temperature = str(forecast.get("기온") or "").strip()
    if temperature:
        sentences.append(f"기온은 {temperature}도입니다")

    spoken_precip = _PTY_SPOKEN.get(str(forecast.get("강수형태") or "").strip())
    if spoken_precip:
        sentences.append(spoken_precip)
    else:
        spoken_sky = _SKY_SPOKEN.get(str(forecast.get("하늘상태") or "").strip())
        if spoken_sky:
            sentences.append(spoken_sky)
        rain_chance = str(forecast.get("강수확률") or "").strip()
        if rain_chance and rain_chance != "0":
            sentences.append(f"비 올 확률은 {rain_chance}%입니다")

    return ". ".join(sentences) + ("." if sentences else "")


def extract_city(text: str) -> str | None:
    """문장 안에서 CITY_GRID 가 지원하는 도시명을 찾는다.

    왜 여기 있는가 (S15P11E102-311)
        원래 legacy 파이프라인(pipeline.py)의 ConversationPipeline 안에 메서드로만
        있었다. 그래프 경로(graph/context.py)도 날씨 조회를 하려면 같은 판정이
        필요한데, 그대로 복사하면 도시 목록이 두 곳에 생기고 CITY_GRID 에 도시를
        추가할 때마다 하나를 빠뜨릴 위험이 생긴다. 그래서 날씨 클라이언트가 이미
        소유한 CITY_GRID 옆으로 옮기고, 두 경로가 이 함수 하나를 import 해서 쓴다.

    반환값
        가장 먼저 매칭되는 도시명, 없으면 None. 여러 도시가 동시에 언급되는 문장은
        드물다고 보고 첫 매치를 쓴다 — 애매하면 로봇이 되묻는 편이 낫지만, 그 판단은
        호출부(조회 실패/도시 불명 처리)의 몫이다.
    """
    for city in CITY_GRID:
        if city in text:
            return city
    return None


class WeatherClient:
    """기상청 단기예보 API 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: Any = requests,
        sleep: Callable[[float], None] = time.sleep,
    ):
        settings = settings or get_settings()
        self.service_key = settings.kma_api_key
        self.timeout_seconds = settings.http_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session
        self._sleep = sleep
        self.base_url = (
            "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
            "/getVilageFcst"
        )

    def _get_base_datetime(self):
        """가장 최근 발표된 예보 시각을 계산한다.
        단기예보는 02,05,08,11,14,17,20,23시에 발표된다."""
        # 발표 시각 계산도 clock 을 통해서만 시간을 읽는다(CLAUDE.md §15).
        # datetime.fromtimestamp(clock.now()) 는 로컬 시(hour)를 그대로 보존하므로
        # KMA 발표시각(KST) 계산이 기존 datetime.now() 와 동일하게 동작한다.
        now = datetime.fromtimestamp(clock.now())
        base_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        available = [h for h in base_hours if h <= now.hour]

        if available:
            base_hour = max(available)
            base_date = now.strftime("%Y%m%d")
        else:
            base_hour = 23
            base_date = (now - timedelta(days=1)).strftime("%Y%m%d")

        return base_date, f"{base_hour:02d}00"

    def get_forecast(self, city: str) -> dict:
        """도시명을 받아 오늘의 날씨 요약 데이터를 반환한다."""
        if city not in CITY_GRID:
            raise ValueError(f"지원하지 않는 지역입니다: {city}")

        nx, ny = CITY_GRID[city]
        base_date, base_time = self._get_base_datetime()

        response = request_with_retry(
            "GET",
            self.base_url,
            service="기상청",
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds,
            max_backoff_seconds=self.max_backoff_seconds,
            session=self._session,
            sleep=self._sleep,
            params={
                "serviceKey": self.service_key,
                "pageNo": "1",
                "numOfRows": "100",
                "dataType": "JSON",
                "base_date": base_date,
                "base_time": base_time,
                "nx": nx,
                "ny": ny,
            },
        )
        data = decode_json_object(response, service="기상청")
        response_data = data.get("response")
        if not isinstance(response_data, dict):
            raise InvalidResponseError("기상청", "response object is missing")

        header = response_data.get("header")
        if not isinstance(header, dict):
            raise InvalidResponseError("기상청", "response header is missing")
        result_code = header.get("resultCode")
        if str(result_code) not in {"0", "00"}:
            raise InvalidResponseError(
                "기상청",
                f"API result code is {result_code!r}",
            )

        body = response_data.get("body")
        if not isinstance(body, dict):
            raise InvalidResponseError("기상청", "response body is missing")
        items_container = body.get("items")
        if not isinstance(items_container, dict):
            raise InvalidResponseError("기상청", "items object is missing")
        items = items_container.get("item")
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise InvalidResponseError("기상청", "item list is missing")
        return self._parse_items(items)

    def _parse_items(self, items: list) -> dict:
        """필요한 항목만 뽑아 정리한다."""
        result = {}
        category_map = {
            "TMP": "기온",
            "SKY": "하늘상태",
            "PTY": "강수형태",
            "POP": "강수확률",
        }
        for item in items:
            if not isinstance(item, dict):
                raise InvalidResponseError("기상청", "forecast item must be an object")
            category = item.get("category")
            if category in category_map:
                value = item.get("fcstValue")
                if not isinstance(value, (str, int, float)):
                    raise InvalidResponseError(
                        "기상청",
                        f"{category} item has no forecast value",
                    )
                key = category_map[category]
                if key not in result:
                    result[key] = str(value)
        if not result:
            raise InvalidResponseError(
                "기상청",
                "forecast has no supported categories",
            )
        return result
