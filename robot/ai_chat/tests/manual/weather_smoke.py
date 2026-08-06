"""기상청과 Gemini를 실제 호출해 날씨 응답을 확인한다."""


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.llm.client import LLMClient
    from bomi_ai_chat.weather.client import WeatherClient

    settings = Settings.from_env()
    if not settings.kma_api_key or not settings.gemini_api_key:
        raise SystemExit("KMA_API_KEY와 GEMINI_API_KEY가 필요합니다.")

    data = WeatherClient(settings).get_forecast("서울")
    response = LLMClient(settings).generate("서울 날씨 알려줘", weather_data=data)
    print(response)


if __name__ == "__main__":
    main()
