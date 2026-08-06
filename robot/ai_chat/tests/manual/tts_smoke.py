"""Typecast TTS 응답을 WAV 파일로 저장해 직접 확인한다."""


def main() -> None:
    from pathlib import Path

    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.tts.client import TTSClient

    settings = Settings.from_env()
    if not settings.typecast_api_key:
        raise SystemExit("TYPECAST_API_KEY가 필요합니다.")

    audio = TTSClient(settings).synthesize(
        "안녕하세요, 오늘 하루 어떻게 지내셨어요?"
    )
    output = Path("test_output.wav")
    output.write_bytes(audio)
    print(f"저장 완료: {output.resolve()}")


if __name__ == "__main__":
    main()
