"""오디오 판단 계층 — 에코 억제, 비블로킹 재생, barge-in 양보.

audio_io/ 와의 차이  ★ 혼동 주의
    audio_io/ = 장치 입출력(캡처·재생 백엔드, 마이크 빔 제어). 이미 있고 유지한다.
    audio/    = 그 위의 '판단'. 지금 들어온 소리를 믿을 것인가, 말을 멈출 것인가.

    전자는 하드웨어가 있어야 검증되고, 후자는 없어도 검증된다. 그래서 나눴다.

실기에서 붙여야 하는 것
    Silero VAD 와 openWakeWord 의 실제 구현. 경계(vad.VoiceActivityDetector)만
    정의해 두었다. 확인 항목은 docs/hardware/audio-echo-bargein-verification.md.

참고
    CLAUDE.md §13 (barge-in), §22 3단계
"""

from bomi_ai_chat.audio.echo_guard import EchoGuard
from bomi_ai_chat.audio.playback import SentencePlayer, SpeechPlayback
from bomi_ai_chat.audio.vad import EchoAwareVad, VoiceActivityDetector

__all__ = [
    "EchoGuard",
    "SentencePlayer",
    "SpeechPlayback",
    "EchoAwareVad",
    "VoiceActivityDetector",
]
