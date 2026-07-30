"""STT -> LLM/API -> TTS 파이프라인 (단일 API LLM 체제)."""

from bomi_ai_chat.audio_io.base import AudioInput, AudioOutput
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.llm.medical_flow import handle_medical_query
from bomi_ai_chat.llm.router import is_medical_query
from bomi_ai_chat.stt.client import STTClient
from bomi_ai_chat.tts.client import TTSClient
from bomi_ai_chat.weather.client import CITY_GRID, WeatherClient


class ConversationPipeline:
    """마이크 입력을 받아 LLM 응답 음성을 재생하는 파이프라인."""

    def __init__(
        self,
        audio_in: AudioInput,
        audio_out: AudioOutput,
        settings: Settings | None = None,
    ):
        settings = settings or get_settings()
        self.audio_in = audio_in
        self.audio_out = audio_out
        self.stt = STTClient(settings)
        self.llm = LLMClient(settings)
        self.tts = TTSClient(settings)
        self.weather = WeatherClient(settings)

    def _extract_city(self, text: str) -> str | None:
        """텍스트 안에서 지원하는 도시명을 찾는다."""
        for city in CITY_GRID:
            if city in text:
                return city
        return None

    def run_once(self):
        audio = self.audio_in.capture()
        text = self.stt.transcribe(audio)
        print(f"[STT] 인식된 텍스트: {text}")

        if is_medical_query(text):
            response = handle_medical_query(text)
            print(f"[의료 API] 응답: {response}")
        else:
            weather_data = None
            if "날씨" in text:
                city = self._extract_city(text)
                if city:
                    weather_data = self.weather.get_forecast(city)
                    print(f"[날씨] {city}: {weather_data}")

            response = self.llm.generate(text, weather_data=weather_data)
            print(f"[LLM] 응답: {response}")

        audio_out = self.tts.synthesize(response)
        self.audio_out.play(audio_out)
