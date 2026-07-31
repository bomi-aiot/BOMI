"""외부 모델과 카메라 없이 사람 추적 상태 머신과 계약을 검증한다.

`docs/state-machine.md` §24의 시나리오를 사람 수 입력만으로 재현해 다중 인물
확인, 한 명 복귀 안정화, 일시적 추적 실패와 안전 규칙을 확인한다.
"""

import pytest

from bomi_vision.domain import TrackedPerson, TrackingResult, TrackingResultStatus
from bomi_vision.tracking import UserTrackingService

pytestmark = pytest.mark.unit
FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def tracking_service(
    *,
    lost_tolerance_frames: int = 2,
    multiple_confirm_frames: int = 2,
    single_recovery_frames: int = 3,
) -> UserTrackingService:
    """검증할 전환만 짧게 만들 수 있는 상태 머신을 생성한다."""
    return UserTrackingService(
        lost_tolerance_frames=lost_tolerance_frames,
        multiple_confirm_frames=multiple_confirm_frames,
        single_recovery_frames=single_recovery_frames,
    )


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


def tracked_people(person_count: int) -> list[TrackedPerson]:
    """겹치지 않는 박스를 가진 사람 추적 결과를 사람 수만큼 생성한다."""
    return [
        tracked_person(
            track_id=index + 1,
            x1=10.0 + index * 60.0,
            x2=60.0 + index * 60.0,
        )
        for index in range(person_count)
    ]


def advance(service: UserTrackingService, *person_counts: int) -> list[TrackingResultStatus]:
    """사람 수 시퀀스를 순서대로 입력하고 각 프레임의 상태를 모은다."""
    return [service.update_state(person_count) for person_count in person_counts]


def test_initial_state_is_not_detected() -> None:
    """첫 프레임이 들어오기 전 초기 상태는 미검출이다."""
    assert tracking_service().state is TrackingResultStatus.NOT_DETECTED


def test_no_people_keeps_not_detected() -> None:
    """사람이 계속 없으면 미검출 상태를 유지한다."""
    assert advance(tracking_service(), 0, 0, 0) == [
        TrackingResultStatus.NOT_DETECTED,
        TrackingResultStatus.NOT_DETECTED,
        TrackingResultStatus.NOT_DETECTED,
    ]


def test_single_person_starts_tracking() -> None:
    """미검출 상태에서 한 명이 검출되면 정상 추적으로 전환한다."""
    assert advance(tracking_service(), 1) == [TrackingResultStatus.TRACKING]


def test_missing_person_becomes_temporarily_lost() -> None:
    """정상 추적 중 사람이 사라지면 먼저 일시 누락으로 완충한다."""
    assert advance(tracking_service(), 1, 0) == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.TEMPORARILY_LOST,
    ]


def test_person_returning_within_tolerance_resumes_tracking() -> None:
    """허용 범위 안에 한 명이 다시 검출되면 정상 추적으로 복귀한다."""
    service = tracking_service(lost_tolerance_frames=2)

    states = advance(service, 1, 0, 0, 1)

    assert states == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.TEMPORARILY_LOST,
        TrackingResultStatus.TEMPORARILY_LOST,
        TrackingResultStatus.TRACKING,
    ]


def test_loss_beyond_tolerance_becomes_not_detected() -> None:
    """누락이 허용 프레임 수를 넘으면 오래된 대상을 폐기한다."""
    service = tracking_service(lost_tolerance_frames=1)

    states = advance(service, 1, 0, 0)

    assert states == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.TEMPORARILY_LOST,
        TrackingResultStatus.NOT_DETECTED,
    ]


def test_multiple_people_first_frame_is_pending() -> None:
    """정상 추적 중 두 명이 검출된 첫 프레임은 확인 상태로 완충한다."""
    assert advance(tracking_service(multiple_confirm_frames=2), 1, 2) == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.MULTIPLE_PENDING,
    ]


def test_single_person_before_confirm_returns_to_tracking() -> None:
    """확인 기준 전에 다시 한 명이 되면 정상 추적으로 복귀한다."""
    service = tracking_service(multiple_confirm_frames=3)

    states = advance(service, 1, 2, 2, 1)

    assert states == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.TRACKING,
    ]


def test_multiple_people_are_confirmed_after_threshold() -> None:
    """두 명 이상이 확인 기준까지 지속되면 다중 인물로 확정한다."""
    service = tracking_service(multiple_confirm_frames=3)

    states = advance(service, 2, 2, 2)

    assert states == [
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PERSONS,
    ]


def test_single_confirm_frame_still_buffers_one_frame() -> None:
    """확인 기준이 1이어도 한 프레임의 검출만으로 확정하지 않는다."""
    service = tracking_service(multiple_confirm_frames=1)

    states = advance(service, 2, 2)

    assert states == [
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PERSONS,
    ]


def test_multiple_persons_with_single_person_starts_recovery() -> None:
    """다중 인물 확정 후 한 명이 되면 안정화를 시작한다."""
    service = tracking_service(multiple_confirm_frames=2, single_recovery_frames=3)

    states = advance(service, 2, 2, 1)

    assert states[-1] is TrackingResultStatus.SINGLE_RECOVERY


def test_single_person_recovers_after_stable_frames() -> None:
    """한 명 상태가 복귀 기준까지 유지되면 정상 추적으로 복귀한다."""
    service = tracking_service(multiple_confirm_frames=2, single_recovery_frames=3)
    advance(service, 2, 2)

    recovery_states = advance(service, 1, 1, 1)

    assert recovery_states == [
        TrackingResultStatus.SINGLE_RECOVERY,
        TrackingResultStatus.SINGLE_RECOVERY,
        TrackingResultStatus.TRACKING,
    ]


def test_multiple_people_during_recovery_return_to_multiple_persons() -> None:
    """안정화 도중 두 명 이상이 재검출되면 확인 없이 확정 상태로 돌아간다."""
    service = tracking_service(multiple_confirm_frames=2, single_recovery_frames=3)
    advance(service, 2, 2, 1)

    states = advance(service, 2, 1)

    assert states == [
        TrackingResultStatus.MULTIPLE_PERSONS,
        TrackingResultStatus.SINGLE_RECOVERY,
    ]


def test_temporarily_lost_with_multiple_people_starts_pending() -> None:
    """일시 누락 중 두 명 이상이 검출되면 다중 인물 확인으로 전이한다."""
    service = tracking_service(lost_tolerance_frames=2, multiple_confirm_frames=2)

    states = advance(service, 1, 0, 2)

    assert states[-1] is TrackingResultStatus.MULTIPLE_PENDING


def test_pending_after_tracking_falls_back_to_temporarily_lost() -> None:
    """정상 추적 이력이 있으면 확인 중 모두 사라져도 일시 누락으로 완충한다."""
    service = tracking_service(lost_tolerance_frames=2, multiple_confirm_frames=3)

    states = advance(service, 1, 2, 0)

    assert states[-1] is TrackingResultStatus.TEMPORARILY_LOST


def test_pending_without_previous_target_falls_back_to_not_detected() -> None:
    """추적 이력 없이 시작한 확인 상태에서 모두 사라지면 미검출로 전환한다."""
    service = tracking_service(multiple_confirm_frames=3)

    states = advance(service, 2, 0)

    assert states == [
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.NOT_DETECTED,
    ]


def test_multiple_persons_without_people_becomes_not_detected() -> None:
    """다중 인물 확정 상태에서 모두 사라지면 미검출로 전환한다."""
    service = tracking_service(multiple_confirm_frames=2)

    states = advance(service, 2, 2, 0)

    assert states[-1] is TrackingResultStatus.NOT_DETECTED


def test_recovery_without_people_becomes_not_detected() -> None:
    """안정화 중 모두 사라지면 이전 대상을 유지하지 않고 미검출로 전환한다."""
    service = tracking_service(multiple_confirm_frames=2, single_recovery_frames=3)

    states = advance(service, 2, 2, 1, 0)

    assert states[-1] is TrackingResultStatus.NOT_DETECTED


def test_one_person_returns_track_id_and_position() -> None:
    """한 명이면 Track ID와 기존 계산 방식의 화면 위치를 반환한다."""
    result = tracking_service().update([tracked_person()], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.TRACKING
    assert result.track_id == 3
    assert result.position is not None
    assert result.position.offset_x == pytest.approx(0.0)


def test_same_input_track_id_is_preserved_across_frames() -> None:
    """추적기가 유지한 Track ID를 연속 결과에서 변경하지 않고 전달한다."""
    service = tracking_service()
    first = service.update([tracked_person(track_id=7)], FRAME_WIDTH, FRAME_HEIGHT)
    second = service.update([tracked_person(track_id=7)], FRAME_WIDTH, FRAME_HEIGHT)
    assert first.track_id == second.track_id == 7


def test_no_people_without_previous_target_returns_not_detected() -> None:
    """이전 대상이 없는 빈 프레임은 즉시 찾지 못한 상태를 반환한다."""
    result = tracking_service().update([], FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.NOT_DETECTED
    assert result.person_count == 0


def test_multiple_people_have_no_representative_target() -> None:
    """다중 인물 확인 상태에서는 대표 Track ID와 위치를 생성하지 않는다."""
    result = tracking_service().update(tracked_people(2), FRAME_WIDTH, FRAME_HEIGHT)
    assert result.status is TrackingResultStatus.MULTIPLE_PENDING
    assert result.person_count == 2
    assert result.track_id is None
    assert result.position is None


def test_buffer_states_never_expose_a_representative_target() -> None:
    """정상 추적이 아닌 모든 상태에서 대표 Track ID와 위치를 제공하지 않는다."""
    service = tracking_service(
        lost_tolerance_frames=2,
        multiple_confirm_frames=2,
        single_recovery_frames=3,
    )
    frame_sequence = [
        tracked_people(1),
        [],
        tracked_people(2),
        tracked_people(2),
        tracked_people(1),
        [],
    ]

    results = [service.update(people, FRAME_WIDTH, FRAME_HEIGHT) for people in frame_sequence]

    assert [result.status for result in results] == [
        TrackingResultStatus.TRACKING,
        TrackingResultStatus.TEMPORARILY_LOST,
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PERSONS,
        TrackingResultStatus.SINGLE_RECOVERY,
        TrackingResultStatus.NOT_DETECTED,
    ]
    for result in results[1:]:
        assert result.track_id is None
        assert result.position is None


@pytest.mark.parametrize(
    "status",
    [
        TrackingResultStatus.MULTIPLE_PENDING,
        TrackingResultStatus.MULTIPLE_PERSONS,
        TrackingResultStatus.SINGLE_RECOVERY,
        TrackingResultStatus.TEMPORARILY_LOST,
        TrackingResultStatus.NOT_DETECTED,
    ],
)
def test_result_contract_rejects_target_outside_tracking(
    status: TrackingResultStatus,
) -> None:
    """정상 추적이 아닌 상태에 대표 Track ID를 담는 결과를 거부한다."""
    with pytest.raises(ValueError, match="Tracking result"):
        TrackingResult(status, 1, 3, None)


@pytest.mark.parametrize(
    ("status", "person_count"),
    [
        (TrackingResultStatus.NOT_DETECTED, 1),
        (TrackingResultStatus.TEMPORARILY_LOST, 2),
        (TrackingResultStatus.MULTIPLE_PENDING, 1),
        (TrackingResultStatus.MULTIPLE_PERSONS, 1),
        (TrackingResultStatus.SINGLE_RECOVERY, 2),
    ],
)
def test_result_contract_rejects_mismatched_person_count(
    status: TrackingResultStatus,
    person_count: int,
) -> None:
    """상태 정의와 맞지 않는 사람 수를 담은 결과를 거부한다."""
    with pytest.raises(ValueError, match="Tracking result"):
        TrackingResult(status, person_count, None, None)


@pytest.mark.parametrize("person_count", [-1, 1.5, True, None])
def test_rejects_invalid_person_count(person_count: object) -> None:
    """음수이거나 정수가 아닌 사람 수를 0명으로 바꾸지 않고 거부한다."""
    with pytest.raises(ValueError, match="Person count"):
        tracking_service().update_state(person_count)  # type: ignore[arg-type]


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
        tracking_service(lost_tolerance_frames=lost_tolerance_frames)  # type: ignore[arg-type]


@pytest.mark.parametrize("multiple_confirm_frames", [0, -1, 1.5, True])
def test_rejects_invalid_multiple_confirm_frames(multiple_confirm_frames: object) -> None:
    """1 미만이거나 정수가 아닌 다중 인물 확인 프레임 수를 거부한다."""
    with pytest.raises(ValueError, match="Multiple confirm"):
        tracking_service(multiple_confirm_frames=multiple_confirm_frames)  # type: ignore[arg-type]


@pytest.mark.parametrize("single_recovery_frames", [0, -1, 1.5, True])
def test_rejects_invalid_single_recovery_frames(single_recovery_frames: object) -> None:
    """1 미만이거나 정수가 아닌 복귀 안정화 프레임 수를 거부한다."""
    with pytest.raises(ValueError, match="Single recovery"):
        tracking_service(single_recovery_frames=single_recovery_frames)  # type: ignore[arg-type]
