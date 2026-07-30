"""외부 클라이언트가 중앙 설정을 사용하는지 검증한다."""

from bomi_ai_chat.config import Settings
from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.stt.client import STTClient
from bomi_ai_chat.tts.client import TTSClient
from bomi_ai_chat.weather.client import WeatherClient


def test_clients_receive_shared_settings(monkeypatch):
    monkeypatch.setenv("RTZR_CLIENT_ID", "rtzr-id")
    monkeypatch.setenv("RTZR_CLIENT_SECRET", "rtzr-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("TYPECAST_API_KEY", "typecast-key")
    monkeypatch.setenv("TYPECAST_VOICE_ID", "voice-id")
    monkeypatch.setenv("KMA_API_KEY", "weather-key")
    settings = Settings.from_env(load_env_file=False)

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
