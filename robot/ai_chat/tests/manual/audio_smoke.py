"""설정한 laptop/robot 마이크와 스피커를 직접 확인한다."""


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.main import _build_audio_adapters

    settings = Settings.from_env()
    settings.validate_audio()
    audio_in, audio_out = _build_audio_adapters(settings)

    print(f"[오디오 모드] {settings.audio_mode}")
    audio = audio_in.capture()
    audio_out.play(audio)


if __name__ == "__main__":
    main()
