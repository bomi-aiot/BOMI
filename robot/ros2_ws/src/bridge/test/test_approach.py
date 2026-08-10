"""ApproachController(도착 후 사람 접근, CLAUDE.md §3a)의 순수 로직 검증.

threading.Timer 를 가짜로 주입해 실제 시간 없이 만료를 재현한다 —
rclpy·paho 어느 쪽도 필요 없는 순수 스케줄링/게이팅 로직이다.
"""

from __future__ import annotations

import pytest

from bridge import contract
from bridge.approach import ApproachController


class _FakeTimer:
    """threading.Timer 호환 대역. fire() 로 즉시 만료를 재현한다."""

    def __init__(self, interval: float, function) -> None:
        self.interval = interval
        self.function = function
        self.cancelled = False
        self.started = False
        self.daemon = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        """실제 threading.Timer 가 만료됐을 때 하는 일 — function() 호출."""
        if not self.cancelled:
            self.function()


def _make_controller(*, enabled: bool = True, duration_sec: float = 15.0):
    published: list[bool] = []
    timers: list[_FakeTimer] = []

    def factory(interval, function):
        timer = _FakeTimer(interval, function)
        timers.append(timer)
        return timer

    controller = ApproachController(
        published.append,
        duration_sec=duration_sec,
        enabled=enabled,
        timer_factory=factory,
    )
    return controller, published, timers


def test_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError):
        ApproachController(lambda _enable: None, duration_sec=0.0)
    with pytest.raises(ValueError):
        ApproachController(lambda _enable: None, duration_sec=-1.0)


# ── 킬 스위치 ─────────────────────────────────────────────────────────────


def test_disabled_by_default_does_nothing_on_arrival() -> None:
    """★ 기본값이 꺼짐이어야 한다 — V4 실기 전까지의 안전한 기본 상태."""
    controller, published, timers = _make_controller(enabled=False)

    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    assert published == []
    assert timers == []


# ── 목적지 필터 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("target", [contract.TARGET_ENTRANCE, contract.TARGET_DEFAULT])
def test_only_living_room_triggers_approach(target: str) -> None:
    """현관은 문 앞 자체가 목적지, 복귀는 사람에게서 멀어지는 이동이다."""
    controller, published, timers = _make_controller(enabled=True)

    controller.on_arrival(target)

    assert published == []
    assert timers == []


def test_living_room_arrival_enables_and_starts_a_timer() -> None:
    controller, published, timers = _make_controller(enabled=True, duration_sec=15.0)

    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    assert published == [True]
    assert len(timers) == 1
    assert timers[0].interval == 15.0
    assert timers[0].started is True
    assert timers[0].daemon is True


# ── 시간 상한 만료 ────────────────────────────────────────────────────────


def test_timer_expiry_disables_follow() -> None:
    """★ 침묵 고착 방지의 대칭 — 접근도 무기한 켜 두지 않는다."""
    controller, published, timers = _make_controller(enabled=True)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    timers[0].fire()

    assert published == [True, False]


# ── 재도착(연속 NAVIGATE) ────────────────────────────────────────────────


def test_re_arrival_cancels_the_previous_timer() -> None:
    """★ 타이머 둘이 살아 있으면 첫 타이머가 새 접근을 도중에 꺼 버린다."""
    controller, published, timers = _make_controller(enabled=True)

    controller.on_arrival(contract.TARGET_LIVING_ROOM)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    assert len(timers) == 2
    assert timers[0].cancelled is True
    assert timers[1].cancelled is False
    assert published == [True, True]


def test_expired_timer_does_not_fire_after_being_cancelled() -> None:
    controller, published, timers = _make_controller(enabled=True)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)  # 첫 타이머 취소

    timers[0].fire()  # 취소된 타이머 — 아무 일도 없어야 한다

    assert published == [True, True]


# ── stop() ────────────────────────────────────────────────────────────────


def test_stop_cancels_the_timer_and_disables() -> None:
    controller, published, timers = _make_controller(enabled=True)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    controller.stop()

    assert timers[0].cancelled is True
    assert published == [True, False]


def test_stop_is_safe_when_not_approaching() -> None:
    """접근 중이 아니어도 안전하다 — 항상 끄는 발행은 한다(확실한 상태 보장)."""
    controller, published, _timers = _make_controller(enabled=True)

    controller.stop()

    assert published == [False]


def test_stop_is_idempotent() -> None:
    controller, published, timers = _make_controller(enabled=True)
    controller.on_arrival(contract.TARGET_LIVING_ROOM)

    controller.stop()
    controller.stop()

    assert published == [True, False, False]
