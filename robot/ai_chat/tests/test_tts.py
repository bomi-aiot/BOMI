from dotenv import load_dotenv
load_dotenv()

from src.tts.client import TTSClient

client = TTSClient()
audio = client.synthesize("안녕하세요, 오늘 하루 어떻게 지내셨어요?")

with open("test_output.wav", "wb") as f:
    f.write(audio)

print("성공!")