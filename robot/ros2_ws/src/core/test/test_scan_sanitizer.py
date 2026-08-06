"""손상된 LaserScan을 걸러내는 판정 로직을 검증한다."""

import math

import pytest

from core.scan_sanitizer import REASON_INTERVAL, REASON_SPAN, ScanGate


# 실측값: 정상 스캔은 430점, 점당 0.8392°로 정확히 360.0°를 덮는다.
NORMAL_POINTS = 430
NORMAL_INCREMENT = math.radians(0.8392)

# 모터가 돌 때 섞여 나오는 스캔은 480점이라 402°를 덮는다.
BROKEN_POINTS = 480


def make_gate(minimum_interval_sec: float = 0.07) -> ScanGate:
    """기본 기준으로 판정기를 만든다."""
    return ScanGate(
        span_tolerance_rad=math.radians(5.0),
        minimum_interval_sec=minimum_interval_sec,
    )


def test_normal_scan_passes():
    """한 바퀴를 덮는 정상 스캔은 통과한다."""
    gate = make_gate()

    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.0) is None


def test_over_full_turn_scan_is_dropped():
    """각도 범위가 360°를 넘는 스캔은 버린다."""
    gate = make_gate()

    assert (
        gate.judge(BROKEN_POINTS, NORMAL_INCREMENT, 100.0) == REASON_SPAN
    )


def test_partial_turn_scan_is_dropped():
    """한 바퀴를 채우지 못한 스캔도 버린다."""
    gate = make_gate()

    assert gate.judge(200, NORMAL_INCREMENT, 100.0) == REASON_SPAN


def test_ten_hertz_sequence_all_passes():
    """정상 10Hz 연속 스캔은 간격 기준에 걸리지 않는다."""
    gate = make_gate()

    for step in range(20):
        stamp = 100.0 + step * 0.1
        assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, stamp) is None


def test_too_close_scan_is_dropped():
    """직전 통과 스캔과 너무 붙어 오면 버린다."""
    gate = make_gate()

    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.0) is None
    assert (
        gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.02)
        == REASON_INTERVAL
    )
    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.1) is None


def test_dropped_scan_does_not_move_interval_reference():
    """
    버린 스캔은 간격 기준을 옮기지 않는다.

    고장 구간에서는 버린 스캔 직후에 성한 스캔이 온다. 버린 것까지
    기준으로 삼으면 성한 스캔이 연달아 버려진다.
    """
    gate = make_gate()

    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.0) is None
    assert (
        gate.judge(BROKEN_POINTS, NORMAL_INCREMENT, 100.05) == REASON_SPAN
    )
    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.1) is None


def test_interval_check_can_be_disabled():
    """간격 기준을 0으로 두면 각도 범위만 본다."""
    gate = make_gate(minimum_interval_sec=0.0)

    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.0) is None
    assert gate.judge(NORMAL_POINTS, NORMAL_INCREMENT, 100.0) is None


def test_generous_tolerance_passes_everything():
    """허용 오차를 크게 주면 위생 노드를 사실상 끌 수 있다."""
    gate = ScanGate(
        span_tolerance_rad=math.radians(360.0),
        minimum_interval_sec=0.0,
    )

    assert gate.judge(BROKEN_POINTS, NORMAL_INCREMENT, 100.0) is None


def test_rejects_invalid_settings():
    """설정값의 허용 범위를 시작 시 검사한다."""
    with pytest.raises(ValueError):
        ScanGate(span_tolerance_rad=0.0, minimum_interval_sec=0.07)

    with pytest.raises(ValueError):
        ScanGate(span_tolerance_rad=0.09, minimum_interval_sec=-0.1)
