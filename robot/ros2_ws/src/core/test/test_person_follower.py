"""사람 추종 ROS2 노드의 입력 파싱과 LiDAR 계산을 검증한다."""

import math

import pytest
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool

from core.follow_state_machine import FollowStateMachine
from core.person_follower import PersonFollower


def make_scan(
    ranges: list[float],
    angle_min: float = -0.2,
    angle_increment: float = 0.1,
) -> LaserScan:
    """테스트용 LaserScan 메시지를 생성한다."""
    message = LaserScan()
    message.angle_min = angle_min
    message.angle_increment = angle_increment
    message.range_min = 0.12
    message.range_max = 10.0
    message.ranges = ranges

    return message


def test_all_infinite_front_ranges_are_valid_clear_space() -> None:
    """전방이 모두 inf이면 장애물이 없는 정상 데이터로 처리한다."""
    message = make_scan(
        [
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
        ]
    )

    valid, distance = PersonFollower._minimum_front_distance(
        message,
        math.radians(20.0),
    )

    assert valid is True
    assert distance is None


def test_minimum_front_distance_returns_closest_obstacle() -> None:
    """전방 범위 안에서 가장 가까운 장애물을 반환한다."""
    message = make_scan(
        [
            2.0,
            1.2,
            0.4,
            0.8,
            3.0,
        ]
    )

    valid, distance = PersonFollower._minimum_front_distance(
        message,
        math.radians(20.0),
    )

    assert valid is True
    assert distance == pytest.approx(0.4)


def test_obstacle_outside_front_angle_is_ignored() -> None:
    """전방 검사 범위 밖의 가까운 장애물을 무시한다."""
    message = make_scan(
        ranges=[
            0.2,
            1.0,
            1.5,
            2.0,
            2.5,
        ],
        angle_min=-math.pi / 2.0,
        angle_increment=math.pi / 4.0,
    )

    valid, distance = PersonFollower._minimum_front_distance(
        message,
        math.radians(20.0),
    )

    assert valid is True
    assert distance == pytest.approx(1.5)


def test_person_and_obstacle_check_ranges_are_separated() -> None:
    """긴급 장애물 범위와 중앙 사람 거리 범위를 구분한다."""
    message = make_scan(
        ranges=[
            0.4,
            2.0,
            1.2,
            2.5,
            0.6,
        ],
        angle_min=-0.3,
        angle_increment=0.15,
    )

    obstacle_valid, obstacle_distance = (
        PersonFollower._minimum_front_distance(
            message,
            math.radians(20.0),
        )
    )

    person_valid, person_distance = (
        PersonFollower._minimum_front_distance(
            message,
            math.radians(8.0),
        )
    )

    assert obstacle_valid is True
    assert obstacle_distance == pytest.approx(0.4)

    assert person_valid is True
    assert person_distance == pytest.approx(1.2)


def test_nan_only_front_scan_is_invalid() -> None:
    """전방 측정값이 모두 NaN이면 유효하지 않게 처리한다."""
    message = make_scan(
        [
            math.nan,
            math.nan,
            math.nan,
            math.nan,
            math.nan,
        ]
    )

    valid, distance = PersonFollower._minimum_front_distance(
        message,
        math.radians(20.0),
    )

    assert valid is False
    assert distance is None


def test_empty_scan_is_invalid() -> None:
    """거리 측정값이 없는 스캔은 유효하지 않게 처리한다."""
    message = make_scan([])

    valid, distance = PersonFollower._minimum_front_distance(
        message,
        math.radians(20.0),
    )

    assert valid is False
    assert distance is None


def test_parse_valid_vision_message() -> None:
    """정상 JSON 결과를 표준 구조로 변환한다."""
    result = PersonFollower._parse_vision_message(
        '{"status":"TRACKING",'
        '"command":"MOVE_FORWARD",'
        '"track_id":7}'
    )

    assert result == {
        "status": "tracking",
        "command": "move_forward",
        "track_id": 7,
    }


def test_parse_invalid_json_raises_value_error() -> None:
    """올바르지 않은 JSON 입력은 예외 처리한다."""
    with pytest.raises(ValueError):
        PersonFollower._parse_vision_message(
            '{"status":"tracking"'
        )


def test_boolean_track_id_is_rejected() -> None:
    """Boolean 값은 정수 Track ID로 허용하지 않는다."""
    with pytest.raises(ValueError):
        PersonFollower._parse_vision_message(
            '{"status":"tracking",'
            '"command":"move_forward",'
            '"track_id":true}'
        )


def test_negative_track_id_is_rejected() -> None:
    """음수 Track ID는 허용하지 않는다."""
    with pytest.raises(ValueError):
        PersonFollower._parse_vision_message(
            '{"status":"tracking",'
            '"command":"move_forward",'
            '"track_id":-1}'
        )


def test_scan_callback_ignores_scan_when_lidar_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lidar 비활성화 시 수신된 스캔을 완전히 무시한다."""
    follower = object.__new__(PersonFollower)
    follower._use_lidar = False

    def fail_get_clock(_self: PersonFollower) -> None:
        raise AssertionError(
            "LiDAR 비활성화 상태에서 스캔을 처리했습니다."
        )

    monkeypatch.setattr(
        PersonFollower,
        "get_clock",
        fail_get_clock,
    )

    follower._scan_callback(
        make_scan([0.2])
    )


# ── 추종 스위치 (S15P11E102 통합 스프린트 2-5, "도착 후 사람 접근") ──────────
#
# object.__new__(PersonFollower) 로 Node.__init__ (rclpy 컨텍스트 필요)을
# 건너뛰고, 이 스위치가 실제로 쓰는 속성만 직접 채운다. 위
# test_scan_callback_ignores_scan_when_lidar_disabled 과 같은 패턴이다.


class _FakeClock:
    """get_clock().now() 를 고정 시각으로 흉내 낸다."""

    def __init__(self, sec: float) -> None:
        self._time = Time(nanoseconds=int(sec * 1_000_000_000))

    def now(self) -> Time:
        return self._time


class _RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[float, float]] = []

    def publish(self, twist) -> None:
        self.published.append((twist.linear.x, twist.angular.z))


class _FakeLogger:
    """get_logger().info/warning/debug 를 조용히 삼킨다."""

    def info(self, _message: str) -> None:
        pass

    def warning(self, _message: str) -> None:
        pass

    def debug(self, _message: str) -> None:
        pass


def _make_follower(*, enabled: bool, clock_sec: float = 100.0) -> PersonFollower:
    follower = object.__new__(PersonFollower)
    follower._enabled = enabled
    follower._state_machine = FollowStateMachine()
    if not enabled:
        follower._state_machine.disable(clock_sec)
    follower._velocity_publisher = _RecordingPublisher()
    follower._last_velocity = None
    follower._last_logged_state = None
    follower._vision_timeout_handled = True
    follower._lidar_timeout_stop_sent = True
    follower.get_clock = lambda: _FakeClock(clock_sec)  # type: ignore[method-assign]
    follower.get_logger = lambda: _FakeLogger()  # type: ignore[method-assign]
    return follower


def test_publish_velocity_is_a_noop_when_disabled() -> None:
    """★ 끄면 속도 발행 자체가 나가지 않는다.

    /cmd_vel 로 직결된 접근 대본에서, 꺼진 채로도 매 프레임 정지가 나가면
    그게 곧 '항상 0'인 Nav2 방해 신호다. 발행 자체를 막아야 한다.
    """
    from core.person_following_controller import VelocityCommand

    follower = _make_follower(enabled=False)

    follower._publish_velocity(
        VelocityCommand(linear_x=0.2, angular_z=0.0, reason="test")
    )

    assert follower._velocity_publisher.published == []


def test_publish_velocity_publishes_when_enabled() -> None:
    from core.person_following_controller import VelocityCommand

    follower = _make_follower(enabled=True)

    follower._publish_velocity(
        VelocityCommand(linear_x=0.2, angular_z=0.1, reason="test")
    )

    assert follower._velocity_publisher.published == [(0.2, 0.1)]


def test_enable_callback_turns_on_and_state_machine_leaves_disabled() -> None:
    follower = _make_follower(enabled=False)
    assert follower._state_machine.state.value == "disabled"

    follower._enable_callback(Bool(data=True))

    assert follower._enabled is True
    assert follower._state_machine.state.value == "waiting_target"


def test_enable_callback_turns_off_and_publishes_a_final_stop_first() -> None:
    """★ 순서가 핵심: 정지 발행이 스위치를 내리기 '전'에 나가야 한다.

    _publish_velocity 의 초크포인트는 self._enabled 를 본다. 스위치를
    먼저 내리면 이 마지막 정지 자체가 삼켜져 로봇이 마지막 속도로
    멈추지 않고 계속 움직일 수 있다.
    """
    follower = _make_follower(enabled=True)

    follower._enable_callback(Bool(data=False))

    assert follower._enabled is False
    assert follower._velocity_publisher.published == [(0.0, 0.0)]
    assert follower._state_machine.state.value == "disabled"


def test_enable_callback_is_idempotent_for_the_same_value() -> None:
    """같은 값이 다시 오면 아무 일도 하지 않는다 — 재발행에 로그가 쌓이지 않는다."""
    follower = _make_follower(enabled=True)

    follower._enable_callback(Bool(data=True))

    assert follower._velocity_publisher.published == []


def test_vision_callback_does_not_move_while_disabled() -> None:
    """꺼진 상태에서 TRACKING 비전 신호가 와도 움직이지 않는다."""
    from core.person_following_controller import PersonFollowingController

    follower = _make_follower(enabled=False)
    follower._controller = PersonFollowingController()
    follower._use_lidar = False

    follower._vision_callback(
        _StringMessage(
            '{"status":"tracking","command":"move_forward","track_id":1}'
        )
    )

    assert follower._velocity_publisher.published == []


class _StringMessage:
    """std_msgs/String 의 .data 속성만 흉내 낸다."""

    def __init__(self, data: str) -> None:
        self.data = data
