"""외부 추적 라이브러리와 무관한 사람 추적 결과 계약을 정의한다.

Track ID는 한 영상 흐름에서 객체를 구분하는 임시 식별자이며 실제 사용자
신원을 의미하지 않는다. 한 명을 추적할 때만 대표 ID와 위치를 제공한다.
"""

from dataclasses import dataclass
from enum import Enum

from bomi_vision.domain.detection import PersonDetection
from bomi_vision.domain.position import UserPosition


@dataclass(frozen=True)
class TrackedPerson:
    """현재 프레임에서 ByteTrack이 추적한 한 사람을 표현한다.

    좌표는 원본 프레임의 픽셀 좌표다. ``track_id``는 추적기 재시작이나
    재진입 시 바뀔 수 있으므로 사용자 식별 용도로 사용하면 안 된다.
    """

    track_id: int
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        """Track ID와 탐지 박스가 안전한 도메인 값인지 검증한다."""
        if isinstance(self.track_id, bool) or not isinstance(self.track_id, int):
            raise ValueError("Track ID must be an integer.")
        if self.track_id < 0:
            raise ValueError("Track ID must be zero or greater.")
        self.to_detection()

    def to_detection(self) -> PersonDetection:
        """기존 위치 계산이 사용할 사람 탐지 계약으로 변환한다."""
        return PersonDetection(
            confidence=self.confidence,
            x1=self.x1,
            y1=self.y1,
            x2=self.x2,
            y2=self.y2,
        )


class TrackingResultStatus(str, Enum):
    """현재 프레임의 사용자 추적 상태를 표현한다."""

    NOT_FOUND = "not_found"
    TRACKING = "tracking"
    MULTIPLE_PEOPLE = "multiple_people"
    TEMPORARILY_LOST = "temporarily_lost"


@dataclass(frozen=True)
class TrackingResult:
    """사람 수와 대표 사용자 추적 결과를 함께 표현한다.

    다중 인물이나 미탐지 상태에서는 안전을 위해 대표 Track ID와 위치를
    제공하지 않는다.
    """

    status: TrackingResultStatus
    person_count: int
    track_id: int | None
    position: UserPosition | None

    def __post_init__(self) -> None:
        """상태별 사람 수와 대표 결과의 일관성을 검증한다."""
        has_target = self.track_id is not None and self.position is not None
        valid = (
            (self.status is TrackingResultStatus.TRACKING and self.person_count == 1 and has_target)
            or (
                self.status is TrackingResultStatus.MULTIPLE_PEOPLE
                and self.person_count >= 2
                and not has_target
                and self.track_id is None
                and self.position is None
            )
            or (
                self.status
                in {
                    TrackingResultStatus.NOT_FOUND,
                    TrackingResultStatus.TEMPORARILY_LOST,
                }
                and self.person_count == 0
                and self.track_id is None
                and self.position is None
            )
        )
        if not valid:
            raise ValueError("Tracking result does not match its status.")
