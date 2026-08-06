"""도착 후 사람 접근 제어기 — LIVING_ROOM 도착 시 추종을 잠깐 켠다.

왜 존재하는가 (CLAUDE.md §3a, 보미야 호출 대본)
    "보미야"를 부르면 로봇은 거실 고정 좌표(waypoint)까지는 Nav2 로 온다.
    그러나 어르신은 좌표가 아니라 '사람'이다 — 마지막 몇 걸음을 좁히는 것이
    이 제어기다. Nav2 목표가 끝난 뒤 person_follower(사람 추종, LiDAR 안전
    내장)를 **짧게** 켜서 어르신 앞 약 0.5m(person_stop_distance_m)까지
    다가가고, 시간 상한이 지나면 무조건 끈다.

왜 시간 상한인가
    추종은 "어디서 멈출지"를 사람과의 거리로 정하지만, "언제 포기할지"는
    모른다. 시야에 사람이 없으면(먼 방, 가림) 추종 상태기계가 움직임을
    허용하지 않아 로봇은 제자리에 있지만, 그 상태로 영원히 켜 두면 시연
    도중 지나가는 다른 사람을 따라가기 시작할 수 있다. 상한(기본 15초)이
    이 기능의 최대 피해 반경이다.

킬 스위치 (enabled=False 가 기본)
    이 기능은 시연 대본의 마지막 구간이고, V4 실기에서 처음 실측된다.
    불안정하면 bridge 파라미터 하나(approach_enabled)로 꺼서 "거실 좌표
    도착"까지의 검증된 동작으로 폴백한다 — CLAUDE.md §5 가 요구하는 그
    킬 스위치다.

스레드 모델
    on_arrival 은 브릿지 워커 스레드에서 불린다(MqttBridge._handle_navigate
    직후). enable_publish 콜백은 rclpy 퍼블리셔의 publish 를 감싼 람다인데,
    rclpy 발행은 스레드 안전하다. 끄는 쪽은 threading.Timer 스레드에서
    불린다 — 같은 콜백을 쓰므로 마찬가지다. _lock 은 타이머 교체(재도착 시
    이전 타이머 취소)만 보호한다.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from bridge import contract

logger = logging.getLogger(__name__)

# 접근 단계 기본 시간 상한(초). 시연 대본(어르신 소파 착석, 거실 waypoint 는
# 소파 앞)에서 마지막 몇 걸음이면 충분한 값이다.
#   올리면 -> 먼 위치의 사람에게도 도달할 수 있다. 대신 오추종의 최대 피해
#             반경도 같이 커진다.
#   내리면 -> 안전하지만, 접근이 끝나기 전에 멈춰 어중간한 거리에서 대화가
#             시작될 수 있다.
DEFAULT_APPROACH_DURATION_SEC = 15.0


class ApproachController:
    """LIVING_ROOM 도착 시 사람 추종을 켜고, 시간 상한 뒤 끈다.

    입력값(생성자)
        enable_publish: bool 하나를 받아 추종 노드에 전달하는 콜백.
            운영에서는 /person_following/enable(std_msgs/Bool) 발행이고,
            테스트에서는 리스트 수집기다.
        duration_sec: 접근 단계 시간 상한.
        enabled: 킬 스위치. False 면 on_arrival 이 아무 일도 하지 않는다.
        timer_factory: threading.Timer 호환 팩터리. 테스트가 가짜 타이머를
            주입해 시간 없이 만료를 재현한다.
    """

    def __init__(
        self,
        enable_publish: Callable[[bool], None],
        *,
        duration_sec: float = DEFAULT_APPROACH_DURATION_SEC,
        enabled: bool = False,
        timer_factory: Callable[..., threading.Timer] = threading.Timer,
    ) -> None:
        if duration_sec <= 0:
            raise ValueError("duration_sec must be positive")
        self._enable_publish = enable_publish
        self._duration_sec = duration_sec
        self._enabled = enabled
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_arrival(self, target: str) -> None:
        """MqttBridge 의 도착 훅. LIVING_ROOM 이 아니면 아무 일도 하지 않는다.

        ENTRANCE(현관 인사)와 DEFAULT(복귀)에서는 접근하지 않는 이유:
        현관 대본은 문 앞 고정 위치가 목적지 그 자체이고, 복귀는 사람에게서
        '멀어지는' 이동이다. 사람 접근이 의미 있는 곳은 거실 대본뿐이다.
        """
        if not self._enabled:
            return
        if target != contract.TARGET_LIVING_ROOM:
            return

        with self._lock:
            # 접근 중 재도착(연속 NAVIGATE)이면 이전 타이머를 버리고 다시
            # 시작한다 — 타이머 둘이 살아 있으면 첫 타이머가 새 접근을
            # 도중에 꺼 버린다.
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._timer_factory(
                self._duration_sec, self._expire)
            self._timer.daemon = True

            logger.info(
                "approach phase started (duration=%.0fs)", self._duration_sec)
            self._enable_publish(True)
            self._timer.start()

    def stop(self) -> None:
        """접근을 즉시 끝낸다(종료 정리·CANCEL 대응).

        idempotent — 접근 중이 아니어도 안전하다. 끄는 발행은 항상 한다:
        추종 노드 쪽 상태를 모르는 채 '아마 꺼져 있겠지'로 두는 것보다
        확실히 꺼진 상태를 만드는 편이 안전하다.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._enable_publish(False)

    def _expire(self) -> None:
        with self._lock:
            self._timer = None
        logger.info("approach phase time limit reached; disabling follow")
        self._enable_publish(False)
