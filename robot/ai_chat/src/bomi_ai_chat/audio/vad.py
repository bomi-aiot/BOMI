"""음성 활동 감지(VAD) 경계 — 실물 모델은 실기에서 붙인다.

무엇을 하는 계층인가
    "지금 누군가 말하고 있는가"를 값싸게 판정한다. 로컬에서 돌아야 하고(네트워크
    왕복을 쓸 수 없다), 프레임마다 불리므로 가벼워야 한다.

지금 여기 없는 것  ★ 실기 필요
    Silero VAD 와 openWakeWord 의 실제 구현이 없다. 둘 다 모델 파일과 실제 오디오
    스트림이 필요하고, 이 환경에는 마이크도 스피커도 없다. 그래서 '경계'만 정의하고
    실물은 하드웨어가 있는 곳에서 붙인다.

    억지로 지금 넣지 않는 이유: 오디오 장치 없이 작성한 VAD 연동 코드는 검증할 수
    없고, 검증되지 않은 오디오 코드는 실기에서 어차피 다시 쓰게 된다. 대신 이
    경계 위에 있는 판단 로직(에코 가드, 맞장구 판별, 재큐)은 지금 전부 검증해 둔다.

    실기에서 확인할 항목: docs/hardware/audio-echo-bargein-verification.md

참고
    CLAUDE.md §3 (VAD/웨이크워드), §13 (barge-in), §24 (원거리 마이크 성능 미결)
"""

from __future__ import annotations

from typing import Protocol

from bomi_ai_chat.audio.echo_guard import EchoGuard


class VoiceActivityDetector(Protocol):
    """한 프레임에 대해 발화 강도를 돌려준다.

    반환값
        0.0~1.0 사이의 강도. 임계치와 비교해서 쓴다.

    구현 메모 (실기)
        Silero VAD 를 쓸 예정이다. CPU 로 충분히 돌아가고, Jetson 의 GPU 는
        어차피 외부 API 때문에 거의 유휴다 (CLAUDE.md §18).
    """

    def speech_probability(self, frame: bytes) -> float:
        ...


class EchoAwareVad:
    """VAD 위에 에코 가드를 씌운 얇은 래퍼.

    무엇을 하는가
        원래 VAD 에게 강도를 물어보고, 재생 상태를 반영해 최종 판정을 내린다.
        재생 직후에는 무시하고, 재생 중에는 임계치를 올린다.

    왜 VAD 안이 아니라 래퍼인가
        Silero 를 다른 모델로 갈아끼워도 에코 정책은 그대로여야 한다. 그리고
        에코 정책은 하드웨어 없이 테스트할 수 있는 반면 VAD 는 그렇지 않다.
        섞어두면 둘 다 테스트할 수 없게 된다.

    누가 호출하는가
        캡처 루프(pipeline). 프레임마다.
    """

    def __init__(
        self,
        detector: VoiceActivityDetector,
        echo_guard: EchoGuard,
        base_threshold: float,
    ):
        self._detector = detector
        self._echo_guard = echo_guard
        self._base_threshold = base_threshold

    def is_speech(self, frame: bytes) -> bool:
        """이 프레임을 어르신의 발화로 받아들일 것인가."""
        if self._echo_guard.should_ignore_input():
            # 재생 직후 가드 구간. 모델을 부를 필요도 없다.
            return False
        level = self._detector.speech_probability(frame)
        return self._echo_guard.accepts(level, self._base_threshold)
