"""노트북 마이크와 RTZR STT 실제 연동을 확인한다."""


def main() -> None:
    from bomi_ai_chat.audio_io.laptop import LaptopMicInput
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.stt.client import STTClient

    settings = Settings.from_env()
    if not settings.rtzr_client_id or not settings.rtzr_client_secret:
        raise SystemExit("RTZR_CLIENT_ID와 RTZR_CLIENT_SECRET이 필요합니다.")

    audio = LaptopMicInput().capture()
    text = STTClient(settings).transcribe(audio)
    print(f"인식된 텍스트: {text}")


if __name__ == "__main__":
    main()
