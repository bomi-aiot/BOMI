"""턴 왕복 시간 실측 — 지연 예산이 지켜지는지 눈에 보이게 한다.

왜 존재하는가
    음성 대화는 약 2초를 넘기면 대화처럼 느껴지지 않는다. 그런데 지연은 조용히
    늘어난다. 기억 top-k 를 올리고, 문서를 붙이고, 프롬프트가 길어지고, 어느 날
    보면 4초가 되어 있다. 그때 "언제부터 느려졌나"를 답할 수 없으면 되돌릴 수도 없다.

    그래서 매 턴 단계별로 재고, 예산을 넘기면 경고를 남긴다. 로그가 곧 회귀 감지다.

왜 clock 이 아니라 time.monotonic 인가  ★ CLAUDE.md §15 의 예외
    §15 는 "시각을 읽을 때" clock 을 쓰라는 규칙이다. 여기서 재는 것은 시각이 아니라
    '경과 시간'이고, 둘은 다르다. SimClock(speed=8640) 을 끼우면 clock 기준 경과는
    실제의 8640배로 나와서 지연 측정이 무의미해진다. 실제 사용자가 기다리는 시간은
    시뮬레이션과 무관하게 흘러야 한다.

    monotonic 은 이 레포에서 이미 http.py, stt/client.py, pipeline.py 가 같은 이유로
    쓰고 있다. 주입 가능한 인자로 두는 관례도 그대로 따른다.

참고
    CLAUDE.md §16 (지연 예산), §18 (네트워크가 병목이다), §15 (시계 주입 규칙)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

from bomi_ai_chat import policy

logger = logging.getLogger(__name__)


@dataclass
class TurnTimer:
    """한 턴의 단계별 경과 시간을 모은다.

    사용 예
        timer = TurnTimer()
        with timer.stage("stt"):
            text = stt.transcribe(audio)
        with timer.stage("graph"):
            result = app.invoke(...)
        timer.finish()          # 예산 초과면 WARNING

    주의사항
        측정 자체가 비싸면 안 된다. monotonic 호출 두 번과 dict 갱신뿐이다.
    """

    monotonic: Callable[[], float] = time.monotonic
    stages: dict[str, float] = field(default_factory=dict)
    _started_at: float | None = None

    def __post_init__(self) -> None:
        self._started_at = self.monotonic()

    @contextmanager
    def stage(self, name: str):
        """한 단계를 잰다. 예외가 나도 잰 값은 남긴다.

        예외 경로에서도 기록하는 이유: 느려서 타임아웃이 난 단계가 바로 우리가
        보고 싶은 단계다. 실패했다고 측정을 버리면 가장 중요한 데이터를 잃는다.
        """
        started = self.monotonic()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (self.monotonic() - started)

    @property
    def elapsed(self) -> float:
        """턴 시작부터 지금까지의 실제 경과 시간(초).

        `is None` 으로 비교하는 이유: 시작 시각 0.0 은 완벽히 정상인 값인데
        `or` 로 쓰면 falsy 라서 '시작 안 함'으로 오인된다.
        """
        if self._started_at is None:
            return 0.0
        return self.monotonic() - self._started_at

    def finish(self, *, senior_id: str = "", intent: str = "") -> float:
        """턴을 마감하고 결과를 남긴다.

        반환값
            총 경과 시간(초).

        주의사항
            예산 초과는 WARNING 이다. INFO 로 두면 아무도 안 본다. 그리고 단계별
            내역을 함께 남긴다 — "느리다"만으로는 어디를 고칠지 알 수 없고,
            대개 범인은 네트워크(문맥 조회·생성·TTS)이지 로컬 계산이 아니다.
        """
        total = self.elapsed
        breakdown = " ".join(f"{name}={value:.3f}s" for name, value in self.stages.items())

        if total > policy.TURN_LATENCY_BUDGET_SEC:
            logger.warning(
                "turn latency %.3fs exceeded budget %.1fs (senior=%s intent=%s) | %s",
                total, policy.TURN_LATENCY_BUDGET_SEC, senior_id, intent, breakdown)
        else:
            logger.info(
                "turn latency %.3fs (senior=%s intent=%s) | %s",
                total, senior_id, intent, breakdown)
        return total
