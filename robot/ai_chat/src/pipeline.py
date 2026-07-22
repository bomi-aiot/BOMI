"""STT -> LLM -> TTS 순차 파이프라인."""

from src.audio_io.base import AudioInput, AudioOutput
from src.stt.client import STTClient
from src.llm.client import LLMClient
from src.tts.client import TTSClient
from src.weather.client import WeatherClient, CITY_GRID


class ConversationPipeline:
    """마이크 입력을 받아 LLM 응답 음성을 재생하는 파이프라인."""

    def __init__(self, audio_in: AudioInput, audio_out: AudioOutput):
        self.audio_in = audio_in
        self.audio_out = audio_out
        self.stt = STTClient()
        self.llm = LLMClient()
        self.tts = TTSClient()
        self.weather = WeatherClient()

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