"""TimedDriveRobotDriver(Nav2 없이 "2초 직진")의 순수 로직 검증.

시간(monotonic/sleep)과 속도 발행을 주입해 실제 대기 없이 검증한다 —
rclpy 도 하드웨어도 필요 없다. 여기서 지켜야 할 것은 하나다:
**어떤 경로로 끝나든 마지막 발행은 정지(0.0)여야 한다.**
"""

from __future__ import annotations

import pytest

from bridge import contract
from bridge.timed_drive_driver import TimedDriveRobotDriver


class _FakeClock:
    """sleep 한 만큼 시간이 흐르는 가짜 시계."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _make_driver(*, duration_sec: float = 2.0, linear_speed: float = 0.08):
    published: list[float] = []
    clock = _FakeClock()
    driver = TimedDriveRobotDriver(
        published.append,
        duration_sec=duration_sec,
        linear_speed=linear_speed,
        tick_sec=0.1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return driver, published, clock


# ── 설정 검증 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("duration", [0.0, -1.0])
def test_rejects_non_positive_duration(duration: float) -> None:
    with pytest.raises(ValueError):
        TimedDriveRobotDriver(lambda _v: None, duration_sec=duration)


def test_rejects_tick_at_or_above_the_pico_watchdog() -> None:
    """★ tick 이 워치독(300ms)보다 크면 주행이 조용히 잘린다."""
    with pytest.raises(ValueError):
        TimedDriveRobotDriver(lambda _v: None, tick_sec=0.3)
    with pytest.raises(ValueError):
        TimedDriveRobotDriver(lambda _v: None, tick_sec=1.0)


# ── 정상 주행 ─────────────────────────────────────────────────────────────


def test_navigate_drives_forward_then_stops() -> None:
    driver, published, _clock = _make_driver(duration_sec=2.0, linear_speed=0.08)

    status = driver.navigate(contract.TARGET_LIVING_ROOM)

    assert status == contract.STATUS_ARRIVED
    assert published[-1] == 0.0, "마지막 발행은 반드시 정지여야 한다"
    assert set(published[:-1]) == {0.08}


def test_navigate_keeps_republishing_within_the_watchdog() -> None:
    """★ 한 번만 발행하면 Pico 가 300ms 뒤 스스로 멈춘다 — 계속 보내야 한다."""
    driver, published, clock = _make_driver(duration_sec=2.0)

    driver.navigate(contract.TARGET_LIVING_ROOM)

    # 2초 / 0.1초 = 20회 전진 + 정지 1회
    assert len(published) == 21
    assert all(gap <= 0.1 for gap in clock.slept)


def test_navigate_does_not_overshoot_the_duration() -> None:
    """마지막 tick 이 정해진 시간을 넘겨 주행을 늘리지 않는다."""
    driver, _published, clock = _make_driver(duration_sec=0.25)

    driver.navigate(contract.TARGET_LIVING_ROOM)

    assert clock.now == pytest.approx(0.25)


@pytest.mark.parametrize(
    "target",
    [contract.TARGET_ENTRANCE, contract.TARGET_DEFAULT, contract.TARGET_LIVING_ROOM],
)
def test_every_supported_target_drives_the_same(target: str) -> None:
    """목적지 구분이 없다는 사실 자체를 테스트로 못박아 둔다."""
    driver, published, _clock = _make_driver()

    assert driver.navigate(target) == contract.STATUS_ARRIVED
    assert len(published) == 21


# ── 목적지 검증 ───────────────────────────────────────────────────────────


def test_unknown_target_fails_without_moving() -> None:
    """★ 알 수 없는 목적지에 거짓 ARRIVED 를 주면 mock 검증이 무의미해진다."""
    driver, published, _clock = _make_driver()

    status = driver.navigate("KITCHEN")

    assert status == contract.STATUS_FAILED
    assert driver.last_reason_code == contract.REASON_UNKNOWN_TARGET
    assert published == [], "실패한 명령은 바퀴를 돌리지 않아야 한다"


# ── 취소 ──────────────────────────────────────────────────────────────────


def test_cancel_with_no_active_drive_is_a_no_op() -> None:
    """주행 전 CANCEL 은 다음 명령을 막지 않는다 — Nav2 드라이버와 같은 의미다.

    (Nav2 쪽도 진행 중 목표가 없으면 취소가 무동작이다.) 대가로 "NAVIGATE 를
    워커가 집어 들기 직전에 도착한 CANCEL"은 유실되는 창이 있다 —
    timed_drive_driver 의 cancel() docstring 에 명시돼 있다.
    """
    driver, published, _clock = _make_driver()

    assert driver.cancel() == contract.STATUS_CANCELLED
    assert published == []

    assert driver.navigate(contract.TARGET_LIVING_ROOM) == contract.STATUS_ARRIVED


def test_cancel_midway_stops_and_reports_cancelled() -> None:
    """수신 스레드의 cancel() 을 주행 도중에 재현한다."""
    published: list[float] = []
    clock = _FakeClock()
    driver = TimedDriveRobotDriver(
        published.append,
        duration_sec=2.0,
        tick_sec=0.1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    def sleep_then_cancel(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.now >= 0.5:
            driver.cancel()

    driver._sleep = sleep_then_cancel  # 주행 중 취소 주입

    status = driver.navigate(contract.TARGET_LIVING_ROOM)

    assert status == contract.STATUS_CANCELLED
    assert published[-1] == 0.0
    assert clock.now == pytest.approx(0.5)


def test_a_previous_cancel_does_not_leak_into_the_next_command() -> None:
    """★ 취소 상태가 남아 있으면 다음 NAVIGATE 가 즉시 취소로 끝난다."""
    driver, published, _clock = _make_driver()
    driver.cancel()
    driver.navigate(contract.TARGET_LIVING_ROOM)  # 취소로 끝남

    published.clear()
    status = driver.navigate(contract.TARGET_ENTRANCE)

    assert status == contract.STATUS_ARRIVED
    assert len(published) == 21


# ── 예외·종료 ─────────────────────────────────────────────────────────────


def test_stop_is_published_even_when_publishing_fails_midway() -> None:
    """★ 예외로 빠져나가도 정지는 나가야 한다 — 안 그러면 계속 굴러간다."""
    calls: list[float] = []

    def flaky_publish(velocity: float) -> None:
        calls.append(velocity)
        if len(calls) == 3:
            raise RuntimeError("publisher died")

    driver = TimedDriveRobotDriver(flaky_publish, duration_sec=2.0, tick_sec=0.1)
    status = driver.navigate(contract.TARGET_LIVING_ROOM)

    assert status == contract.STATUS_FAILED
    assert driver.last_reason_code == contract.REASON_INTERNAL_ERROR
    assert calls[-1] == 0.0


def test_shutdown_publishes_stop() -> None:
    driver, published, _clock = _make_driver()

    driver.shutdown()

    assert published == [0.0]


def test_shutdown_survives_a_dead_publisher() -> None:
    """종료 경로에서 예외가 새어 나가면 노드 정리가 멈춘다."""

    def dead_publish(_velocity: float) -> None:
        raise RuntimeError("publisher already destroyed")

    driver = TimedDriveRobotDriver(dead_publish)

    driver.shutdown()  # 예외가 밖으로 나오지 않아야 한다


# ── speak ─────────────────────────────────────────────────────────────────


def test_speak_is_not_supported() -> None:
    """가짜 성공을 돌려주지 않는다(백엔드는 SPEAK 를 발행하지도 않는다)."""
    driver, _published, _clock = _make_driver()

    assert driver.speak("안녕하세요") == contract.STATUS_FAILED
    assert driver.last_reason_code == contract.REASON_INTERNAL_ERROR
