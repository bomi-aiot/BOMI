"""외부 장비 없이 사용자 위치 기반 추종 희망 명령을 검증한다."""

from dataclasses import replace
import math

import pytest

from bomi_vision.domain import (
    FollowCommand,
    TrackingResult,
    TrackingResultStatus,
    UserPosition,
)
from bomi_vision.follow import FollowCommandGenerator

pytestmark = pytest.mark.unit


def tracking_result(
    *,
    offset_x: float = 0.0,
    height_ratio: float = 0.3,
) -> TrackingResult:
    """정상적인 한 명 추적 결과의 위치값만 바꿔 생성한다."""
    position = UserPosition(320.0, 240.0, offset_x, 0.0, height_ratio)
    return TrackingResult(TrackingResultStatus.TRACKING, 1, 7, position)


def unsafe_result(status: TrackingResultStatus) -> TrackingResult:
    """대표 대상이 없는 안전 상태의 추적 결과를 생성한다."""
    person_count = 2 if status is TrackingResultStatus.MULTIPLE_PEOPLE else 0
    return TrackingResult(status, person_count, None, None)


def inconsistent_tracking_result(
    *,
    track_id: int | None,
    position: UserPosition | None,
) -> TrackingResult:
    """도메인 생성자를 우회해 상위 경계의 손상된 입력을 재현한다."""
    result = object.__new__(TrackingResult)
    object.__setattr__(result, "status", TrackingResultStatus.TRACKING)
    object.__setattr__(result, "person_count", 1)
    object.__setattr__(result, "track_id", track_id)
    object.__setattr__(result, "position", position)
    return result


def test_left_user_turns_left() -> None:
    """화면 왼쪽 사용자는 왼쪽 회전 희망 명령을 생성한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(tracking_result(offset_x=-0.3))
    assert result.command is FollowCommand.TURN_LEFT
    assert result.reason == "user_left_of_center"
    assert result.track_id == 7


def test_right_user_turns_right() -> None:
    """화면 오른쪽 사용자는 오른쪽 회전 희망 명령을 생성한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(tracking_result(offset_x=0.3))
    assert result.command is FollowCommand.TURN_RIGHT


def test_centered_far_user_moves_forward() -> None:
    """화면 중앙에 있고 작게 보이는 사용자는 전진 희망 명령을 생성한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(tracking_result(height_ratio=0.2))
    assert result.command is FollowCommand.MOVE_FORWARD
    assert result.reason == "user_far_and_centered"


def test_centered_near_user_stops() -> None:
    """화면 중앙에서 정지 거리 비율에 도달한 사용자는 정지한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(tracking_result(height_ratio=0.45))
    assert result.command is FollowCommand.STOP
    assert result.reason == "safe_follow_distance_reached"
    assert result.track_id == 7


@pytest.mark.parametrize("offset_x", [-0.15, 0.15])
def test_dead_zone_boundary_is_centered(offset_x: float) -> None:
    """수평 임계값과 정확히 같은 위치는 중앙으로 처리한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(
        tracking_result(offset_x=offset_x, height_ratio=0.2)
    )
    assert result.command is FollowCommand.MOVE_FORWARD


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (TrackingResultStatus.NOT_FOUND, "tracking_not_available"),
        (TrackingResultStatus.TEMPORARILY_LOST, "temporarily_lost"),
        (TrackingResultStatus.MULTIPLE_PEOPLE, "multiple_people_detected"),
    ],
)
def test_unsafe_tracking_status_stops(
    status: TrackingResultStatus,
    reason: str,
) -> None:
    """대표 사용자를 신뢰할 수 없는 추적 상태는 항상 정지한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(unsafe_result(status))
    assert result.command is FollowCommand.STOP
    assert result.reason == reason
    assert result.track_id is None


def test_missing_position_stops() -> None:
    """정상 추적 상태라도 위치가 없으면 이동하지 않는다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(
        inconsistent_tracking_result(track_id=7, position=None)
    )
    assert result.command is FollowCommand.STOP
    assert result.reason == "position_missing"


def test_missing_track_id_stops() -> None:
    """정상 추적 상태라도 대표 Track ID가 없으면 이동하지 않는다."""
    position = tracking_result().position
    assert position is not None
    result = FollowCommandGenerator(0.15, 0.45).generate(
        inconsistent_tracking_result(track_id=None, position=position)
    )
    assert result.command is FollowCommand.STOP
    assert result.reason == "track_id_missing"


@pytest.mark.parametrize(
    ("horizontal_dead_zone", "forward_threshold"),
    [
        (-0.1, 0.45),
        (1.0, 0.45),
        (math.nan, 0.45),
        (0.15, -0.1),
        (0.15, 1.1),
        (0.15, math.inf),
    ],
)
def test_rejects_invalid_thresholds(
    horizontal_dead_zone: float,
    forward_threshold: float,
) -> None:
    """유한하지 않거나 허용 범위 밖인 추종 임계값을 거부한다."""
    with pytest.raises(ValueError):
        FollowCommandGenerator(horizontal_dead_zone, forward_threshold)


@pytest.mark.parametrize(
    ("offset_x", "expected"),
    [(-0.3, FollowCommand.TURN_LEFT), (0.3, FollowCommand.TURN_RIGHT)],
)
def test_horizontal_turn_has_priority_over_distance(
    offset_x: float,
    expected: FollowCommand,
) -> None:
    """사용자가 가까워도 좌우에 있으면 수평 정렬을 먼저 요청한다."""
    result = FollowCommandGenerator(0.15, 0.45).generate(
        tracking_result(offset_x=offset_x, height_ratio=0.9)
    )
    assert result.command is expected


def test_invalid_position_stops() -> None:
    """범위를 벗어난 위치값은 이동에 사용하지 않고 안전하게 정지한다."""
    valid = tracking_result()
    assert valid.position is not None
    damaged = inconsistent_tracking_result(
        track_id=7,
        position=replace(valid.position, offset_x=1.1),
    )
    result = FollowCommandGenerator(0.15, 0.45).generate(damaged)
    assert result.command is FollowCommand.STOP
    assert result.reason == "invalid_tracking_result"


def test_follow_command_has_no_reverse_option() -> None:
    """추종 희망 명령 계약에 후진 명령이 포함되지 않았음을 확인한다."""
    assert "move_backward" not in {command.value for command in FollowCommand}
