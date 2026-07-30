"""기상청 timeout, retry, 응답 구조 검증 테스트."""

import pytest

from bomi_ai_chat.http import InvalidResponseError
from bomi_ai_chat.weather.client import WeatherClient
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
