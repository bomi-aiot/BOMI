"""사람 추종 ROS2 노드의 입력 파싱과 LiDAR 계산을 검증한다."""

import math

import pytest
from sensor_msgs.msg import LaserScan

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
