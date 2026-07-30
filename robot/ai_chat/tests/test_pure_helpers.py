"""네트워크 없이 실행 가능한 응답 변환 로직의 회귀 테스트."""

import pytest

from bomi_ai_chat.llm.client import format_weather
from bomi_ai_chat.weather.client import WeatherClient


def test_weather_parser_keeps_first_value_for_each_category(
    settings_factory,
):
    client = WeatherClient(settings_factory(KMA_API_KEY="weather-key"))

    result = client._parse_items(
        [
            {"category": "TMP", "fcstValue": "21"},
            {"category": "SKY", "fcstValue": "1"},
            {"category": "TMP", "fcstValue": "24"},
            {"category": "POP", "fcstValue": "10"},
            {"category": "REH", "fcstValue": "45"},
        ]
    )

    assert result == {
        "기온": "21",
        "하늘상태": "1",
        "강수확률": "10",
    }


def test_unsupported_city_fails_before_http(settings_factory):
    client = WeatherClient(settings_factory(KMA_API_KEY="weather-key"))

    with pytest.raises(ValueError, match="지원하지 않는 지역"):
        client.get_forecast("없는도시")


def test_weather_format_maps_codes_for_spoken_prompt():
    formatted = format_weather(
        {
            "기온": "21",
            "하늘상태": "1",
            "강수형태": "0",
            "강수확률": "10",
        }
    )

    assert formatted == (
        "[날씨 정보] 기온: 21도, 하늘상태: 맑음, "
        "강수형태: 없음, 강수확률: 10%"
    )
