"""Nav2 준비 확인과 제한된 목표 재시도 동작을 검증한다."""

from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from action_msgs.msg import GoalStatus
from lifecycle_msgs.msg import State

from core.nav2_waypoint_patrol import Nav2WaypointPatrol
from core.waypoint_route import PatrolRoute, Waypoint


def test_active_nav2_state_starts_patrol():
    """bt_navigator가 active일 때만 첫 목표를 전송한다."""
    logger = Mock()
    start_timer = Mock()
    action_client = Mock()
    action_client.wait_for_server.return_value = True
    patrol = SimpleNamespace(
        nav2_state_request_pending=True,
        last_nav2_state_id=None,
        action_client=action_client,
        start_timer=start_timer,
        get_logger=Mock(return_value=logger),
        _send_current_goal=Mock(),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        current_state=SimpleNamespace(
            id=State.PRIMARY_STATE_ACTIVE,
            label="active",
        )
    )

    Nav2WaypointPatrol._handle_nav2_state(patrol, future)

    assert patrol.nav2_state_request_pending is False
    action_client.wait_for_server.assert_called_once_with(timeout_sec=0.0)
    start_timer.cancel.assert_called_once()
    patrol._send_current_goal.assert_called_once()
    logger.info.assert_called_once_with(
        "Nav2 bt_navigator 활성화 완료"
    )


def test_inactive_nav2_state_keeps_waiting():
    """bt_navigator가 inactive이면 목표를 보내지 않고 대기한다."""
    logger = Mock()
    patrol = SimpleNamespace(
        nav2_state_request_pending=True,
        last_nav2_state_id=None,
        action_client=Mock(),
        start_timer=Mock(),
        get_logger=Mock(return_value=logger),
        _send_current_goal=Mock(),
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        current_state=SimpleNamespace(
            id=State.PRIMARY_STATE_INACTIVE,
            label="inactive",
        )
    )

    Nav2WaypointPatrol._handle_nav2_state(patrol, future)

    assert patrol.nav2_state_request_pending is False
    assert patrol.last_nav2_state_id == State.PRIMARY_STATE_INACTIVE
    patrol.action_client.wait_for_server.assert_not_called()
    patrol.start_timer.cancel.assert_not_called()
    patrol._send_current_goal.assert_not_called()
    logger.info.assert_called_once_with("Nav2 상태 대기: inactive")


def test_failed_goal_schedules_retry_for_current_waypoint():
    """실패한 목표를 설정된 지연 후 같은 지점에서 재시도한다."""
    route = PatrolRoute(
        waypoints=[Waypoint("sofa", 0.0, 0.0, 0.0)],
        loop=True,
        max_goal_retries=2,
        goal_retry_delay_sec=4.0,
    )
    logger = Mock()
    timer = Mock()
    retry_callback = Mock()
    patrol = SimpleNamespace(
        route=route,
        goal_in_progress=True,
        active_goal_handle=object(),
        goal_retry_timer=None,
        get_logger=Mock(return_value=logger),
        create_timer=Mock(return_value=timer),
        _retry_current_goal=retry_callback,
    )
    patrol._schedule_current_goal_retry = MethodType(
        Nav2WaypointPatrol._schedule_current_goal_retry,
        patrol,
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        status=GoalStatus.STATUS_ABORTED,
    )

    Nav2WaypointPatrol._handle_goal_result(patrol, future)

    assert patrol.goal_in_progress is False
    assert patrol.active_goal_handle is None
    assert route.current().name == "sofa"
    assert route.goal_failure_count == 1
    assert patrol.goal_retry_timer is timer
    patrol.create_timer.assert_called_once_with(4.0, retry_callback)
    logger.warning.assert_called_once()


def test_failed_goal_stops_after_retry_limit():
    """재시도를 모두 소진하면 추가 타이머 없이 안전 정지한다."""
    route = PatrolRoute(
        waypoints=[Waypoint("sofa", 0.0, 0.0, 0.0)],
        loop=True,
        max_goal_retries=0,
        goal_retry_delay_sec=0.0,
    )
    logger = Mock()
    patrol = SimpleNamespace(
        route=route,
        goal_in_progress=True,
        active_goal_handle=object(),
        goal_retry_timer=None,
        get_logger=Mock(return_value=logger),
        create_timer=Mock(),
        _retry_current_goal=Mock(),
    )
    patrol._schedule_current_goal_retry = MethodType(
        Nav2WaypointPatrol._schedule_current_goal_retry,
        patrol,
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(
        status=GoalStatus.STATUS_ABORTED,
    )

    Nav2WaypointPatrol._handle_goal_result(patrol, future)

    patrol.create_timer.assert_not_called()
    logger.error.assert_called_once()
    assert route.current().name == "sofa"


def test_rejected_goal_uses_bounded_retry_timer():
    """거부된 목표도 즉시 반복하지 않고 제한된 재시도를 사용한다."""
    route = PatrolRoute(
        waypoints=[Waypoint("sofa", 0.0, 0.0, 0.0)],
        loop=True,
        max_goal_retries=2,
        goal_retry_delay_sec=5.0,
    )
    logger = Mock()
    timer = Mock()
    retry_callback = Mock()
    patrol = SimpleNamespace(
        route=route,
        goal_in_progress=True,
        active_goal_handle=object(),
        goal_retry_timer=None,
        get_logger=Mock(return_value=logger),
        create_timer=Mock(return_value=timer),
        _retry_current_goal=retry_callback,
    )
    patrol._schedule_current_goal_retry = MethodType(
        Nav2WaypointPatrol._schedule_current_goal_retry,
        patrol,
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(accepted=False)

    Nav2WaypointPatrol._handle_goal_response(patrol, future)

    assert patrol.active_goal_handle is None
    assert patrol.goal_in_progress is False
    assert route.goal_failure_count == 1
    assert patrol.goal_retry_timer is timer
    patrol.create_timer.assert_called_once_with(5.0, retry_callback)
    logger.warning.assert_called_once()


def test_rejected_goal_stops_after_retry_limit():
    """목표 거부가 반복되면 설정된 한도에서 안전 정지한다."""
    route = PatrolRoute(
        waypoints=[Waypoint("sofa", 0.0, 0.0, 0.0)],
        loop=True,
        max_goal_retries=0,
        goal_retry_delay_sec=0.0,
    )
    logger = Mock()
    patrol = SimpleNamespace(
        route=route,
        goal_in_progress=True,
        active_goal_handle=object(),
        goal_retry_timer=None,
        get_logger=Mock(return_value=logger),
        create_timer=Mock(),
        _retry_current_goal=Mock(),
    )
    patrol._schedule_current_goal_retry = MethodType(
        Nav2WaypointPatrol._schedule_current_goal_retry,
        patrol,
    )
    future = Mock()
    future.result.return_value = SimpleNamespace(accepted=False)

    Nav2WaypointPatrol._handle_goal_response(patrol, future)

    patrol.create_timer.assert_not_called()
    logger.error.assert_called_once()
    assert route.goal_failure_count == 0


def test_retry_callback_releases_timer_before_resending_goal():
    """재시도 타이머를 해제한 뒤 현재 목표를 다시 보낸다."""
    timer = Mock()
    patrol = SimpleNamespace(
        goal_retry_timer=timer,
        destroy_timer=Mock(),
        _send_current_goal=Mock(),
    )

    Nav2WaypointPatrol._retry_current_goal(patrol)

    assert patrol.goal_retry_timer is None
    timer.cancel.assert_called_once()
    patrol.destroy_timer.assert_called_once_with(timer)
    patrol._send_current_goal.assert_called_once()
