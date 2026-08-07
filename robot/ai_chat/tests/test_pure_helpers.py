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
    """레거시 프롬프트도 라벨-값 나열이 아니라 서술형을 쓴다 (S15P11E102-333).

    "기온: 21도, 하늘상태: 맑음" 모양은 모델이 그대로 소리 내어 읽는다 —
    233 실기에서 실제로 그랬다.
    """
    formatted = format_weather(
        {
            "기온": "21",
            "하늘상태": "1",
            "강수형태": "0",
            "강수확률": "10",
        }
    )

    assert formatted == (
        "[날씨 정보] 기온은 21도입니다. 하늘은 맑습니다. 비 올 확률은 10%입니다."
    )


def test_describe_forecast_never_speaks_raw_codes():
    """★ 숫자 코드("하늘상태 3")가 그대로 사람 귀에 닿지 않는다 (S15P11E102-333)."""
    from bomi_ai_chat.weather.client import describe_forecast

    spoken = describe_forecast(
        {"기온": "25", "하늘상태": "3", "강수형태": "0", "강수확률": "30"}
    )

    assert "하늘상태" not in spoken
    assert "강수형태" not in spoken
    assert "구름" in spoken
    assert "25도" in spoken


def test_describe_forecast_skips_rain_chance_while_raining():
    """지금 비가 오면 "비 올 확률 80%" 는 하지 않는 말이다."""
    from bomi_ai_chat.weather.client import describe_forecast

    spoken = describe_forecast(
        {"기온": "18", "하늘상태": "4", "강수형태": "1", "강수확률": "80"}
    )

    assert "비가 옵니다" in spoken
    assert "%" not in spoken


def test_describe_forecast_drops_unknown_codes_silently():
    """기상청이 낯선 코드를 돌려줘도 예외가 나지 않고, 모르는 값은 말하지 않는다."""
    from bomi_ai_chat.weather.client import describe_forecast

    spoken = describe_forecast({"기온": "10", "하늘상태": "9", "강수형태": "7"})

    assert spoken == "기온은 10도입니다."
