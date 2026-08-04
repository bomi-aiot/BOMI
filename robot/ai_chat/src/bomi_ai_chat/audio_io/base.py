"""오디오 입력과 출력을 위한 추상 인터페이스.

이 인터페이스 덕분에 파이프라인 코드는 오디오가 노트북에서
들어오는지 로봇에서 들어오는지 신경 쓸 필요가 없다.
"""

from abc import ABC, abstractmethod


class AudioInput(ABC):
    """오디오를 캡처하는 소스의 공통 인터페이스."""

    @abstractmethod
    def capture(self, onset_timeout_seconds: float | None = None) -> bytes:
        """오디오를 녹음하고 WAV 형식의 바이트로 반환한다.

        onset_timeout_seconds
            값을 주면 '단일 리슨' 모드로 동작한다: 발화가 '시작'되기를 이 시간(초)까지
            기다리고, 그 안에 아무 말도 시작되지 않으면 빈 바이트 b""를 반환한다(무응답).
            발화가 시작되면 그때부터 녹음해 말이 끝나면 종료한다. None 이면 예전처럼
            첫 순간부터 녹음하고 침묵/최대 길이로 끊는다.
        """
        ...


class AudioOutput(ABC):
    """오디오를 재생하는 대상의 공통 인터페이스."""

    @abstractmethod
    def play(self, audio_bytes: bytes) -> None:
        """WAV 형식의 오디오 바이트를 재생한다."""
        ...
