"""사람 탐지 명령행 옵션의 최소 유효성 검사를 검증한다."""

import argparse

import pytest

from bomi_vision.main import (
    parse_camera_index,
    parse_confidence,
    parse_forward_threshold,
    parse_horizontal_dead_zone,
    parse_lost_tolerance_frames,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", ["0", "2"])
def test_accepts_non_negative_camera_index(value: str) -> None:
    """0 이상의 정수 카메라 인덱스를 허용한다."""
    assert parse_camera_index(value) == int(value)


@pytest.mark.parametrize("value", ["-1", "camera"])
def test_rejects_invalid_camera_index(value: str) -> None:
    """음수이거나 정수가 아닌 카메라 인덱스를 거부한다."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_camera_index(value)


@pytest.mark.parametrize("value", ["0", "0.5", "1"])
def test_accepts_confidence_in_range(value: str) -> None:
    """경곗값을 포함해 0.0 이상 1.0 이하의 신뢰도를 허용한다."""
    assert parse_confidence(value) == float(value)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "high"])
def test_rejects_invalid_confidence(value: str) -> None:
    """숫자가 아니거나 허용 범위 밖인 신뢰도를 거부한다."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_confidence(value)


@pytest.mark.parametrize("value", ["0", "3"])
def test_accepts_non_negative_lost_tolerance(value: str) -> None:
    """0 이상의 누락 허용 프레임 수를 허용한다."""
    assert parse_lost_tolerance_frames(value) == int(value)


@pytest.mark.parametrize("value", ["-1", "short"])
def test_rejects_invalid_lost_tolerance(value: str) -> None:
    """음수이거나 정수가 아닌 누락 허용 프레임 수를 거부한다."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_lost_tolerance_frames(value)


@pytest.mark.parametrize("value", ["0", "0.15", "0.999"])
def test_accepts_horizontal_dead_zone(value: str) -> None:
    """0.0 이상 1.0 미만인 수평 중앙 범위를 허용한다."""
    assert parse_horizontal_dead_zone(value) == float(value)


@pytest.mark.parametrize("value", ["-0.1", "1", "wide"])
def test_rejects_invalid_horizontal_dead_zone(value: str) -> None:
    """범위 밖이거나 숫자가 아닌 수평 중앙 범위를 거부한다."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_horizontal_dead_zone(value)


@pytest.mark.parametrize("value", ["0", "0.45", "1"])
def test_accepts_forward_threshold(value: str) -> None:
    """경곗값을 포함한 유효한 전진 정지 임계값을 허용한다."""
    assert parse_forward_threshold(value) == float(value)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "near"])
def test_rejects_invalid_forward_threshold(value: str) -> None:
    """범위 밖이거나 숫자가 아닌 전진 정지 임계값을 거부한다."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_forward_threshold(value)
