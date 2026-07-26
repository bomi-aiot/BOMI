"""사람 탐지 명령행 옵션의 최소 유효성 검사를 검증한다."""

import argparse

import pytest

from bomi_vision.main import parse_camera_index, parse_confidence

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
