"""에코 가드 — 로봇이 자기 목소리를 어르신의 말로 착각하지 않게 한다.

왜 이것이 능동 발화보다 먼저인가
    스피커와 마이크가 한 몸통에 있다. TTS 출력이 그대로 마이크로 되돌아오고, VAD 는
    그것을 "누군가 말한다"로 읽는다. 그러면 로봇은 자기 말에 자기가 멈춘다.

    이걸 해결하지 않은 채 능동 발화를 테스트하면 **모든 버그 리포트가 실제로는
    에코다.** 게이트 버그로 오진하면 디버깅이 지옥이 된다. 그래서 CLAUDE.md §22 가
    이 단계를 3번에, 능동성(4번)보다 앞에 둔다.

두 겹으로 막는다
    1. 재생 시작 직후 ECHO_GUARD_SEC 동안은 입력을 아예 무시한다. 스피커가 소리를
       내기 시작하는 구간이고, 이때 들어오는 것은 거의 확실히 우리 목소리다.
    2. 재생이 이어지는 동안에는 VAD 임계치를 올린다. 완전히 막지는 않는다 —
       막으면 barge-in 이 원리적으로 불가능해지고, 양보 우선 정책이 죽는다.

    2번이 핵심이다. "재생 중에는 듣지 않는다"가 아니라 "재생 중에는 더 크게 말해야
    들린다"이다.

이건 AEC 가 아니다
    진짜 해법은 음향 반향 제거(AEC)이고, 이것은 값싼 완화책이다. 어느 쪽으로 갈지는
    실기에서 측정한 뒤 정한다(CLAUDE.md §24). 다만 둘 중 아무것도 없는 상태로
    능동 발화를 만들면 안 되므로, 지금은 이 완화책을 둔다.

참고
    CLAUDE.md §13 (barge-in), §22 3단계, §24 (AEC vs 임계치 미결)
    docs/hardware/audio-echo-bargein-verification.md (실기 확인 항목)
"""

from __future__ import annotations

import logging
import threading

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock

logger = logging.getLogger(__name__)

class EchoGuard:
    """재생 상태를 보고 "지금 들어온 입력을 믿어도 되는가"를 판정한다.

    무엇을 하는가
        재생 시작·종료를 기록하고, 입력이 들어올 때마다 세 가지 중 하나를 답한다.
          - 무시한다        (재생 직후 가드 구간)
          - 임계치를 올린다 (재생 중)
          - 그대로 받는다   (조용할 때)

    왜 시각을 clock 으로 읽는가
        가드 구간 판정은 '시각' 비교다. 압축 시계로 시연할 때도 일관되게 동작해야
        한다 (CLAUDE.md §15).

    스레드 안전성
        재생 스레드가 mark_* 를 부르고 캡처 스레드가 판정을 부른다. 값이 두 개뿐이라
        락 하나로 충분하다.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playing = False
        self._started_at = 0.0

    def mark_playback_started(self) -> None:
        """재생이 시작됐다. 재생 스레드가 부른다."""
        with self._lock:
            self._playing = True
            self._started_at = clock.now()
        logger.debug("echo guard: playback started (ignoring input for %.2fs)",
                     policy.ECHO_GUARD_SEC)

    def mark_playback_stopped(self) -> None:
        """재생이 끝났거나 취소됐다."""
        with self._lock:
            self._playing = False
        logger.debug("echo guard: playback stopped")

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def should_ignore_input(self) -> bool:
        """지금 들어온 입력을 아예 버려야 하는가?

        반환값
            True -> 버린다. 재생이 막 시작된 구간이라 우리 목소리일 확률이 매우 높다.

        주의사항
            이 구간을 길게 잡으면 어르신이 로봇의 첫 마디에 바로 끼어들 때 그것을
            놓친다. 짧게 잡으면 에코가 새어 들어온다. policy.ECHO_GUARD_SEC 의
            기본값은 추정치이며 실기 측정으로 조정해야 한다.
        """
        with self._lock:
            if not self._playing:
                return False
            return (clock.now() - self._started_at) < policy.ECHO_GUARD_SEC

    def vad_threshold(self, base_threshold: float) -> float:
        """지금 적용할 VAD 임계치.

        무엇을 하는가
            재생 중이면 기본 임계치를 올려서 돌려준다. 조용하면 그대로 돌려준다.

        왜 무한대로 올리지 않는가
            재생 중 입력을 완전히 막으면 barge-in 이 불가능해진다. 청력이 떨어진
            어르신은 로봇이 말하는 중인 것을 모른 채 말을 시작하는데, 그 발화가
            우리 발화보다 항상 더 가치 있다 (CLAUDE.md §13 양보 우선).
        """
        if not self.is_playing:
            return base_threshold
        return base_threshold * policy.ECHO_VAD_THRESHOLD_MULTIPLIER

    def accepts(self, level: float, base_threshold: float) -> bool:
        """이 입력을 '어르신의 발화'로 받아들일 것인가.

        인자
            level: VAD 가 측정한 입력 강도.
            base_threshold: 조용할 때 쓰는 기준값.

        누가 호출하는가
            캡처 루프. 이 판정이 False 면 그 프레임은 없었던 것으로 친다.
        """
        if self.should_ignore_input():
            # ★ 실기에서 임계치를 재려면 '무엇을 왜 버렸는지'가 보여야 한다
            #   (S15P11E102-233). 로그가 없으면 관찰할 수 있는 것이 "멈췄다 / 안
            #   멈췄다"뿐이고, 그 둘 사이에서 ECHO_GUARD_SEC 을 조정할 근거가 없다.
            logger.debug(
                "echo guard: dropped level=%.0f (playback started %.2fs ago, "
                "guard=%.2fs)", level, clock.now() - self._started_at,
                policy.ECHO_GUARD_SEC)
            return False

        threshold = self.vad_threshold(base_threshold)
        accepted = level >= threshold
        if self.is_playing:
            # 재생 중의 판정만 남긴다. 조용할 때의 판정까지 남기면 캡처 루프가
            # 매 프레임 로그를 찍어 다른 것을 전부 덮는다.
            logger.debug(
                "echo guard: %s level=%.0f threshold=%.0f (base=%.0f x%.1f, playing)",
                "accepted" if accepted else "rejected", level, threshold,
                base_threshold, policy.ECHO_VAD_THRESHOLD_MULTIPLIER)
        return accepted
