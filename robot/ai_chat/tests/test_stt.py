# test_stt.py
from dotenv import load_dotenv
load_dotenv()

from bomi_ai_chat.audio_io.laptop import LaptopMicInput
from bomi_ai_chat.stt.client import STTClient

mic = LaptopMicInput(duration_seconds=3)
stt = STTClient()

audio = mic.capture()
text = stt.transcribe(audio)
print(f"인식된 텍스트: {text}")
