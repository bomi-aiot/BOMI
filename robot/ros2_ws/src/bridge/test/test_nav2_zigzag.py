"""현관 지그재그 주행이 Nav2 목표로 어떻게 바뀌는지 검증한다.

test_nav2_robot_driver.py 가 직선 주행(NavigateToPose)을 고정한다면, 이
파일은 그 위에 얹힌 분기만 본다: **언제 NavigateThroughPoses 로 가고, 언제
조용히 직선으로 내려가는가.** 애교 기능이 귀가 대본을 실패시키지 않는다는
것이 여기서 지켜야 할 성질이다.
"""

from __future__ import annotations

from pathlib import Path

from builtin_interfaces.msg import Time
from nav2_msgs.action import NavigateThroughPoses, NavigateToPose
import pytest

from bridge import contract
from bridge.nav2_robot_driver import Nav2RobotDriver

_WAYPOINTS = """
waypoints:
  - name: entrance
    x: 4.0
    y: 0.0
    yaw: 1.57
  - name: charging
    x: 0.0
    y: 0.0
    yaw: 0.0
"""


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        pass


class _FakeClock:
    def now(self):
        return self

    def to_msg(self):
        return Time()


class _FakeNode:
    def __init__(self) -> None:
        self._logger = _FakeLogger()

    def get_logger(self):
        return self._logger

    def get_clock(self):
        return _FakeClock()

    def destroy_node(self) -> None:
        pass


class _FakeExecutor:
    def spin_once(self, timeout_sec=None) -> None:
        pass

    def spin_until_future_complete(self, future, timeout_sec=None) -> None:
        pass

    def remove_node(self, node) -> None:
        pass


class _FakeFuture:
    def __init__(self, result) -> None:
        self._result = result

    def done(self) -> bool:
        return True

    def result(self):
        return self._result


class _FakeResult:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakeGoalHandle:
    accepted = True

    def get_result_async(self):
        # 4 == GoalStatus.STATUS_SUCCEEDED
        return _FakeFuture(_FakeResult(4))


class _RecordingActionClient:
    """보내진 목표를 기록하는 Fake 액션 클라이언트."""

    def __init__(self) -> None:
        self.goals: list = []

    def server_is_ready(self) -> bool:
        return True

    def send_goal_async(self, goal):
        self.goals.append(goal)
        return _FakeFuture(_FakeGoalHandle())


class _Translation:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Transform:
    def __init__(self, x: float, y: float) -> None:
        self.transform = type(
            "_T", (), {"translation": _Translation(x, y)})()


class _FakeTfBuffer:
    """항상 같은 위치를 돌려주는 TF 버퍼."""

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self._x = x
        self._y = y

    def lookup_transform(self, target_frame, source_frame, when):
        return _Transform(self._x, self._y)


class _EmptyTfBuffer:
    """TF 가 아직 준비되지 않은 상태."""

    def lookup_transform(self, target_frame, source_frame, when):
        raise RuntimeError("no transform yet")


def _make_driver(tmp_path: Path, **kwargs) -> tuple:
    waypoint_file = tmp_path / "room_waypoints.yaml"
    waypoint_file.write_text(_WAYPOINTS, encoding="utf-8")

    to_pose = _RecordingActionClient()
    through_poses = _RecordingActionClient()
    node = _FakeNode()

    kwargs.setdefault("through_poses_client", through_poses)
    kwargs.setdefault("tf_buffer", _FakeTfBuffer())
    kwargs.setdefault("zigzag_enabled", True)

    driver = Nav2RobotDriver(
        navigation_node=node,
        action_client=to_pose,
        executor=_FakeExecutor(),
        waypoint_file=waypoint_file,
        **kwargs,
    )
    return driver, to_pose, through_poses, node


def test_entrance_uses_navigate_through_poses(tmp_path: Path) -> None:
    """현관은 지그재그 경유 좌표로 NavigateThroughPoses 를 쓴다."""
    driver, to_pose, through_poses, _ = _make_driver(tmp_path)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_ARRIVED

    assert to_pose.goals == []
    assert len(through_poses.goals) == 1
    goal = through_poses.goals[0]
    assert isinstance(goal, NavigateThroughPoses.Goal)
    assert len(goal.poses) >= 2


def test_zigzag_still_ends_exactly_on_the_waypoint(tmp_path: Path) -> None:
    """경유점을 넣어도 마지막 목표는 현관 좌표 그대로다."""
    driver, _, through_poses, _ = _make_driver(tmp_path)
    driver.navigate(contract.TARGET_ENTRANCE)

    last = through_poses.goals[0].poses[-1]
    assert last.pose.position.x == pytest.approx(4.0)
    assert last.pose.position.y == pytest.approx(0.0)


def test_other_targets_stay_straight(tmp_path: Path) -> None:
    """현관이 아니면 지그재그가 켜져 있어도 직선 주행이다."""
    driver, to_pose, through_poses, _ = _make_driver(tmp_path)

    assert driver.navigate(contract.TARGET_DEFAULT) == contract.STATUS_ARRIVED

    assert through_poses.goals == []
    assert len(to_pose.goals) == 1
    assert isinstance(to_pose.goals[0], NavigateToPose.Goal)


def test_disabled_switch_keeps_the_straight_path(tmp_path: Path) -> None:
    """킬 스위치가 꺼져 있으면 현관도 직선으로 간다."""
    driver, to_pose, through_poses, _ = _make_driver(
        tmp_path, zigzag_enabled=False)

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_ARRIVED

    assert through_poses.goals == []
    assert len(to_pose.goals) == 1


def test_missing_pose_falls_back_to_a_straight_path(tmp_path: Path) -> None:
    """TF 를 못 읽으면 경고만 남기고 직선으로 간다 — 실패시키지 않는다."""
    driver, to_pose, through_poses, node = _make_driver(
        tmp_path, tf_buffer=_EmptyTfBuffer())

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_ARRIVED

    assert through_poses.goals == []
    assert len(to_pose.goals) == 1
    assert any("current pose" in w for w in node.get_logger().warnings)


def test_short_approach_falls_back_to_a_straight_path(tmp_path: Path) -> None:
    """현관이 코앞이면(1m 미만) 꺾지 않고 직선으로 간다."""
    driver, to_pose, through_poses, _ = _make_driver(
        tmp_path, tf_buffer=_FakeTfBuffer(x=3.7, y=0.0))

    assert driver.navigate(contract.TARGET_ENTRANCE) == contract.STATUS_ARRIVED

    assert through_poses.goals == []
    assert len(to_pose.goals) == 1
