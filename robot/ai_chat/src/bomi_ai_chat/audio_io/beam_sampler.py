# robot/ai_chat/src/bomi_ai_chat/audio_io/beam_sampler.py
"""마이크가 잡는 소리 방향을 백그라운드에서 계속 기록한다.

왜 필요한가 (2026-08-09 실기)
    마이크(XVF3800)의 방향 추정은 **말이 나오는 동안에만** 정확하다. 같은
    자리에서 말하는 중에는 154.9/154.6/154.5/154.2 처럼 촘촘히 일치하지만,
    말이 끊긴 뒤에는 매번 전혀 다른 각도가 나온다. 그런데 웨이크워드는
    "보미야"를 **다 말한 뒤에** 감지되므로, 그 시점에 방향을 읽으면 이미
    말이 끝난 뒤의 무작위 값을 잡는다 — 왼쪽에서 불렀는데 오른쪽으로 도는
    증상의 원인이었다.

    그래서 방향을 계속 기록해 두고, 웨이크워드가 감지되면 "직전 몇 초"
    구간의 값들, 즉 사람이 실제로 말하던 동안의 값들을 쓴다.

주의사항
    - 읽기는 xvf_host 프로세스를 띄우는 방식이라 공짜가 아니다. 간격을
      너무 좁히지 않는다(기본 0.2초).
    - 읽기 실패는 조용히 건너뛴다. 방향은 부가 기능이고 대화가 본체다.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 0.2
DEFAULT_HISTORY_SEC = 6.0


class BeamDirectionSampler:
    """소리 방향을 주기적으로 읽어 최근 이력을 들고 있는다."""

    def __init__(
        self,
        read_direction_deg,
        *,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        history_sec: float = DEFAULT_HISTORY_SEC,
        clock=time.monotonic,
    ) -> None:
        """방향 읽기 콜백과 주기를 받는다.

        Args:
            read_direction_deg: 절대 각도(도)를 돌려주는 콜백. 실패 시 예외.
            interval_sec: 읽는 간격(초).
            history_sec: 몇 초 분량을 들고 있을지.
            clock: 단조 증가 시계. 테스트에서 갈아 끼운다.
        """
        if interval_sec <= 0.0:
            raise ValueError("interval_sec must be positive")
        if history_sec <= 0.0:
            raise ValueError("history_sec must be positive")

        self._read_direction_deg = read_direction_deg
        self._interval_sec = float(interval_sec)
        self._history_sec = float(history_sec)
        self._clock = clock

        self._samples: list[tuple[float, float]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── 수집 ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """백그라운드 수집을 시작한다. 두 번 불러도 안전하다."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="beam-direction-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """수집을 멈춘다. 두 번 불러도 안전하다."""
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            self._stop.wait(self._interval_sec)

    def sample_once(self) -> None:
        """한 번 읽어 이력에 넣는다. 실패는 조용히 넘긴다."""
        try:
            degrees = float(self._read_direction_deg())
        except Exception:  # noqa: BLE001 - 방향을 못 읽어도 대화는 계속된다
            logger.debug("소리 방향 표본 읽기 실패", exc_info=True)
            return
        self._append(self._clock(), degrees)

    def _append(self, stamp: float, degrees: float) -> None:
        with self._lock:
            self._samples.append((stamp, degrees))
            cutoff = stamp - self._history_sec
            self._samples = [
                item for item in self._samples if item[0] >= cutoff
            ]

    # ── 조회 ────────────────────────────────────────────────────────────────

    def recent(self, window_sec: float) -> list[float]:
        """최근 window_sec 안에 읽은 각도들을 돌려준다."""
        if window_sec <= 0.0:
            return []
        cutoff = self._clock() - window_sec
        with self._lock:
            return [
                degrees for stamp, degrees in self._samples
                if stamp >= cutoff
            ]
