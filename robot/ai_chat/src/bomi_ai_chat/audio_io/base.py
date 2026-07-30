"""오디오 입력과 출력을 위한 추상 인터페이스.

이 인터페이스 덕분에 파이프라인 코드는 오디오가 노트북에서
들어오는지 로봇에서 들어오는지 신경 쓸 필요가 없다.
"""

from abc import ABC, abstractmethod


class AudioInput(ABC):
    """오디오를 캡처하는 소스의 공통 인터페이스."""

    @abstractmethod
    def capture(self) -> bytes:
        """오디오를 녹음하고 WAV 형식의 바이트로 반환한다."""
        ...


class AudioOutput(ABC):
    """오디오를 재생하는 대상의 공통 인터페이스."""

    @abstractmethod
    def play(self, audio_bytes: bytes) -> None:
        """WAV 형식의 오디오 바이트를 재생한다."""
        ...
