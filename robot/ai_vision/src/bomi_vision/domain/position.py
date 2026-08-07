"""화면 기준 사용자 위치와 사람 수에 따른 비전 결과 계약을 정의한다.

이 모듈의 위치값은 카메라 프레임의 픽셀 좌표와 정규화 값이며,
실제 공간 좌표나 거리 정보를 의미하지 않는다.
"""

from dataclasses import dataclass
from enum import Enum


class VisionResultStatus(str, Enum):
    """현재 프레임의 사용자 탐지 결과 상태를 표현한다."""

    NOT_FOUND = "not_found"
    USER_DETECTED = "user_detected"
    MULTIPLE_PEOPLE = "multiple_people"


@dataclass(frozen=True)
class UserPosition:
    """카메라 화면을 기준으로 계산한 사용자의 위치를 표현한다.

    이 클래스는 계산된 위치값을 보관하는 순수 데이터 컨테이너이며,
    값의 유효 범위 검증은 위치 계산 함수에서 수행한다.

    Attributes:
        center_x: 프레임에서 바운딩 박스 중심의 x 픽셀 좌표.
        center_y: 프레임에서 바운딩 박스 중심의 y 픽셀 좌표.
        offset_x: 화면 중심 기준 수평 위치. 계산 함수가 -1.0 이상 1.0 이하로 제한한다.
        offset_y: 화면 중심 기준 수직 위치. 계산 함수가 -1.0 이상 1.0 이하로 제한한다.
        height_ratio: 화면 높이 대비 바운딩 박스 높이 비율.
            계산 함수가 0.0 이상 1.0 이하로 제한한다.
    """

    center_x: float
    center_y: float
    offset_x: float
    offset_y: float
    height_ratio: float


@dataclass(frozen=True)
class VisionPositionResult:
    """사람 수와 사용자 화면 위치 계산 결과를 표현한다.

    사람이 한 명일 때만 ``position``을 제공한다. 사람이 없거나 두 명
    이상이면 특정 사용자를 선택하지 않고 ``None``을 사용한다.
    """

    status: VisionResultStatus
    person_count: int
    position: UserPosition | None

    def __post_init__(self) -> None:
        """상태, 사람 수, 위치 정보가 서로 일치하는지 검증한다.

        Raises:
            ValueError: 상태별 결과 계약이 일치하지 않는 경우.
        """
        valid = (
            (
                self.status is VisionResultStatus.NOT_FOUND
                and self.person_count == 0
                and self.position is None
            )
            or (
                self.status is VisionResultStatus.USER_DETECTED
                and self.person_count == 1
                and self.position is not None
            )
            or (
                self.status is VisionResultStatus.MULTIPLE_PEOPLE
                and self.person_count >= 2
                and self.position is None
            )
        )
        if not valid:
            raise ValueError("Vision position result does not match its status.")
