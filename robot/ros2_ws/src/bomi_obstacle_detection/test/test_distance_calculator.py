"""LiDAR 전방 거리 계산 기능을 검증한다."""

import math

import pytest
from sensor_msgs.msg import LaserScan

from bomi_obstacle_detection.distance_calculator import (
    calculate_front_distance,
)


def create_test_scan(ranges: list[float]) -> LaserScan:
    """
    테스트용 LaserScan 메시지를 생성한다.

    입력:
        ranges: -60도부터 30도 간격으로 배치할 거리값 목록

    출력:
        테스트에 사용할 LaserScan 메시지를 반환한다.

    주의사항:
        다섯 개의 값을 전달하면 각도는 각각
        -60, -30, 0, 30, 60도가 된다.
    """
    scan = LaserScan()
    scan.angle_min = math.radians(-60.0)
    scan.angle_increment = math.radians(30.0)
    scan.range_min = 0.12
    scan.range_max = 10.0
    scan.ranges = ranges

    return scan


def test_returns_nearest_front_distance() -> None:
    """전방 범위에서 가장 가까운 거리값을 반환하는지 확인한다."""
    scan = create_test_scan(
        [
            0.2,
            0.8,
            0.5,
            0.7,
            0.3,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert result == pytest.approx(0.5)


def test_ignores_invalid_distance_values() -> None:
    """0, NaN, inf와 측정 범위 밖의 값을 제외하는지 확인한다."""
    scan = create_test_scan(
        [
            2.0,
            0.0,
            math.inf,
            0.4,
            2.0,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert result == pytest.approx(0.4)


def test_ignores_objects_outside_front_angle() -> None:
    """전방 범위 밖의 가까운 물체를 제외하는지 확인한다."""
    scan = create_test_scan(
        [
            0.2,
            0.9,
            0.8,
            1.0,
            0.3,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert result == pytest.approx(0.8)


def test_ignores_values_below_sensor_minimum() -> None:
    """센서 최소 측정거리보다 작은 값을 제외하는지 확인한다."""
    scan = create_test_scan(
        [
            2.0,
            0.05,
            0.6,
            0.7,
            2.0,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert result == pytest.approx(0.6)


def test_ignores_values_above_sensor_maximum() -> None:
    """센서 최대 측정거리보다 큰 값을 제외하는지 확인한다."""
    scan = create_test_scan(
        [
            2.0,
            11.0,
            0.6,
            0.7,
            2.0,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert result == pytest.approx(0.6)


def test_returns_nan_when_no_valid_distance_exists() -> None:
    """전방에 유효한 값이 없으면 NaN을 반환하는지 확인한다."""
    scan = create_test_scan(
        [
            2.0,
            0.0,
            math.nan,
            math.inf,
            2.0,
        ]
    )

    result = calculate_front_distance(
        scan=scan,
        front_angle_min_deg=-30.0,
        front_angle_max_deg=30.0,
    )

    assert math.isnan(result)


def test_rejects_invalid_angle_range() -> None:
    """최소 각도가 최대 각도보다 크면 오류가 발생하는지 확인한다."""
    scan = create_test_scan(
        [
            2.0,
            0.8,
            0.5,
            0.7,
            2.0,
        ]
    )

    with pytest.raises(ValueError):
        calculate_front_distance(
            scan=scan,
            front_angle_min_deg=30.0,
            front_angle_max_deg=-30.0,
        )
