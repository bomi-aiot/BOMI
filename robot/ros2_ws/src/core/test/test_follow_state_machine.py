"""사람 추종 상태 머신의 안전 상태 전환을 검증한다."""

from core.follow_state_machine import (
    FollowState,
    FollowStateMachine,
    VisionTrackingStatus,
)


def acquire_target(
    machine: FollowStateMachine,
    track_id: int = 7,
) -> None:
    """한 명의 대상을 안정적으로 확인해 추종 상태로 만든다."""
    first = machine.update(
        VisionTrackingStatus.TRACKING,
        track_id,
        0.0,
    )
    assert first.movement_allowed is False

    confirmed = machine.update(
        VisionTrackingStatus.TRACKING,
        track_id,
        0.5,
    )
    assert confirmed.state is FollowState.FOLLOWING
    assert confirmed.movement_allowed is True


def test_target_is_confirmed_before_following() -> None:
    """처음 보인 사람을 즉시 따라가지 않고 잠시 확인한다."""
    machine = FollowStateMachine(
        target_confirm_sec=0.5,
    )

    first = machine.update(
        "tracking",
        7,
        0.0,
    )
    assert first.state is FollowState.WAITING_TARGET
    assert first.movement_allowed is False

    confirmed = machine.update(
        "tracking",
        7,
        0.5,
    )
    assert confirmed.state is FollowState.FOLLOWING
    assert confirmed.movement_allowed is True
    assert confirmed.target_track_id == 7


def test_multiple_people_stop_robot_immediately() -> None:
    """추종 중 여러 사람이 나타나면 즉시 정지한다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    result = machine.update(
        VisionTrackingStatus.MULTIPLE_PERSONS,
        None,
        1.0,
    )

    assert result.state is FollowState.MULTIPLE_OBSERVING
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "multiple_people_observing"


def test_single_person_after_multiple_waits_for_recovery_time() -> None:
    """다중 인물 이후 같은 Track ID가 유지돼야 추종을 재개한다."""
    machine = FollowStateMachine(
        single_recovery_sec=1.0,
    )
    acquire_target(machine)

    stopped = machine.update(
        "multiple_persons",
        None,
        1.0,
    )
    assert stopped.state is FollowState.MULTIPLE_OBSERVING
    assert stopped.movement_allowed is False

    confirming = machine.update(
        "tracking",
        7,
        1.1,
    )
    assert confirming.state is FollowState.MULTIPLE_OBSERVING
    assert confirming.movement_allowed is False
    assert confirming.target_track_id is None
    assert (
        confirming.reason
        == "single_target_recovery_confirming"
    )

    still_confirming = machine.update(
        "tracking",
        7,
        2.0,
    )
    assert still_confirming.state is FollowState.MULTIPLE_OBSERVING
    assert still_confirming.movement_allowed is False
    assert still_confirming.target_track_id is None

    resumed = machine.update(
        "tracking",
        7,
        2.2,
    )
    assert resumed.state is FollowState.FOLLOWING
    assert resumed.movement_allowed is True
    assert resumed.target_track_id == 7
    assert resumed.reason == "single_target_recovered"


def test_track_id_change_restarts_recovery_timer() -> None:
    """복구 중 Track ID가 바뀌면 안정화 시간을 다시 계산한다."""
    machine = FollowStateMachine(
        single_recovery_sec=1.0,
    )
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        1.0,
    )

    first_candidate = machine.update(
        "tracking",
        7,
        1.1,
    )
    assert first_candidate.movement_allowed is False
    assert first_candidate.target_track_id is None

    changed_candidate = machine.update(
        "tracking",
        9,
        1.6,
    )
    assert changed_candidate.movement_allowed is False
    assert changed_candidate.target_track_id is None
    assert (
        changed_candidate.reason
        == "single_target_recovery_confirming"
    )

    still_confirming = machine.update(
        "tracking",
        9,
        2.5,
    )
    assert still_confirming.movement_allowed is False
    assert still_confirming.target_track_id is None

    resumed = machine.update(
        "tracking",
        9,
        2.7,
    )
    assert resumed.state is FollowState.FOLLOWING
    assert resumed.movement_allowed is True
    assert resumed.target_track_id == 9
    assert resumed.reason == "single_target_recovered"


def test_persistent_multiple_people_keep_robot_stopped() -> None:
    """여러 사람이 계속 보이는 동안 로봇을 계속 정지시킨다."""
    machine = FollowStateMachine(
        multiple_observation_sec=3.0,
    )
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        1.0,
    )

    result = machine.update(
        "multiple_persons",
        None,
        10.0,
    )

    assert result.state is FollowState.MULTIPLE_OBSERVING
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "multiple_people_observing"


def test_long_multiple_still_requires_recovery_time() -> None:
    """다중 인물이 오래 지속돼도 복구 시간을 별도로 확인한다."""
    machine = FollowStateMachine(
        multiple_observation_sec=3.0,
        single_recovery_sec=1.0,
    )
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        1.0,
    )

    still_stopped = machine.update(
        "multiple_persons",
        None,
        10.0,
    )
    assert still_stopped.state is FollowState.MULTIPLE_OBSERVING
    assert still_stopped.movement_allowed is False

    confirming = machine.update(
        "tracking",
        9,
        10.1,
    )
    assert confirming.state is FollowState.MULTIPLE_OBSERVING
    assert confirming.movement_allowed is False
    assert confirming.target_track_id is None

    resumed = machine.update(
        "tracking",
        9,
        11.2,
    )
    assert resumed.state is FollowState.FOLLOWING
    assert resumed.movement_allowed is True
    assert resumed.target_track_id == 9


def test_not_detected_after_multiple_keeps_robot_stopped() -> None:
    """다중 인물 이후 아무도 감지되지 않으면 정지 상태를 유지한다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        1.0,
    )

    result = machine.update(
        "not_detected",
        None,
        2.0,
    )

    assert result.state is FollowState.MULTIPLE_OBSERVING
    assert result.movement_allowed is False
    assert result.target_track_id is None


def test_multiple_pending_keeps_robot_stopped() -> None:
    """다중 인물 여부를 확인하는 동안 로봇을 정지시킨다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    result = machine.update(
        "multiple_pending",
        None,
        1.0,
    )

    assert result.movement_allowed is False
    assert result.reason == "multiple_people_pending"


def test_single_recovery_keeps_robot_stopped() -> None:
    """AI가 한 명 복구를 안정화하는 동안 로봇을 정지시킨다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    result = machine.update(
        "single_recovery",
        None,
        1.0,
    )

    assert result.state is FollowState.MULTIPLE_OBSERVING
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "single_recovery_stabilizing"


def test_reset_lock_does_not_reset_normal_following() -> None:
    """잠기지 않은 추종 상태에서는 reset_lock이 상태를 바꾸지 않는다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    result = machine.reset_lock(1.0)

    assert result.state is FollowState.FOLLOWING
    assert result.movement_allowed is True
    assert result.reason == "following_lock_not_active"
    assert result.target_track_id == 7


def test_temporary_loss_recovers_same_target() -> None:
    """잠시 놓친 동일 Track ID가 돌아오면 추종을 재개한다."""
    machine = FollowStateMachine(
        lost_timeout_sec=1.0,
    )
    acquire_target(machine)

    lost = machine.update(
        "temporarily_lost",
        None,
        1.0,
    )
    assert lost.state is FollowState.TEMPORARILY_LOST
    assert lost.movement_allowed is False

    recovered = machine.update(
        "tracking",
        7,
        1.5,
    )
    assert recovered.state is FollowState.FOLLOWING
    assert recovered.movement_allowed is True
    assert recovered.target_track_id == 7


def test_vision_timeout_clears_following_target() -> None:
    """비전 입력이 끊기면 기존 대상을 지우고 대기 상태로 전환한다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    result = machine.handle_vision_timeout(2.0)

    assert result.state is FollowState.WAITING_TARGET
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "vision_command_timeout"


def test_vision_timeout_during_multiple_returns_to_waiting() -> None:
    """다중 인물 관찰 중 영상이 끊기면 대기 상태로 전환한다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        1.0,
    )

    result = machine.handle_vision_timeout(1.5)

    assert result.state is FollowState.WAITING_TARGET
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert (
        result.reason
        == "vision_timeout_during_multiple_observation"
    )


def test_clock_rollback_during_multiple_returns_to_waiting() -> None:
    """다중 인물 관찰 중 시간이 역행하면 안전하게 초기화한다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    machine.update(
        "multiple_persons",
        None,
        2.0,
    )

    result = machine.update(
        "tracking",
        7,
        1.0,
    )

    assert result.state is FollowState.WAITING_TARGET
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "clock_moved_backward"


def test_clock_rollback_does_not_enable_disabled_following() -> None:
    """시간이 뒤로 가도 비활성화 상태는 자동 해제되지 않는다."""
    machine = FollowStateMachine()
    acquire_target(machine)

    machine.disable(5.0)

    result = machine.update(
        "tracking",
        7,
        1.0,
    )

    assert result.state is FollowState.DISABLED
    assert result.movement_allowed is False
    assert result.target_track_id is None
    assert result.reason == "following_disabled"
