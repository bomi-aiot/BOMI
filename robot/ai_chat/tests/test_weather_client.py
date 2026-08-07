"""기상청 timeout, retry, 응답 구조 검증 테스트."""

import pytest

from bomi_ai_chat.http import InvalidResponseError
from bomi_ai_chat.weather.client import WeatherClient, extract_city
from tests.http_fakes import StubResponse, StubSession


def weather_settings(settings_factory):
    return settings_factory(
        KMA_API_KEY="weather-key",
        HTTP_TIMEOUT_SECONDS="6",
        HTTP_MAX_ATTEMPTS="2",
        HTTP_BACKOFF_SECONDS="0.2",
        HTTP_MAX_BACKOFF_SECONDS="0.2",
    )


def weather_response(items, result_code="00"):
    return StubResponse(
        json_data={
            "response": {
                "header": {"resultCode": result_code},
                "body": {"items": {"item": items}},
            }
        }
    )


def test_weather_retries_503_and_parses_forecast(settings_factory):
    session = StubSession(
        StubResponse(503),
        weather_response(
            [
                {"category": "TMP", "fcstValue": "21"},
                {"category": "SKY", "fcstValue": "1"},
            ]
        ),
    )
    delays = []
    client = WeatherClient(
        weather_settings(settings_factory),
        session=session,
        sleep=delays.append,
    )

    assert client.get_forecast("서울") == {
        "기온": "21",
        "하늘상태": "1",
    }
    assert delays == [0.2]
    assert session.calls[0]["timeout"] == 6.0


def test_weather_api_result_error_is_invalid(settings_factory):
    session = StubSession(weather_response([], result_code="03"))
    client = WeatherClient(weather_settings(settings_factory), session=session)

    with pytest.raises(InvalidResponseError, match="result code"):
        client.get_forecast("서울")


def test_weather_missing_item_list_is_invalid(settings_factory):
    session = StubSession(
        StubResponse(
            json_data={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"items": {}},
                }
            }
        )
    )
    client = WeatherClient(weather_settings(settings_factory), session=session)

    with pytest.raises(InvalidResponseError, match="item list"):
        client.get_forecast("서울")


# ── 도시 추출 (S15P11E102-311) ───────────────────────────────────────────────
#
# 원래 pipeline.py(legacy 경로)의 ConversationPipeline._extract_city 메서드
# 안에만 있었다. 그래프 경로(graph/context.py)도 같은 판정이 필요해져서 여기로
# 옮겼다 — 두 경로가 이 함수 하나를 import 해서 쓴다(복사하지 않는다).


def test_extract_city_finds_a_supported_city_mentioned_in_the_text():
    assert extract_city("오늘 서울 날씨 어때") == "서울"
    assert extract_city("부산 날씨 알려줘") == "부산"


def test_extract_city_returns_none_when_no_supported_city_is_mentioned():
    assert extract_city("오늘 날씨 어때") is None
    assert extract_city("") is None
