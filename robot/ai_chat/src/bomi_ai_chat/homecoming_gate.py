# robot/ai_chat/src/bomi_ai_chat/homecoming_gate.py
"""귀가 대본이 도는 동안 "보미야"를 막는 게이트.

왜 필요한가
    시연에서 문이 열린 뒤 현관으로 이동 -> 귀가 인사 -> 추종 -> 온습도 마무리
    까지가 하나의 대본이다. 그 사이에 웨이크워드가 잡히면 로봇이 대본을 벗어나
    거실 호출 시나리오를 새로 시작한다 — 보는 사람에게는 오작동이다. 특히
    현관으로 이동하는 동안은 메인 루프가 웨이크워드 대기 상태라 무방비다.

    DOOR_OPENED 에서 닫고(start), 온습도 대화가 끝나면 연다(finish).

왜 마감 시각을 함께 두는가
    귀가 대본이 도중에 실패하면(주행이 막혀 START_CONVERSATION 이 영영 안 옴)
    finish 를 부를 사람이 없다. 그때 웨이크워드가 영영 죽으면 이 게이트가
    시연을 살리는 게 아니라 죽인다. 마감이 지나면 스스로 열린다.

[.env 로 조절하는 값들]
    WAKE_BLOCK_DURING_HOMECOMING  "false" 면 막지 않는다(기본 "true").
    HOMECOMING_GATE_TIMEOUT_SEC   최대 차단 시간(초, 기본 300).
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 300.0


def _blocking_enabled() -> bool:
    """차단이 켜져 있는가. 매번 읽는다 — 테스트가 monkeypatch 로 끌 수 있어야 한다."""
    return os.environ.get("WAKE_BLOCK_DURING_HOMECOMING", "true").lower() in (
        "1", "true", "yes"
    )


def _timeout_sec() -> float:
    """최대 차단 시간. 잘못 적혀 있으면 기본값으로 돌아간다."""
    raw = os.environ.get("HOMECOMING_GATE_TIMEOUT_SEC")
    if raw is None:
        return DEFAULT_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "HOMECOMING_GATE_TIMEOUT_SEC=%r 를 숫자로 읽지 못해 %.0f초를 씁니다",
            raw, DEFAULT_TIMEOUT_SEC)
        return DEFAULT_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TIMEOUT_SEC


class HomecomingGate:
    """귀가 대본이 진행 중인지 들고 있는 작은 상태.

    paho 콜백 스레드(문 이벤트)가 세우고 메인 루프가 읽으므로 락으로 감싼다.
    """

    def __init__(self, *, clock=time.monotonic):
        """clock 을 주입받는 이유: 테스트가 300초를 실제로 기다릴 수는 없다."""
        self._clock = clock
        self._lock = threading.Lock()
        self._deadline: float | None = None

    def start(self) -> None:
        """귀가 대본이 시작됐다(DOOR_OPENED). 이 시점부터 웨이크워드를 막는다.

        이미 진행 중이어도 마감을 새로 잡는다 — 문이 다시 열렸다면 대본도
        다시 시작하는 것이 맞다.
        """
        with self._lock:
            self._deadline = self._clock() + _timeout_sec()
        logger.info("귀가 대본 시작 — 웨이크워드를 막습니다")

    def finish(self) -> None:
        """귀가 대본이 끝났다(온습도 대화까지). 웨이크워드를 다시 연다."""
        with self._lock:
            was_running = self._deadline is not None
            self._deadline = None
        if was_running:
            logger.info("귀가 대본 종료 — 웨이크워드를 다시 받습니다")

    def is_running(self) -> bool:
        """지금 귀가 대본이 도는 중인가. 마감이 지났으면 스스로 연다."""
        with self._lock:
            if self._deadline is None:
                return False
            if self._clock() < self._deadline:
                return True
            self._deadline = None
        logger.warning(
            "귀가 대본이 %.0f초 안에 끝나지 않아 웨이크워드를 다시 엽니다 "
            "— 주행이나 백엔드 대화가 중간에 멈췄을 수 있습니다", _timeout_sec())
        return False

    def blocks_wake_word(self) -> bool:
        """웨이크워드를 막아야 하는가. 킬 스위치가 꺼져 있으면 항상 False."""
        if not _blocking_enabled():
            return False
        return self.is_running()
