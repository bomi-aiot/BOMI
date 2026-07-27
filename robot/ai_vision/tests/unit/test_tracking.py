"""외부 모델과 카메라 없이 사용자 추적 상태와 계약을 검증한다."""

import pytest

from bomi_vision.domain import TrackedPerson, TrackingResultStatus
from bomi_vision.tracking import UserTrackingService

pytestmark = pytest.mark.unit
FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def tracked_person(
    *,
    track_id: int = 3,
    x1: float = 270.0,
    y1: float = 140.0,
    x2: float = 370.0,
    y2: float = 340.0,
) -> TrackedPerson:
    """관심 있는 추적 필드만 바꿀 수 있는 테스트 결과를 생성한다."""
    return TrackedPerson(track_id, 0.9, x1, y1, x2, y2)


def test_one_person_returns_track_id_and_position() -> None:
    """한 명이면 Track ID와 기존 계산 방식의 화면 위치를 반환한다."""
    result = UserTrackingService(2).update([tracked_person()], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.TRACKING
    assert result.track_id == 3
    assert result.position is not None
    assert result.position.offset_x == pytest.approx(0.0)


def test_same_input_track_id_is_preserved_across_frames() -> None:
    """추적기가 유지한 Track ID를 연속 결과에서 변경하지 않고 전달한다."""
    service = UserTrackingService(2)
    first = service.update([tracked_person(track_id=7)], FRAME_WIDTH, FRAME_HEIGHT)
    second = service.update([tracked_person(track_id=7)], FRAME_WIDTH, FRAME_HEIGHT)
    assert first.track_id == second.track_id == 7


def test_no_people_without_previous_target_returns_not_found() -> None:
    """이전 대상이 없는 빈 프레임은 즉시 찾지 못한 상태를 반환한다."""
    result = UserTrackingService(2).update([], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.NOT_FOUND


def test_short_detection_loss_returns_temporarily_lost() -> None:
    """정상 추적 직후 허용 범위 안의 빈 프레임은 일시 누락으로 처리한다."""
    service = UserTrackingService(2)
    service.update([tracked_person()], FRAME_WIDTH, FRAME_HEIGHT)
    result = service.update([], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.TEMPORARILY_LOST
    assert result.track_id is None
    assert result.position is None


def test_loss_beyond_tolerance_returns_not_found() -> None:
    """연속 누락이 허용 프레임 수를 넘으면 오래된 대상을 폐기한다."""
    service = UserTrackingService(1)
    service.update([tracked_person()], FRAME_WIDTH, FRAME_HEIGHT)
    service.update([], FRAME_WIDTH, FRAME_HEIGHT)
    result = service.update([], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.NOT_FOUND


def test_multiple_people_has_no_representative_target() -> None:
    """두 명 이상이면 대표 Track ID와 위치를 생성하지 않는다."""
    result = UserTrackingService(2).update(
        [tracked_person(track_id=1), tracked_person(track_id=2, x1=400.0, x2=500.0)],
        FRAME_WIDTH,
        FRAME_HEIGHT,
    )
    assert result.status is TrackingResultStatus.MULTIPLE_PEOPLE
    assert result.person_count == 2
    assert result.track_id is None
    assert result.position is None


@pytest.mark.parametrize("track_id", [-1, 1.5, True])
def test_rejects_invalid_track_id(track_id: object) -> None:
    """음수이거나 정수가 아닌 Track ID를 안전하게 거부한다."""
    with pytest.raises(ValueError, match="Track ID"):
        TrackedPerson(track_id, 0.9, 10.0, 10.0, 20.0, 20.0)  # type: ignore[arg-type]


def test_rejects_invalid_tracked_bounding_box() -> None:
    """면적이 없는 추적 바운딩 박스를 기존 탐지 계약으로 거부한다."""
    with pytest.raises(ValueError, match="positive width"):
        tracked_person(x1=10.0, x2=10.0)


@pytest.mark.parametrize("lost_tolerance_frames", [-1, 1.5, True])
def test_rejects_invalid_lost_tolerance(lost_tolerance_frames: object) -> None:
    """음수이거나 정수가 아닌 누락 허용 프레임 수를 거부한다."""
    with pytest.raises(ValueError, match="Lost tolerance"):
        UserTrackingService(lost_tolerance_frames)  # type: ignore[arg-type]
