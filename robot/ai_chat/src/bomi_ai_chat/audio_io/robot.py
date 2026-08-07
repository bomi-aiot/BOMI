"""Jetson에서 명시적으로 선택한 PortAudio 장치를 사용하는 어댑터."""

from bomi_ai_chat.config import Settings, get_settings

from .sounddevice_backend import SoundDeviceAudioInput, SoundDeviceAudioOutput


class RobotAudioInput(SoundDeviceAudioInput):
    """환경설정으로 지정한 로봇 마이크 입력."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        settings.validate_robot_audio()
        super().__init__(
            device=settings.audio_input_device,
            sample_rate=settings.audio_sample_rate,
            channels=settings.audio_channels,
            chunk_seconds=settings.audio_chunk_seconds,
            silence_threshold=settings.audio_silence_threshold,
            silence_limit_seconds=settings.audio_silence_limit_seconds,
            max_seconds=settings.audio_max_seconds,
        )


class RobotAudioOutput(SoundDeviceAudioOutput):
    """환경설정으로 지정한 로봇 스피커 출력."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        settings.validate_robot_audio()
        super().__init__(device=settings.audio_output_device)
