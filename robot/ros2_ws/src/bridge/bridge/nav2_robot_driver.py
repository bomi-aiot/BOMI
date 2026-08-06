"""백엔드 NAVIGATE 명령을 실제 Nav2 주행으로 실행하는 드라이버.

이 모듈은 결정 문서 ``docs/decisions/0001-nav2-driver-owns-action-client.md``의
옵션 B를 구현한다. 즉 브릿지의 실물 드라이버가 Nav2 ``NavigateToPose`` 액션
클라이언트를 직접 소유하고, 목적지 이름을 좌표로 바꿔 목표를 보낸 뒤 도착 결과를
기다린다.

핵심 설계:

* 드라이버의 ``navigate()``는 동기 인터페이스이고 Nav2 액션은 비동기다. 두 구조를
  잇기 위해 드라이버 전용 ROS 2 노드와 전용 executor를 사용하고, 목표가 끝날
  때까지 그 전용 executor만 spin한다. 상위 실행 노드(mqtt_bridge_node)가 spin하는
  전역 executor는 건드리지 않으므로 중첩 spin과 교착이 발생하지 않는다.
* 노드/executor/액션 클라이언트는 생성자로 명시적으로 주입한다. 실제 ROS 2 객체는
  ``create_nav2_robot_driver`` 팩터리가 만들고, 단위 테스트는 Fake를 주입한다.
* 좌표는 이 모듈에 하드코딩하지 않고 core의 room_waypoints.yaml에서 읽는다.

이 모듈은 ROS 2 노드 실행 경로에서만 사용한다. 순수 paho MQTT 러너처럼 rclpy가
없는 실행 경로에서는 import하거나 생성하지 않는다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor

from bridge import contract
from bridge.robot_driver import RobotDriver
from bridge.waypoint_lookup import load_waypoint, resolve_waypoint_name
from core.waypoint_route import Waypoint, yaw_to_quaternion

# 목표 전송 후 도착까지 기다리는 최대 시간(초). 기존 문서에 기준이 없어 기본값으로
# 120초를 사용하되, 생성자 인자와 ROS 2 파라미터로 노출해 상수로 숨기지 않는다.
DEFAULT_GOAL_TIMEOUT_SECONDS = 120.0

# 액션 서버 준비를 기다리며 전용 executor를 한 번 spin할 때의 대기 시간(초).
_SPIN_ONCE_TIMEOUT_SECONDS = 0.1

# 취소 요청을 보낸 뒤 취소 응답을 기다리는 최대 시간(초).
_CANCEL_RESULT_WAIT_SECONDS = 5.0


class Nav2RobotDriver(RobotDriver):
    """NAVIGATE 명령을 Nav2 NavigateToPose 주행으로 실행하는 드라이버.

    역할: 목적지 이름을 웨이포인트 좌표로 바꿔 Nav2에 목표를 보내고, 도착
        여부에 따라 계약 상태(ARRIVED/FAILED)를 돌려준다.
    입력값(생성자): navigation_node - 드라이버 전용 ROS 2 노드. action_client -
        NavigateToPose 액션 클라이언트. executor - 전용 SingleThreadedExecutor
        (navigation_node가 추가된 상태). waypoint_file - room_waypoints.yaml
        경로. frame_id - 목표 pose의 좌표계(기본 "map"). goal_timeout_seconds -
        도착 대기 최대 시간(초).
    주의: 이 드라이버의 메서드는 단일 스레드(paho MQTT 콜백 스레드)에서 순차
        호출된다고 가정한다. paho 루프는 메시지를 순차 처리하므로 navigate()가
        블로킹하는 동안 같은 스레드에서 cancel()이 동시에 진입하지 않는다.
    """

    def __init__(
        self,
        navigation_node: Any,
        action_client: Any,
        executor: Any,
        waypoint_file: str | Path,
        *,
        frame_id: str = "map",
        goal_timeout_seconds: float = DEFAULT_GOAL_TIMEOUT_SECONDS,
    ) -> None:
        """전용 노드/executor/액션 클라이언트와 주행 설정을 저장한다."""
        if goal_timeout_seconds <= 0.0:
            raise ValueError(
                "goal_timeout_seconds must be a positive number of seconds"
            )

        self._navigation_node = navigation_node
        self._action_client = action_client
        self._executor = executor
        self._waypoint_file = waypoint_file
        self._frame_id = frame_id
        self._goal_timeout_seconds = float(goal_timeout_seconds)
        self._logger = navigation_node.get_logger()

        # 진행 중인 Nav2 목표 핸들. 목표가 없으면 None이다. 완료/실패/취소 시
        # 반드시 None으로 정리해 다음 명령에서 재사용되지 않게 한다.
        self._active_goal_handle: Any | None = None

    def navigate(self, target: str) -> str:
        """목적지로 주행하고 계약 상태(ARRIVED 또는 FAILED)를 반환한다.

        역할: target을 웨이포인트로 변환해 Nav2 목표를 보내고 결과를 기다린다.
        입력값: target - 백엔드 목적지 이름(예: "ENTRANCE").
        반환값: 도착 성공 시 contract.STATUS_ARRIVED, 그 밖의 모든 경우
            contract.STATUS_FAILED.
        실패: 미지원 목적지, 웨이포인트 로딩 실패, 서버 미준비, 목표 거부,
            타임아웃, 결과 실패, 예외를 모두 FAILED로 처리한다. 하드웨어나
            Nav2가 없다는 이유로 가짜 ARRIVED를 만들지 않는다.
        """
        waypoint_name = resolve_waypoint_name(target)
        if waypoint_name is None:
            self._logger.warning(
                f"Unsupported navigation target '{target}'; "
                "not sending a Nav2 goal"
            )
            return contract.STATUS_FAILED

        try:
            waypoint = load_waypoint(self._waypoint_file, waypoint_name)
        except Exception as error:
            # 파일 없음, 잘못된 YAML, 이름 누락 등 어떤 로딩 실패든 성공으로
            # 처리하지 않고 원인을 남긴 뒤 FAILED로 돌려준다.
            self._logger.error(
                f"Failed to load waypoint '{waypoint_name}': {error}"
            )
            return contract.STATUS_FAILED

        try:
            return self._navigate_to_waypoint(waypoint)
        except Exception as error:
            # 예외가 MQTT 처리 스레드로 새어 나가 브릿지 전체를 멈추지 않도록
            # 드라이버 경계에서 잡는다. 원인을 남기고 진행 중 목표를 정리한다.
            self._logger.error(
                f"Navigation failed with an unexpected error: {error}"
            )
            self._cancel_active_goal_quietly()
            return contract.STATUS_FAILED

    def speak(self, text: str) -> str:
        """이 드라이버는 발화를 지원하지 않으므로 FAILED를 반환한다.

        Nav2 드라이버는 주행만 담당한다. SPEAK 실행 수단이 없으므로 가짜
        성공(DONE) 대신 FAILED를 돌려주고 그 사실을 로그로 남긴다.
        """
        self._logger.warning(
            "Nav2RobotDriver does not support speak; reporting FAILED"
        )
        return contract.STATUS_FAILED

    def cancel(self) -> str:
        """진행 중인 Nav2 목표가 있으면 취소를 요청하고 CANCELLED를 반환한다.

        역할: 진행 중 목표가 없으면 안전하게 CANCELLED를 돌려주고, 있으면 Nav2에
            취소를 요청한다.
        반환값: 항상 contract.STATUS_CANCELLED.
        실패: 취소 요청 자체가 실패해도 예외를 밖으로 던지지 않고 로그만 남긴다.
        주의: 취소 뒤 이전 목표 핸들을 정리해 다음 명령에서 재사용되지 않게 한다.
        """
        goal_handle = self._active_goal_handle
        if goal_handle is None:
            self._logger.info(
                "Cancel requested but no navigation goal is active"
            )
            return contract.STATUS_CANCELLED

        self._request_goal_cancellation(goal_handle)
        return contract.STATUS_CANCELLED

    def shutdown(self) -> None:
        """드라이버가 보유한 ROS 2 자원을 정리한다.

        상위 실행 노드가 종료할 때 호출한다. rclpy 컨텍스트(init/shutdown)는
        상위 노드가 소유하므로 여기서는 건드리지 않고, 이 드라이버가 만든
        액션 클라이언트와 전용 노드만 정리한다.
        """
        try:
            self._action_client.destroy()
        except Exception as error:
            self._logger.warning(
                f"Failed to destroy the action client cleanly: {error}"
            )

        try:
            self._executor.remove_node(self._navigation_node)
        except Exception:
            # executor 정리 실패는 종료 흐름을 막을 이유가 아니므로 무시한다.
            pass

        self._navigation_node.destroy_node()

    def _navigate_to_waypoint(self, waypoint: Waypoint) -> str:
        """웨이포인트 하나로 Nav2 목표를 보내고 도착 결과를 기다린다."""
        deadline = time.monotonic() + self._goal_timeout_seconds

        if not self._wait_for_action_server(deadline):
            self._logger.error(
                "Nav2 action server was not available before timeout"
            )
            return contract.STATUS_FAILED

        goal_message = NavigateToPose.Goal()
        goal_message.pose = self._create_goal_pose(waypoint)

        send_goal_future = self._action_client.send_goal_async(goal_message)
        self._logger.info(f"Sending Nav2 goal: {waypoint.name}")

        if not self._spin_until_complete(send_goal_future, deadline):
            self._logger.error(
                "Timed out while waiting for the goal to be accepted"
            )
            return contract.STATUS_FAILED

        goal_handle = send_goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self._logger.warning("Nav2 rejected the navigation goal")
            return contract.STATUS_FAILED

        self._active_goal_handle = goal_handle
        result_future = goal_handle.get_result_async()

        if not self._spin_until_complete(result_future, deadline):
            self._logger.error(
                "Navigation did not finish before timeout; cancelling goal"
            )
            self._cancel_active_goal_quietly()
            return contract.STATUS_FAILED

        # 결과를 받았으므로 진행 중 목표를 정리한다.
        self._active_goal_handle = None

        result = result_future.result()
        if result is None:
            self._logger.error("Navigation result was empty")
            return contract.STATUS_FAILED

        if result.status == GoalStatus.STATUS_SUCCEEDED:
            self._logger.info(f"Navigation succeeded: reached {waypoint.name}")
            return contract.STATUS_ARRIVED

        self._logger.warning(
            f"Navigation finished without success: status={result.status}"
        )
        return contract.STATUS_FAILED

    def _wait_for_action_server(self, deadline: float) -> bool:
        """전용 executor를 spin하며 액션 서버가 준비될 때까지 기다린다."""
        while not self._action_client.server_is_ready():
            if time.monotonic() >= deadline:
                return False
            self._executor.spin_once(timeout_sec=_SPIN_ONCE_TIMEOUT_SECONDS)
        return True

    def _spin_until_complete(self, future: Any, deadline: float) -> bool:
        """남은 시간 동안 전용 executor를 spin하며 future 완료를 기다린다.

        반환값: 마감 시간 안에 future가 완료되면 True, 아니면 False.
        """
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0.0:
            return future.done()

        self._executor.spin_until_future_complete(
            future, timeout_sec=remaining_seconds
        )
        return future.done()

    def _cancel_active_goal_quietly(self) -> None:
        """진행 중 목표가 있으면 조용히 취소를 요청하고 핸들을 정리한다."""
        goal_handle = self._active_goal_handle
        self._active_goal_handle = None
        if goal_handle is None:
            return
        self._request_goal_cancellation(goal_handle)

    def _request_goal_cancellation(self, goal_handle: Any) -> None:
        """목표 취소를 요청하고 취소 응답을 짧게 기다린다.

        취소 요청 자체가 실패해도 예외를 밖으로 던지지 않는다. 어떤 경우에도
        진행 중 목표 핸들을 정리해 다음 명령에서 재사용되지 않게 한다.
        """
        self._active_goal_handle = None
        try:
            cancel_future = goal_handle.cancel_goal_async()
            cancel_deadline = time.monotonic() + _CANCEL_RESULT_WAIT_SECONDS
            completed = self._spin_until_complete(cancel_future, cancel_deadline)
            if completed:
                self._logger.info("Cancel request completed")
            else:
                self._logger.warning(
                    "Cancel request did not complete before timeout"
                )
        except Exception as error:
            self._logger.warning(f"Failed to send cancel request: {error}")

    def _create_goal_pose(self, waypoint: Waypoint) -> PoseStamped:
        """웨이포인트를 Nav2 목표 PoseStamped로 변환한다.

        core의 nav2_waypoint_patrol과 같은 방식으로 frame_id, 현재 시각, x, y,
        yaw->quaternion 변환을 채운다.
        """
        pose = PoseStamped()
        pose.header.frame_id = self._frame_id
        pose.header.stamp = self._navigation_node.get_clock().now().to_msg()
        pose.pose.position.x = waypoint.x
        pose.pose.position.y = waypoint.y

        qx, qy, qz, qw = yaw_to_quaternion(waypoint.yaw)
        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        pose.pose.orientation.w = qw

        return pose


def default_waypoint_file() -> Path:
    """설치된 core 패키지 share 경로의 room_waypoints.yaml 경로를 반환한다.

    현재 작업 디렉터리에 의존하는 상대 경로 대신 ROS 2 패키지 share 경로를
    단일 좌표 출처로 사용한다.
    """
    share_directory = get_package_share_directory("core")
    return Path(share_directory) / "config" / "room_waypoints.yaml"


def create_nav2_robot_driver(
    *,
    waypoint_file: str | Path | None = None,
    action_name: str = "navigate_to_pose",
    frame_id: str = "map",
    goal_timeout_seconds: float = DEFAULT_GOAL_TIMEOUT_SECONDS,
) -> Nav2RobotDriver:
    """실제 ROS 2 객체를 만들어 Nav2RobotDriver를 구성하는 팩터리.

    역할: 드라이버 전용 노드, NavigateToPose 액션 클라이언트, 전용 executor를
        만들어 Nav2RobotDriver에 주입한다.
    입력값: waypoint_file - 좌표 YAML 경로(None이면 core share 경로 사용).
        action_name - 액션 이름(기본 "navigate_to_pose"). frame_id - 목표 좌표계.
        goal_timeout_seconds - 도착 대기 최대 시간(초).
    반환값: 구성된 Nav2RobotDriver.
    주의: rclpy가 이미 초기화된 ROS 2 노드 실행 경로에서만 호출해야 한다.
        전용 노드는 상위 노드가 spin하는 전역 executor에 추가하지 않는다.
    """
    resolved_waypoint_file = waypoint_file
    if resolved_waypoint_file is None:
        resolved_waypoint_file = default_waypoint_file()

    navigation_node = rclpy.create_node("nav2_robot_driver")
    action_client = ActionClient(navigation_node, NavigateToPose, action_name)
    executor = SingleThreadedExecutor()
    executor.add_node(navigation_node)

    return Nav2RobotDriver(
        navigation_node=navigation_node,
        action_client=action_client,
        executor=executor,
        waypoint_file=resolved_waypoint_file,
        frame_id=frame_id,
        goal_timeout_seconds=goal_timeout_seconds,
    )
