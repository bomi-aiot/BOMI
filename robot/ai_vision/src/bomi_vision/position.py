"""사람 탐지 결과에서 화면 기준 사용자 위치와 상태를 계산한다.

OpenCV 프레임 대신 탐지 결과와 프레임 크기만 입력받아 외부 모델이나
카메라 없이 계산 정책을 테스트할 수 있다.
"""

from collections.abc import Sequence
import math

from bomi_vision.domain import (
    PersonDetection,
    UserPosition,
    VisionPositionResult,
    VisionResultStatus,
)


def calculate_vision_position(
    detections: Sequence[PersonDetection],
    frame_width: int,
    frame_height: int,
) -> VisionPositionResult:
    """사람 수를 분류하고 한 명일 때 화면 기준 위치를 계산한다.

    바운딩 박스가 프레임 밖으로 일부 벗어나면 각 좌표를 프레임 경계로
    제한한 뒤 계산한다. 제한 후 너비나 높이가 사라지면 유효한 위치를
    만들 수 없으므로 예외를 발생시킨다.

    Args:
        detections: 현재 프레임의 모든 사람 탐지 결과.
        frame_width: 픽셀 단위 프레임 너비.
        frame_height: 픽셀 단위 프레임 높이.

    Returns:
        사람 수 상태와 선택 가능한 경우의 사용자 화면 위치.

    Raises:
        ValueError: 프레임 크기나 한 명의 탐지 결과가 유효하지 않은 경우.
    """
    _validate_frame_size(frame_width, frame_height)
    person_count = len(detections)

    if person_count == 0:
        return VisionPositionResult(VisionResultStatus.NOT_FOUND, 0, None)
    if person_count >= 2:
        return VisionPositionResult(
            VisionResultStatus.MULTIPLE_PEOPLE,
            person_count,
            None,
        )

    position = _calculate_user_position(
        detections[0],
        frame_width,
        frame_height,
    )
    return VisionPositionResult(VisionResultStatus.USER_DETECTED, 1, position)


def _validate_frame_size(frame_width: int, frame_height: int) -> None:
    """위치 정규화의 분모로 사용할 프레임 크기를 검증한다."""
    if isinstance(frame_width, bool) or not isinstance(frame_width, int):
        raise ValueError("Frame width must be a positive integer.")
    if isinstance(frame_height, bool) or not isinstance(frame_height, int):
        raise ValueError("Frame height must be a positive integer.")
    if frame_width <= 0:
        raise ValueError("Frame width must be greater than zero.")
    if frame_height <= 0:
        raise ValueError("Frame height must be greater than zero.")


def _calculate_user_position(
    detection: PersonDetection,
    frame_width: int,
    frame_height: int,
) -> UserPosition:
    """한 사람의 박스를 프레임에 제한하고 정규화 위치를 계산한다."""
    coordinates = (detection.x1, detection.y1, detection.x2, detection.y2)
    if not math.isfinite(detection.confidence) or not all(
        math.isfinite(value) for value in coordinates
    ):
        raise ValueError("Detection confidence and coordinates must be finite.")
    if not 0.0 <= detection.confidence <= 1.0:
        raise ValueError("Detection confidence must be between 0.0 and 1.0.")
    if detection.x2 <= detection.x1 or detection.y2 <= detection.y1:
        raise ValueError("Detection bounding box must have a positive width and height.")

    x1 = min(max(detection.x1, 0.0), float(frame_width))
    y1 = min(max(detection.y1, 0.0), float(frame_height))
    x2 = min(max(detection.x2, 0.0), float(frame_width))
    y2 = min(max(detection.y2, 0.0), float(frame_height))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Detection bounding box is outside the frame.")

    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    offset_x = _clamp_normalized((center_x - frame_width / 2.0) / (frame_width / 2.0))
    offset_y = _clamp_normalized((center_y - frame_height / 2.0) / (frame_height / 2.0))
    height_ratio = min(max((y2 - y1) / frame_height, 0.0), 1.0)

    return UserPosition(
        center_x=center_x,
        center_y=center_y,
        offset_x=offset_x,
        offset_y=offset_y,
        height_ratio=height_ratio,
    )


def _clamp_normalized(value: float) -> float:
    """부동소수점 오차를 포함한 정규화 값을 안전 범위로 제한한다."""
    return min(max(value, -1.0), 1.0)
