"""이름으로 고른 한 지점만 주행하고 종료하는 동작을 검증한다."""

import math
from types import SimpleNamespace
from unittest.mock import Mock

from action_msgs.msg import GoalStatus
from lifecycle_msgs.msg import State
import pytest
from rclpy.clock import Clock

from core.goto_waypoint import GotoWaypoint, select_waypoint
from core.waypoint_route import Waypoint, WaypointConfigError


WAYPOINTS = [
    Waypoint(name="sofa", x=0.1, y=1.7, yaw=0.0),
    Waypoint(name="entrance", x=-0.2, y=-1.5, yaw=1.57),
    Waypoint(name="charging", x=0.0, y=0.0, yaw=0.0),
]


def test_select_waypoint_finds_the_named_point():
    """이름이 일치하는 지점을 그대로 돌려준다."""
    assert select_waypoint(WAYPOINTS, "entrance") is WAYPOINTS[1]


def test_missing_name_lists_the_available_names():
    """없는 이름을 주면 고를 수 있는 이름을 알려주며 실패한다."""
    with pytest.raises(WaypointConfigError) as error:
        select_waypoint(WAYPOINTS, "livingroom")

    message = str(error.value)
    assert "livingroom" in message
    for waypoint in WAYPOINTS:
        assert waypoint.name in message


def test_missing_name_does_not_fall_back_to_another_point():
    """오타가 났을 때 임의의 지점으로 주행하지 않는다."""
    with pytest.raises(WaypointConfigError):
        select_waypoint(WAYPOINTS, "")


def test_active_nav2_state_sends_the_goal():
    """bt_navigator가 active일 때만 목표를 전송한다."""
    action_client = Mock()
    action_client.wait_for_server.return_value = True
    start_timer = Mock()
    node = SimpleNamespace(
        nav2_state_request_pending=True,
        last_nav2_state_id=None,
        action_client=action_client,
        start_timer=start_timer,
        get_logger=Mock(return_value=Mock()),
        _send_goal=Mock(),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        current_state=SimpleNamespace(
            id=State.PRIMARY_STATE_ACTIVE,
            label="active",
        )
    )

    GotoWaypoint._handle_nav2_state(node, future)

    start_timer.cancel.assert_called_once()
    node._send_goal.assert_called_once()


def test_inactive_nav2_state_does_not_send_the_goal():
    """활성화되지 않은 동안에는 목표를 보내지 않고 계속 기다린다."""
    node = SimpleNamespace(
        nav2_state_request_pending=True,
        last_nav2_state_id=None,
        action_client=Mock(),
        start_timer=Mock(),
        get_logger=Mock(return_value=Mock()),
        _send_goal=Mock(),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        current_state=SimpleNamespace(
            id=State.PRIMARY_STATE_UNCONFIGURED,
            label="unconfigured",
        )
    )

    GotoWaypoint._handle_nav2_state(node, future)

    node._send_goal.assert_not_called()
    node.start_timer.cancel.assert_not_called()


def test_missing_action_server_is_reported_once_and_keeps_waiting():
    """액션 서버를 못 찾는 동안 조용히 멈춰 있지 않고 한 번 알린다.

    이 경로는 return으로 빠지기 때문에 로그가 없으면 "bt_navigator는
    active인데 액션 서버만 없는" 상태를 진단할 수 없다. 실제로 그래서
    30초 동안 아무 로그 없이 멈춘 적이 있어 테스트로 고정한다.
    """
    logger = Mock()
    action_client = Mock()
    action_client.wait_for_server.return_value = False
    start_timer = Mock()
    node = SimpleNamespace(
        nav2_state_request_pending=True,
        last_nav2_state_id=None,
        action_client=action_client,
        start_timer=start_timer,
        warned_action_server_missing=False,
        get_logger=Mock(return_value=logger),
        _send_goal=Mock(),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        current_state=SimpleNamespace(
            id=State.PRIMARY_STATE_ACTIVE,
            label="active",
        )
    )

    GotoWaypoint._handle_nav2_state(node, future)
    GotoWaypoint._handle_nav2_state(node, future)

    node._send_goal.assert_not_called()
    start_timer.cancel.assert_not_called()
    assert node.warned_action_server_missing is True
    assert logger.info.call_count == 1


def test_arrival_finishes_the_run():
    """도착하면 arrived와 finished를 세워 노드가 빠져나가게 한다."""
    node = SimpleNamespace(
        active_goal_handle=Mock(),
        arrived=False,
        finished=False,
        waypoint=WAYPOINTS[1],
        get_logger=Mock(return_value=Mock()),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        status=GoalStatus.STATUS_SUCCEEDED
    )

    GotoWaypoint._handle_goal_result(node, future)

    assert node.arrived is True
    assert node.finished is True
    assert node.active_goal_handle is None


def test_failed_goal_finishes_without_claiming_arrival():
    """주행이 실패하면 종료하되 도착했다고 하지 않는다."""
    node = SimpleNamespace(
        active_goal_handle=Mock(),
        arrived=False,
        finished=False,
        waypoint=WAYPOINTS[1],
        get_logger=Mock(return_value=Mock()),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        status=GoalStatus.STATUS_ABORTED
    )

    GotoWaypoint._handle_goal_result(node, future)

    assert node.arrived is False
    assert node.finished is True


def test_rejected_goal_finishes_immediately():
    """Nav2가 목표를 거부하면 재시도하지 않고 바로 끝낸다."""
    handle = SimpleNamespace(accepted=False)
    future = Mock()
    future.result.return_value = handle
    node = SimpleNamespace(
        active_goal_handle=None,
        finished=False,
        get_logger=Mock(return_value=Mock()),
    )

    GotoWaypoint._handle_goal_response(node, future)

    assert node.finished is True
    assert node.active_goal_handle is None


def test_nav2_wait_gives_up_after_the_timeout():
    """Nav2가 끝내 활성화되지 않으면 무한 대기하지 않고 종료한다."""
    start_timer = Mock()
    node = SimpleNamespace(
        nav2_state_request_pending=False,
        waited_sec=30.0,
        wait_timeout_sec=30.0,
        start_timer=start_timer,
        navigator_state_client=Mock(),
        finished=False,
        get_logger=Mock(return_value=Mock()),
    )

    GotoWaypoint.wait_for_nav2(node)

    assert node.finished is True
    start_timer.cancel.assert_called_once()
    node.navigator_state_client.service_is_ready.assert_not_called()


def test_pose_carries_the_waypoint_coordinates_and_yaw():
    """목표 pose에 좌표와 yaw가 quaternion으로 실린다."""
    node = SimpleNamespace(
        frame_id="map",
        get_clock=Mock(return_value=Clock()),
    )
    waypoint = WAYPOINTS[1]

    pose = GotoWaypoint._create_pose(node, waypoint)

    assert pose.header.frame_id == "map"
    assert pose.pose.position.x == pytest.approx(waypoint.x)
    assert pose.pose.position.y == pytest.approx(waypoint.y)
    assert pose.pose.orientation.z == pytest.approx(
        math.sin(waypoint.yaw / 2.0)
    )
    assert pose.pose.orientation.w == pytest.approx(
        math.cos(waypoint.yaw / 2.0)
    )
