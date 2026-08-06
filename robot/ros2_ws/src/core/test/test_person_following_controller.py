"""사람 추종 속도 제어 로직을 검증한다."""

import pytest

from core.person_following_controller import (
    PersonFollowingController,
)


def test_move_forward_when_person_is_far_enough() -> None:
    """사람이 1.0m보다 멀면 전진 명령을 수행한다."""
    controller = PersonFollowingController(
        linear_speed=0.15,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.2,
        emergency_obstacle_distance_m=1.2,
    )

    assert result.linear_x == pytest.approx(0.15)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "moving_forward"


def test_turn_left_command() -> None:
    """좌회전 명령을 양의 각속도로 변환한다."""
    controller = PersonFollowingController(
        angular_speed=0.5,
    )

    result = controller.calculate_velocity(
        "turn_left",
        movement_allowed=True,
        emergency_obstacle_distance_m=1.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.5)
    assert result.reason == "turning_left"


def test_turn_right_command() -> None:
    """우회전 명령을 음의 각속도로 변환한다."""
    controller = PersonFollowingController(
        angular_speed=0.5,
    )

    result = controller.calculate_velocity(
        "turn_right",
        movement_allowed=True,
        emergency_obstacle_distance_m=1.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(-0.5)
    assert result.reason == "turning_right"


def test_stop_command() -> None:
    """비전 정지 명령에서 모든 속도를 0으로 만든다."""
    controller = PersonFollowingController()

    result = controller.calculate_velocity(
        "stop",
        movement_allowed=True,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "stop_requested"


def test_movement_not_allowed_overrides_command() -> None:
    """상태 머신이 이동을 금지하면 전진 명령도 정지시킨다."""
    controller = PersonFollowingController()

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=False,
        person_distance_m=2.0,
        emergency_obstacle_distance_m=2.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "movement_not_allowed"


def test_emergency_obstacle_stops_forward_command() -> None:
    """전방 장애물이 0.3m 이하면 전진하지 않는다."""
    controller = PersonFollowingController(
        emergency_stop_distance_m=0.3,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=2.0,
        emergency_obstacle_distance_m=0.3,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "emergency_obstacle_too_close"


def test_emergency_obstacle_stops_turn_command() -> None:
    """긴급 장애물이 있으면 회전 명령도 정지시킨다."""
    controller = PersonFollowingController(
        emergency_stop_distance_m=0.3,
    )

    result = controller.calculate_velocity(
        "turn_left",
        movement_allowed=True,
        emergency_obstacle_distance_m=0.2,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "emergency_obstacle_too_close"


def test_person_at_stop_distance_stops_robot() -> None:
    """사람이 0.5m 이하이면 로봇을 정지시킨다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=0.5,
        emergency_obstacle_distance_m=1.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "person_too_close"


def test_person_farther_than_resume_distance_allows_forward() -> None:
    """사람이 1.0m보다 멀면 전진을 시작한다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.01,
        emergency_obstacle_distance_m=1.01,
    )

    assert result.linear_x == pytest.approx(0.15)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "moving_forward"


def test_exact_resume_distance_does_not_start_forward() -> None:
    """정지 상태에서 정확히 1.0m이면 전진을 시작하지 않는다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.0,
        emergency_obstacle_distance_m=1.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert (
        result.reason
        == "waiting_for_person_resume_distance"
    )


def test_forward_continues_inside_hysteresis_range() -> None:
    """전진 중에는 0.5m 초과 거리에서 전진을 유지한다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    started = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.2,
        emergency_obstacle_distance_m=1.2,
    )
    assert started.reason == "moving_forward"

    continued = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=0.8,
        emergency_obstacle_distance_m=0.8,
    )

    assert continued.linear_x == pytest.approx(0.15)
    assert continued.angular_z == pytest.approx(0.0)
    assert continued.reason == "moving_forward"


def test_robot_stays_stopped_until_resume_distance() -> None:
    """0.5m에서 정지한 뒤 1.0m 이하에서는 정지를 유지한다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.2,
        emergency_obstacle_distance_m=1.2,
    )

    stopped = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=0.5,
        emergency_obstacle_distance_m=0.5,
    )
    assert stopped.reason == "person_too_close"

    waiting = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=0.8,
        emergency_obstacle_distance_m=0.8,
    )

    assert waiting.linear_x == pytest.approx(0.0)
    assert waiting.angular_z == pytest.approx(0.0)
    assert (
        waiting.reason
        == "waiting_for_person_resume_distance"
    )


def test_robot_resumes_after_person_moves_farther_than_one_meter() -> None:
    """정지 후 사람이 1.0m보다 멀어지면 전진을 재개한다."""
    controller = PersonFollowingController(
        person_stop_distance_m=0.5,
        person_resume_distance_m=1.0,
    )

    controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.2,
        emergency_obstacle_distance_m=1.2,
    )

    controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=0.5,
        emergency_obstacle_distance_m=0.5,
    )

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        person_distance_m=1.1,
        emergency_obstacle_distance_m=1.1,
    )

    assert result.linear_x == pytest.approx(0.15)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "moving_forward"


def test_missing_person_distance_stops_forward_command() -> None:
    """사람 거리 없이 전진 명령이 오면 안전하게 정지한다."""
    controller = PersonFollowingController()

    result = controller.calculate_velocity(
        "move_forward",
        movement_allowed=True,
        emergency_obstacle_distance_m=1.0,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "person_distance_unavailable"


def test_unknown_command_stops_robot() -> None:
    """알 수 없는 명령은 정지로 처리한다."""
    controller = PersonFollowingController()

    result = controller.calculate_velocity(
        "fly",
        movement_allowed=True,
    )

    assert result.linear_x == pytest.approx(0.0)
    assert result.angular_z == pytest.approx(0.0)
    assert result.reason == "stop_requested"


def test_invalid_distance_configuration_is_rejected() -> None:
    """재출발 거리가 정지 거리보다 작으면 오류를 발생시킨다."""
    with pytest.raises(ValueError):
        PersonFollowingController(
            person_stop_distance_m=0.5,
            person_resume_distance_m=0.4,
        )
