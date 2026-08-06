"""외부 모델과 카메라 없이 화면 기준 사용자 위치 계산을 검증한다."""

from dataclasses import replace

import pytest

from bomi_vision.domain import PersonDetection, VisionResultStatus
from bomi_vision.position import calculate_vision_position

pytestmark = pytest.mark.unit

FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def detection(
    *,
    confidence: float = 0.9,
    x1: float = 270.0,
    y1: float = 140.0,
    x2: float = 370.0,
    y2: float = 340.0,
) -> PersonDetection:
    """위치 계산 테스트용 사람 탐지 결과를 생성한다."""
    return PersonDetection(confidence, x1, y1, x2, y2)


def test_centered_person_has_zero_offsets() -> None:
    """화면 중앙에 있는 사람의 수평·수직 오프셋은 0에 가깝다."""
    result = calculate_vision_position(
        [detection()],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.offset_x == pytest.approx(0.0)
    assert result.position.offset_y == pytest.approx(0.0)


def test_camera_left_person_has_negative_horizontal_offset() -> None:
    """원본 카메라 프레임 기준 실제 왼쪽 사람은 음수 오프셋을 갖는다."""
    result = calculate_vision_position(
        [detection(x1=20.0, x2=120.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.offset_x < 0.0


def test_camera_right_person_has_positive_horizontal_offset() -> None:
    """원본 카메라 프레임 기준 실제 오른쪽 사람은 양수 오프셋을 갖는다."""
    result = calculate_vision_position(
        [detection(x1=520.0, x2=620.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.offset_x > 0.0


def test_upper_person_has_negative_vertical_offset() -> None:
    """화면 위쪽 사람의 수직 오프셋은 음수다."""
    result = calculate_vision_position(
        [detection(y1=20.0, y2=120.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.offset_y < 0.0


def test_lower_person_has_positive_vertical_offset() -> None:
    """화면 아래쪽 사람의 수직 오프셋은 양수다."""
    result = calculate_vision_position(
        [detection(y1=360.0, y2=460.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.offset_y > 0.0


def test_calculates_center_and_height_ratio() -> None:
    """박스 중심 픽셀 좌표와 화면 대비 높이 비율을 계산한다."""
    result = calculate_vision_position(
        [detection(x1=100.0, y1=120.0, x2=300.0, y2=360.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.center_x == pytest.approx(200.0)
    assert result.position.center_y == pytest.approx(240.0)
    assert result.position.height_ratio == pytest.approx(0.5)


def test_no_people_returns_not_found_without_position() -> None:
    """사람이 없으면 위치 없이 찾지 못한 상태를 반환한다."""
    result = calculate_vision_position([], FRAME_WIDTH, FRAME_HEIGHT)

    assert result.status is VisionResultStatus.NOT_FOUND
    assert result.person_count == 0
    assert result.position is None


def test_one_person_returns_detected_position() -> None:
    """한 명이면 사용자 탐지 상태와 계산된 위치를 반환한다."""
    result = calculate_vision_position(
        [detection()],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.status is VisionResultStatus.USER_DETECTED
    assert result.person_count == 1
    assert result.position is not None


def test_multiple_people_returns_no_representative_position() -> None:
    """두 명 이상이면 특정 사람을 선택하지 않고 위치를 비운다."""
    result = calculate_vision_position(
        [detection(), detection(x1=400.0, x2=500.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.status is VisionResultStatus.MULTIPLE_PEOPLE
    assert result.person_count == 2
    assert result.position is None


@pytest.mark.parametrize(
    ("frame_width", "frame_height"),
    [(0, FRAME_HEIGHT), (-1, FRAME_HEIGHT), (FRAME_WIDTH, 0), (FRAME_WIDTH, -1)],
)
def test_rejects_non_positive_frame_size(
    frame_width: int,
    frame_height: int,
) -> None:
    """0 이하인 프레임 너비와 높이를 거부한다."""
    with pytest.raises(ValueError, match="Frame"):
        calculate_vision_position([detection()], frame_width, frame_height)


def test_person_detection_rejects_invalid_box_before_calculation() -> None:
    """면적이 없는 박스는 기존 탐지 계약에서 먼저 거부한다."""
    with pytest.raises(ValueError, match="positive width"):
        detection(x1=100.0, x2=100.0)


def test_clamps_partially_outside_box_to_frame() -> None:
    """프레임 밖으로 일부 벗어난 박스는 경계로 제한해 계산한다."""
    outside_detection = replace(
        detection(),
        x1=0.0,
        y1=0.0,
        x2=700.0,
        y2=500.0,
    )
    result = calculate_vision_position(
        [outside_detection],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert result.position.center_x == pytest.approx(FRAME_WIDTH / 2.0)
    assert result.position.center_y == pytest.approx(FRAME_HEIGHT / 2.0)
    assert result.position.offset_x == pytest.approx(0.0)
    assert result.position.offset_y == pytest.approx(0.0)
    assert result.position.height_ratio == pytest.approx(1.0)


def test_rejects_box_fully_outside_frame() -> None:
    """경계 제한 후 면적이 사라지는 박스는 위치 계산을 거부한다."""
    result_box = replace(detection(), x1=650.0, x2=700.0)

    with pytest.raises(ValueError, match="outside the frame"):
        calculate_vision_position([result_box], FRAME_WIDTH, FRAME_HEIGHT)


def test_normalized_values_remain_in_allowed_range() -> None:
    """경계에 걸친 박스의 정규화 값과 높이 비율은 허용 범위를 지킨다."""
    result = calculate_vision_position(
        [replace(detection(), x1=0.0, y1=0.0, x2=20.0, y2=20.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )

    assert result.position is not None
    assert -1.0 <= result.position.offset_x <= 1.0
    assert -1.0 <= result.position.offset_y <= 1.0
    assert 0.0 <= result.position.height_ratio <= 1.0
