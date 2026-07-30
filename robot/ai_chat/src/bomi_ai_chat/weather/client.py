"""기상청 단기예보 API를 이용한 날씨 조회 클라이언트."""

from datetime import datetime, timedelta

import requests

from bomi_ai_chat.config import Settings, get_settings

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


class WeatherClient:
    """기상청 단기예보 API 클라이언트."""

    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.service_key = settings.kma_api_key
        self.base_url = (
            "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
            "/getVilageFcst"
        )

    def _get_base_datetime(self):
        """가장 최근 발표된 예보 시각을 계산한다.
        단기예보는 02,05,08,11,14,17,20,23시에 발표된다."""
        now = datetime.now()
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

        response = requests.get(
            self.base_url,
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
        response.raise_for_status()
        data = response.json()

        items = data["response"]["body"]["items"]["item"]
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
            category = item["category"]
            if category in category_map:
                key = category_map[category]
                if key not in result:
                    result[key] = item["fcstValue"]
        return result
