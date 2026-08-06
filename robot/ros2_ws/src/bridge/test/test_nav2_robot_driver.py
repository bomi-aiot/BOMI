"""Nav2RobotDriver의 결과/실패/취소 처리를 검증하는 단위 테스트다.

실제 Nav2 서버 없이 액션 클라이언트와 executor 경계만 Fake로 대체한다. 다만 이
테스트는 geometry_msgs/nav2_msgs/action_msgs/rclpy를 import하므로, 이들이 준비된
ROS 2 환경(colcon test)에서 실행한다. Nav2 서버 자체는 필요하지 않다.
"""

from pathlib import Path

from action_msgs.msg import GoalStatus
from bridge import contract
from bridge.nav2_robot_driver import Nav2RobotDriver
from builtin_interfaces.msg import Time
import pytest


_WAYPOINTS = """
waypoints:
  - name: entrance
    x: -0.226
    y: -1.520
    yaw: 1.57
"""


class _FakeLogger:
    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class _FakeClock:
    def now(self):
        return self

    def to_msg(self):
        return Time()


class _FakeNode:
    """드라이버가 쓰는 로거와 시계만 흉내 내는 Fake 노드다."""

    def __init__(self) -> None:
        self.destroyed = False

    def get_logger(self):
        return _FakeLogger()

    def get_clock(self):
        return _FakeClock()

    def destroy_node(self) -> None:
        self.destroyed = True


class _FakeExecutor:
    """spin을 실제로 돌리지 않는 Fake executor다.

    future의 완료 상태는 테스트가 미리 정해 두므로 여기서는 아무 것도 하지
    않는다. spin_until_future_complete가 반환하면 드라이버는 future.done()으로
    완료 여부를 판단한다.
    """

    def spin_once(self, timeout_sec=None) -> None:
        pass

    def spin_until_future_complete(self, future, timeout_sec=None) -> None:
        pass

    def remove_node(self, node) -> None:
        pass


class _FakeFuture:
    def __init__(self, result=None, complete: bool = True) -> None:
        self._result = result
        self._complete = complete

    def done(self) -> bool:
        return self._complete

    def result(self):
        return self._result


class _FakeResult:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakeGoalHandle:
    def __init__(self, accepted: bool, result_future=None) -> None:
        self.accepted = accepted
        self._result_future = result_future or _FakeFuture()
        self.cancel_called = False

    def get_result_async(self):
        return self._result_future

    def cancel_goal_async(self):
        self.cancel_called = True
        return _FakeFuture(result=None, complete=True)


class _FakeActionClient:
    def __init__(self, server_ready: bool, send_goal_future=None,
                 send_error: Exception = None) -> None:
        self._server_ready = server_ready
        self._send_goal_future = send_goal_future
        self._send_error = send_error
        self.sent_goals: list = []

    def server_is_ready(self) -> bool:
        return self._server_ready

    def send_goal_async(self, goal):
        if self._send_error is not None:
            raise self._send_error
        self.sent_goals.append(goal)
        return self._send_goal_future

    def destroy(self) -> None:
        pass


def _make_driver(tmp_path: Path, action_client, goal_timeout_seconds=30.0):
    path = tmp_path / "room_waypoints.yaml"
    path.write_text(_WAYPOINTS, encoding="utf-8")
    return Nav2RobotDriver(
        navigation_node=_FakeNode(),
        action_client=action_client,
        executor=_FakeExecutor(),
        waypoint_file=path,
        goal_timeout_seconds=goal_timeout_seconds,
    )


def test_successful_navigation_returns_arrived(tmp_path) -> None:
    goal_handle = _FakeGoalHandle(
        accepted=True,
        result_future=_FakeFuture(
            result=_FakeResult(GoalStatus.STATUS_SUCCEEDED), complete=True
        ),
    )
    client = _FakeActionClient(
        server_ready=True,
        send_goal_future=_FakeFuture(result=goal_handle, complete=True),
    )
    driver = _make_driver(tmp_path, client)

    status = driver.navigate(contract.TARGET_ENTRANCE)

    assert status == contract.STATUS_ARRIVED
    assert len(client.sent_goals) == 1
    # 완료 후 진행 중 목표 핸들이 정리되어야 한다.
    assert driver._active_goal_handle is None


def test_rejected_goal_returns_failed(tmp_path) -> None:
    goal_handle = _FakeGoalHandle(accepted=False)
    client = _FakeActionClient(
        server_ready=True,
        send_goal_future=_FakeFuture(result=goal_handle, complete=True),
    )
    driver = _make_driver(tmp_path, client)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_FAILED


def test_failed_result_status_returns_failed(tmp_path) -> None:
    goal_handle = _FakeGoalHandle(
        accepted=True,
        result_future=_FakeFuture(
            result=_FakeResult(GoalStatus.STATUS_ABORTED), complete=True
        ),
    )
    client = _FakeActionClient(
        server_ready=True,
        send_goal_future=_FakeFuture(result=goal_handle, complete=True),
    )
    driver = _make_driver(tmp_path, client)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_FAILED


def test_server_not_ready_returns_failed(tmp_path) -> None:
    client = _FakeActionClient(server_ready=False)
    driver = _make_driver(tmp_path, client, goal_timeout_seconds=0.01)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_FAILED
    assert client.sent_goals == []


def test_result_timeout_cancels_and_returns_failed(tmp_path) -> None:
    goal_handle = _FakeGoalHandle(
        accepted=True,
        # 결과 future가 끝나지 않아 타임아웃되는 상황.
        result_future=_FakeFuture(result=None, complete=False),
    )
    client = _FakeActionClient(
        server_ready=True,
        send_goal_future=_FakeFuture(result=goal_handle, complete=True),
    )
    driver = _make_driver(tmp_path, client, goal_timeout_seconds=0.01)

    status = driver.navigate(contract.TARGET_ENTRANCE)

    assert status == contract.STATUS_FAILED
    assert goal_handle.cancel_called is True
    assert driver._active_goal_handle is None


def test_action_client_exception_returns_failed(tmp_path) -> None:
    client = _FakeActionClient(
        server_ready=True, send_error=RuntimeError("boom")
    )
    driver = _make_driver(tmp_path, client)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_FAILED


def test_unsupported_target_does_not_send_goal(tmp_path) -> None:
    client = _FakeActionClient(server_ready=True)
    driver = _make_driver(tmp_path, client)

    assert driver.navigate(contract.TARGET_DEFAULT) == contract.STATUS_FAILED
    assert client.sent_goals == []


def test_cancel_with_active_goal_requests_cancellation(tmp_path) -> None:
    client = _FakeActionClient(server_ready=True)
    driver = _make_driver(tmp_path, client)

    goal_handle = _FakeGoalHandle(accepted=True)
    driver._active_goal_handle = goal_handle

    status = driver.cancel()

    assert status == contract.STATUS_CANCELLED
    assert goal_handle.cancel_called is True
    assert driver._active_goal_handle is None


def test_cancel_without_active_goal_is_safe(tmp_path) -> None:
    client = _FakeActionClient(server_ready=True)
    driver = _make_driver(tmp_path, client)

    assert driver.cancel() == contract.STATUS_CANCELLED


def test_speak_is_not_supported(tmp_path) -> None:
    client = _FakeActionClient(server_ready=True)
    driver = _make_driver(tmp_path, client)

    assert driver.speak("hello") == contract.STATUS_FAILED


def test_zero_timeout_is_rejected(tmp_path) -> None:
    client = _FakeActionClient(server_ready=True)

    with pytest.raises(ValueError):
        _make_driver(tmp_path, client, goal_timeout_seconds=0.0)
