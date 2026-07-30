"""노트북 기본 또는 명시된 PortAudio 장치를 사용하는 어댑터."""

from bomi_ai_chat.config import Settings, get_settings

from .sounddevice_backend import SoundDeviceAudioInput, SoundDeviceAudioOutput


class LaptopMicInput(SoundDeviceAudioInput):
    """노트북 마이크 입력. 장치 미지정 시 운영체제 기본값을 사용한다."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(
            device=settings.audio_input_device,
            sample_rate=settings.audio_sample_rate,
            channels=settings.audio_channels,
            chunk_seconds=settings.audio_chunk_seconds,
            silence_threshold=settings.audio_silence_threshold,
            silence_limit_seconds=settings.audio_silence_limit_seconds,
            max_seconds=settings.audio_max_seconds,
        )


class LaptopSpeakerOutput(SoundDeviceAudioOutput):
    """노트북 스피커 출력. 장치 미지정 시 운영체제 기본값을 사용한다."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(device=settings.audio_output_device)
