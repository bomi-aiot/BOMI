"""Pico 시리얼 프로토콜 순수 로직을 검증한다."""

import math

import pytest

from core.pico_protocol import (
    LineKind,
    classify_line,
    flip_yaw_sign,
    format_velocity_command,
    parse_telemetry_line,
    twist_to_wheel_targets,
)


def test_classify_line_recognizes_telemetry() -> None:
    """T로 시작하는 줄은 텔레메트리로 분류한다."""
    line = (
        "T 128450 0.518 0.515 0.518 0.521 "
        "1937 1948 1935 1921 34.2 31.8 "
        "-1.24 -0.35 0.42 0x03"
    )

    assert classify_line(line) == LineKind.TELEMETRY


def test_classify_line_recognizes_ack_err_warn() -> None:
    """ACK, ERR, WARN으로 시작하는 줄을 각각 구분한다."""
    assert classify_line("ACK V 0.500 0.500 for 0.3s") == LineKind.ACK
    assert classify_line("ERR watchdog") == LineKind.ERR
    assert classify_line("WARN step timeout, moving on") == LineKind.WARN


def test_classify_line_recognizes_comment() -> None:
    """#으로 시작하는 줄은 사람이 읽는 글로 분류한다."""
    assert classify_line("# BOMI closed loop speed controller") == (
        LineKind.COMMENT
    )


def test_classify_line_recognizes_violation() -> None:
    """정해진 첫 낱말이 아니면 규칙 위반으로 분류한다."""
    assert classify_line("garbage output") == LineKind.VIOLATION


def test_parse_telemetry_line_matches_spec_example() -> None:
    """스펙 문서의 예시 줄을 정확히 파싱한다."""
    line = (
        "T 128450 0.518 0.515 0.518 0.521 "
        "1937 1948 1935 1921 34.2 31.8 "
        "-1.24 -0.35 0.42 0x03"
    )

    frame = parse_telemetry_line(line)

    assert frame.elapsed_ms == 128450
    assert frame.left_target_rev_s == pytest.approx(0.518)
    assert frame.left_actual_rev_s == pytest.approx(0.515)
    assert frame.right_target_rev_s == pytest.approx(0.518)
    assert frame.right_actual_rev_s == pytest.approx(0.521)
    assert frame.left_front_count == 1937
    assert frame.left_rear_count == 1948
    assert frame.right_front_count == 1935
    assert frame.right_rear_count == 1921
    assert frame.left_pwm_percent == pytest.approx(34.2)
    assert frame.right_pwm_percent == pytest.approx(31.8)
    assert frame.yaw_deg == pytest.approx(-1.24)
    assert frame.gyro_rate_dps == pytest.approx(-0.35)
    assert frame.distance_m == pytest.approx(0.42)
    assert frame.flags == 0x03
    assert frame.is_driving is True
    assert frame.is_imu_ok is True
    assert frame.is_watchdog_stopped is False
    assert frame.is_fifo_overflowed is False
    assert frame.is_outlier_rejected is False


def test_parse_telemetry_line_negative_counts() -> None:
    """엔코더 카운트는 부호 있는 정수로 파싱한다."""
    line = (
        "T 0 0.0 0.0 0.0 0.0 "
        "-5 -3 -5 -3 0.0 0.0 "
        "0.0 0.0 0.0 0x00"
    )

    frame = parse_telemetry_line(line)

    assert frame.left_front_count == -5
    assert frame.right_rear_count == -3


def test_parse_telemetry_line_rejects_wrong_word_count() -> None:
    """낱말 개수가 16개가 아니면 ValueError를 낸다."""
    with pytest.raises(ValueError):
        parse_telemetry_line("T 1 2 3")


def test_parse_telemetry_line_rejects_non_numeric_field() -> None:
    """숫자로 바꿀 수 없는 필드가 있으면 ValueError를 낸다."""
    line = (
        "T oops 0.0 0.0 0.0 0.0 "
        "0 0 0 0 0.0 0.0 "
        "0.0 0.0 0.0 0x00"
    )

    with pytest.raises(ValueError):
        parse_telemetry_line(line)


def test_parse_telemetry_line_all_flag_bits() -> None:
    """flags의 5개 비트를 모두 개별적으로 읽는다."""
    line = (
        "T 0 0.0 0.0 0.0 0.0 "
        "0 0 0 0 0.0 0.0 "
        "0.0 0.0 0.0 0x1f"
    )

    frame = parse_telemetry_line(line)

    assert frame.is_driving is True
    assert frame.is_imu_ok is True
    assert frame.is_watchdog_stopped is True
    assert frame.is_fifo_overflowed is True
    assert frame.is_outlier_rejected is True


def test_twist_to_wheel_targets_straight_forward() -> None:
    """각속도가 0이면 좌우 목표가 같다."""
    targets = twist_to_wheel_targets(
        linear_x=0.1,
        angular_z=0.0,
        track_width_m=0.257,
        distance_per_rev_m=0.1929,
    )

    expected = 0.1 / 0.1929

    assert targets.left_rev_s == pytest.approx(expected)
    assert targets.right_rev_s == pytest.approx(expected)
    assert targets.clamped is False


def test_twist_to_wheel_targets_in_place_rotation() -> None:
    """linear.x가 0이고 angular.z가 있으면 좌우 부호가 반대다."""
    targets = twist_to_wheel_targets(
        linear_x=0.0,
        angular_z=0.5,
        track_width_m=0.257,
        distance_per_rev_m=0.1929,
    )

    assert targets.left_rev_s == pytest.approx(-targets.right_rev_s)
    assert targets.right_rev_s > 0.0


def test_twist_to_wheel_targets_zero_is_zero() -> None:
    """선속도와 각속도가 모두 0이면 좌우 목표도 0이다."""
    targets = twist_to_wheel_targets(
        linear_x=0.0,
        angular_z=0.0,
        track_width_m=0.257,
        distance_per_rev_m=0.1929,
    )

    assert targets.left_rev_s == 0.0
    assert targets.right_rev_s == 0.0
    assert targets.clamped is False


def test_twist_to_wheel_targets_clamps_and_reports_it() -> None:
    """최대 목표를 넘으면 줄여 맞추고 clamped를 True로 보고한다."""
    targets = twist_to_wheel_targets(
        linear_x=10.0,
        angular_z=0.0,
        track_width_m=0.257,
        distance_per_rev_m=0.1929,
        max_target_rev_s=0.8,
    )

    assert targets.left_rev_s == pytest.approx(0.8)
    assert targets.right_rev_s == pytest.approx(0.8)
    assert targets.clamped is True


def test_twist_to_wheel_targets_keeps_curvature_when_clamped() -> None:
    """한계를 넘어도 좌우 비율을 지켜 곡률(v/w)이 변하지 않는다.

    좌우를 각각 잘라내면 바깥 바퀴만 한계에 붙고 안쪽은 살아남아 회전이
    명령보다 얕아진다. 그만큼 로봇이 계획 경로 바깥으로 빗겨 나갔다.
    """
    track_width_m = 0.278
    distance_per_rev_m = 0.1929
    linear_x = 0.15
    angular_z = 0.5

    targets = twist_to_wheel_targets(
        linear_x=linear_x,
        angular_z=angular_z,
        track_width_m=track_width_m,
        distance_per_rev_m=distance_per_rev_m,
        max_target_rev_s=0.8,
    )

    left_m_s = targets.left_rev_s * distance_per_rev_m
    right_m_s = targets.right_rev_s * distance_per_rev_m
    actual_linear = (left_m_s + right_m_s) / 2.0
    actual_angular = (right_m_s - left_m_s) / track_width_m

    assert targets.clamped is True
    assert max(abs(targets.left_rev_s), abs(targets.right_rev_s)) == (
        pytest.approx(0.8)
    )
    assert actual_linear / actual_angular == pytest.approx(
        linear_x / angular_z
    )


def test_twist_to_wheel_targets_scales_in_place_rotation_symmetrically() -> None:
    """제자리 회전이 한계를 넘어도 좌우 대칭이 깨지지 않는다."""
    targets = twist_to_wheel_targets(
        linear_x=0.0,
        angular_z=5.0,
        track_width_m=0.278,
        distance_per_rev_m=0.1929,
        max_target_rev_s=0.8,
    )

    assert targets.clamped is True
    assert targets.right_rev_s == pytest.approx(0.8)
    assert targets.left_rev_s == pytest.approx(-0.8)


def test_twist_to_wheel_targets_rejects_non_finite_input() -> None:
    """NaN이나 무한대 입력은 거부한다."""
    with pytest.raises(ValueError):
        twist_to_wheel_targets(
            linear_x=math.nan,
            angular_z=0.0,
            track_width_m=0.257,
            distance_per_rev_m=0.1929,
        )

    with pytest.raises(ValueError):
        twist_to_wheel_targets(
            linear_x=math.inf,
            angular_z=0.0,
            track_width_m=0.257,
            distance_per_rev_m=0.1929,
        )


def test_twist_to_wheel_targets_rejects_bad_geometry() -> None:
    """트레드나 바퀴 회전 거리가 0 이하면 거부한다."""
    with pytest.raises(ValueError):
        twist_to_wheel_targets(
            linear_x=0.1,
            angular_z=0.0,
            track_width_m=0.0,
            distance_per_rev_m=0.1929,
        )

    with pytest.raises(ValueError):
        twist_to_wheel_targets(
            linear_x=0.1,
            angular_z=0.0,
            track_width_m=0.257,
            distance_per_rev_m=-0.1,
        )


def test_format_velocity_command() -> None:
    """V 명령 문자열이 스펙 형식과 일치한다."""
    from core.pico_protocol import WheelTargets

    targets = WheelTargets(
        left_rev_s=0.518,
        right_rev_s=-0.3,
        clamped=False,
    )

    assert format_velocity_command(targets) == "V 0.518 -0.300"


def test_flip_yaw_sign() -> None:
    """Pico의 오른쪽 회전 양수를 ROS2 반시계 양수로 뒤집는다."""
    assert flip_yaw_sign(10.0) == -10.0
    assert flip_yaw_sign(-5.0) == 5.0
    assert flip_yaw_sign(0.0) == 0.0
