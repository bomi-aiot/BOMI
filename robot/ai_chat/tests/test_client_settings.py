"""외부 클라이언트가 중앙 설정을 사용하는지 검증한다."""

from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.stt.client import STTClient
from bomi_ai_chat.tts.client import TTSClient
from bomi_ai_chat.weather.client import WeatherClient


def test_clients_receive_shared_settings(settings_factory):
    settings = settings_factory(
        RTZR_CLIENT_ID="rtzr-id",
        RTZR_CLIENT_SECRET="rtzr-secret",
        GEMINI_API_KEY="gemini-key",
        TYPECAST_API_KEY="typecast-key",
        TYPECAST_VOICE_ID="voice-id",
        KMA_API_KEY="weather-key",
    )

    stt = STTClient(settings)
    llm = LLMClient(settings)
    tts = TTSClient(settings)
    weather = WeatherClient(settings)

    assert stt.client_id == "rtzr-id"
    assert stt.client_secret == "rtzr-secret"
    assert llm.api_key == "gemini-key"
    assert tts.api_key == "typecast-key"
    assert tts.voice_id == "voice-id"
    assert weather.service_key == "weather-key"
