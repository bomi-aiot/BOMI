"""노트북 마이크 녹음과 스피커 재생을 직접 확인한다."""


def main() -> None:
    from bomi_ai_chat.audio_io.laptop import (
        LaptopMicInput,
        LaptopSpeakerOutput,
    )

    audio = LaptopMicInput().capture()
    LaptopSpeakerOutput().play(audio)


if __name__ == "__main__":
    main()
