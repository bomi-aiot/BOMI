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
* 현관(ENTRANCE)만은 직선 대신 좌우로 번갈아 기운 지그재그로 다가간다 —
  어르신을 반기러 나가는 걸음을 표현하기 위해서다. 경로를 직접 그리지 않고
  ``bridge.zigzag`` 가 만든 경유 좌표를 ``NavigateThroughPoses`` 로 넘기므로,
  costmap·장애물 회피·복구는 전부 Nav2 가 그대로 담당한다. 출발점(TF
  map->base_link)을 못 얻거나 거리가 짧으면 조용히 직선 주행으로 내려간다 —
  애교 때문에 귀가 대본이 실패하는 일은 없어야 한다.

이 모듈은 ROS 2 노드 실행 경로에서만 사용한다. 순수 paho MQTT 러너처럼 rclpy가
없는 실행 경로에서는 import하거나 생성하지 않는다.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateThroughPoses, NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

from bridge import contract
from bridge.robot_driver import RobotDriver
from bridge.waypoint_lookup import load_waypoint, resolve_waypoint_name
from bridge.zigzag import (
    DEFAULT_ZIGZAG_ANGLE_DEG,
    DEFAULT_ZIGZAG_LEG_LENGTH_M,
    DEFAULT_ZIGZAG_MIN_DISTANCE_M,
    zigzag_path,
)
from core.waypoint_route import Waypoint, yaw_to_quaternion

# 목표 전송 후 도착까지 기다리는 최대 시간(초). 기존 문서에 기준이 없어 기본값으로
# 120초를 사용하되, 생성자 인자와 ROS 2 파라미터로 노출해 상수로 숨기지 않는다.
DEFAULT_GOAL_TIMEOUT_SECONDS = 120.0

# 액션 서버 준비를 기다리며 전용 executor를 한 번 spin할 때의 대기 시간(초).
_SPIN_ONCE_TIMEOUT_SECONDS = 0.1

# 취소 요청을 보낸 뒤 취소 응답을 기다리는 최대 시간(초).
_CANCEL_RESULT_WAIT_SECONDS = 5.0

# 현재 위치(TF map->base_link)를 기다리는 최대 시간(초). 지그재그는 출발점을
# 알아야 그릴 수 있는데, 이걸 위해 주행 예산을 크게 쓰면 안 된다. 못 얻으면
# 지그재그를 포기하고 평소의 직선 주행으로 내려간다.
_POSE_LOOKUP_TIMEOUT_SECONDS = 2.0


class Nav2RobotDriver(RobotDriver):
    """NAVIGATE 명령을 Nav2 NavigateToPose 주행으로 실행하는 드라이버.

    역할: 목적지 이름을 웨이포인트 좌표로 바꿔 Nav2에 목표를 보내고, 도착
        여부에 따라 계약 상태(ARRIVED/FAILED)를 돌려준다.
    입력값(생성자): navigation_node - 드라이버 전용 ROS 2 노드. action_client -
        NavigateToPose 액션 클라이언트. executor - 전용 SingleThreadedExecutor
        (navigation_node가 추가된 상태). waypoint_file - room_waypoints.yaml
        경로. frame_id - 목표 pose의 좌표계(기본 "map"). goal_timeout_seconds -
        도착 대기 최대 시간(초).

    스레드 모델 (v1 개편에서 변경)
        navigate()/speak() 는 브릿지의 **워커 스레드**에서, cancel() 은 **수신
        (paho 콜백) 스레드**에서 불린다 — 그래야 주행 중에 CANCEL 이 실제로
        목표를 멈출 수 있다. 규칙은 하나다: **spin 은 오직 navigate() 를 부른
        스레드에서만 한다.** cancel() 은 취소 요청을 던지기만 하고(spin 없음),
        그 응답은 navigate() 쪽 spin 루프가 처리한다. 같은 executor 를 두
        스레드가 spin 하는 순간 rclpy 가 깨진다 — 그 금지가 이 설계의 전부다.
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
        through_poses_client: Any | None = None,
        tf_buffer: Any | None = None,
        base_frame_id: str = "base_link",
        zigzag_enabled: bool = False,
        zigzag_angle_deg: float = DEFAULT_ZIGZAG_ANGLE_DEG,
        zigzag_leg_length_m: float = DEFAULT_ZIGZAG_LEG_LENGTH_M,
        zigzag_min_distance_m: float = DEFAULT_ZIGZAG_MIN_DISTANCE_M,
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

        # 현관 지그재그 접근. 킬 스위치가 기본 꺼짐인 이유는 approach·search 와
        # 같다(CLAUDE.md §5) — 실기에서 처음 검증되는 동작이라, 이상하면
        # 파라미터 하나로 검증된 직선 주행으로 되돌릴 수 있어야 한다.
        # through_poses_client 나 tf_buffer 가 없으면(단위 테스트의 Fake 주입
        # 경로) 켜져 있어도 지그재그를 시도하지 않는다.
        self._through_poses_client = through_poses_client
        self._tf_buffer = tf_buffer
        self._base_frame_id = base_frame_id
        self._zigzag_enabled = zigzag_enabled
        self._zigzag_angle_deg = float(zigzag_angle_deg)
        self._zigzag_leg_length_m = float(zigzag_leg_length_m)
        self._zigzag_min_distance_m = float(zigzag_min_distance_m)

        # 진행 중인 Nav2 목표 핸들. 목표가 없으면 None이다. 완료/실패/취소 시
        # 반드시 None으로 정리해 다음 명령에서 재사용되지 않게 한다.
        # cancel()(수신 스레드)과 navigate()(워커 스레드)가 함께 만지므로
        # 락으로 보호한다.
        self._active_goal_handle: Any | None = None
        self._goal_lock = threading.Lock()

        # 브릿지가 실패 결과의 reasonCode 로 읽어 가는 값(선택 규약).
        # 실패 지점마다 백엔드 허용 enum(contract.REASON_*) 중 가장 가까운
        # 원인을 남긴다 — 백엔드는 enum 밖 값을 통째로 폐기하므로 자유 문장을
        # 넣으면 안 된다.
        self.last_reason_code: str | None = None

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
        self.last_reason_code = None

        waypoint_name = resolve_waypoint_name(target)
        if waypoint_name is None:
            self._logger.warning(
                f"Unsupported navigation target '{target}'; "
                "not sending a Nav2 goal"
            )
            self.last_reason_code = contract.REASON_UNKNOWN_TARGET
            return contract.STATUS_FAILED

        try:
            waypoint = load_waypoint(self._waypoint_file, waypoint_name)
        except Exception as error:
            # 파일 없음, 잘못된 YAML, 이름 누락 등 어떤 로딩 실패든 성공으로
            # 처리하지 않고 원인을 남긴 뒤 FAILED로 돌려준다.
            self._logger.error(
                f"Failed to load waypoint '{waypoint_name}': {error}"
            )
            self.last_reason_code = contract.REASON_INTERNAL_ERROR
            return contract.STATUS_FAILED

        try:
            return self._navigate_to_waypoint(waypoint, target)
        except Exception as error:
            # 예외가 실행 스레드로 새어 나가 브릿지 전체를 멈추지 않도록
            # 드라이버 경계에서 잡는다. 원인을 남기고 진행 중 목표를 정리한다.
            self._logger.error(
                f"Navigation failed with an unexpected error: {error}"
            )
            self._cancel_active_goal_quietly()
            self.last_reason_code = contract.REASON_INTERNAL_ERROR
            return contract.STATUS_FAILED

    def speak(self, text: str) -> str:
        """이 드라이버는 발화를 지원하지 않으므로 FAILED를 반환한다.

        Nav2 드라이버는 주행만 담당한다. SPEAK 실행 수단이 없으므로 가짜
        성공(DONE) 대신 FAILED를 돌려주고 그 사실을 로그로 남긴다.

        last_reason_code 를 여기서 명시적으로 설정한다 — 안 하면 직전
        navigate() 호출이 남긴 값을 브릿지가 잘못 읽어 갈 수 있다(이 값은
        navigate() 진입 시에만 초기화되고 speak() 는 건드리지 않았었다).
        """
        self._logger.warning(
            "Nav2RobotDriver does not support speak; reporting FAILED"
        )
        self.last_reason_code = contract.REASON_INTERNAL_ERROR
        return contract.STATUS_FAILED

    def cancel(self) -> str:
        """진행 중인 Nav2 목표가 있으면 취소를 요청하고 CANCELLED를 반환한다.

        ★ 다른 스레드(수신 스레드)에서 불린다. 여기서는 취소 요청을 **던지기만**
        하고 spin 하지 않는다 — 응답 처리와 결과 정리는 navigate() 를 돌리고
        있는 워커 스레드의 spin 루프 몫이다. 그래서 이 함수는 즉시 돌아오고,
        주행 중이던 navigate() 는 목표가 CANCELED 로 끝나는 것을 보고
        STATUS_CANCELLED 를 반환하게 된다.

        반환값: 항상 contract.STATUS_CANCELLED.
        실패: 취소 요청 자체가 실패해도 예외를 밖으로 던지지 않고 로그만 남긴다.
        """
        with self._goal_lock:
            goal_handle = self._active_goal_handle
        if goal_handle is None:
            self._logger.info(
                "Cancel requested but no navigation goal is active"
            )
            return contract.STATUS_CANCELLED

        try:
            # fire-and-forget. 취소 응답 future 는 워커의 spin 이 소화한다.
            goal_handle.cancel_goal_async()
            self._logger.info("Cancel request sent for the active goal")
        except Exception as error:
            self._logger.warning(f"Failed to send cancel request: {error}")
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

    def _navigate_to_waypoint(self, waypoint: Waypoint, target: str) -> str:
        """웨이포인트 하나로 Nav2 목표를 보내고 도착 결과를 기다린다.

        현관이면 먼저 지그재그 경유 좌표를 만들어 보고, 만들어졌으면
        NavigateThroughPoses 로 그 경로를 지나가게 한다. 그 밖의 모든 경우는
        지금까지와 똑같이 NavigateToPose 목표 하나다.
        """
        deadline = time.monotonic() + self._goal_timeout_seconds

        zigzag_poses = self._build_zigzag_poses(waypoint, target)
        client = (
            self._through_poses_client if zigzag_poses else self._action_client
        )

        if not self._wait_for_action_server(client, deadline):
            self._logger.error(
                "Nav2 action server was not available before timeout"
            )
            self.last_reason_code = contract.REASON_EXECUTION_TIMEOUT
            return contract.STATUS_FAILED

        if zigzag_poses:
            goal_message = NavigateThroughPoses.Goal()
            goal_message.poses = zigzag_poses
            self._logger.info(
                f"Sending Nav2 zigzag goal: {waypoint.name} "
                f"({len(zigzag_poses)} poses, "
                f"±{self._zigzag_angle_deg:.0f}°)"
            )
        else:
            goal_message = NavigateToPose.Goal()
            goal_message.pose = self._create_goal_pose(waypoint)
            self._logger.info(f"Sending Nav2 goal: {waypoint.name}")

        send_goal_future = client.send_goal_async(goal_message)

        if not self._spin_until_complete(send_goal_future, deadline):
            self._logger.error(
                "Timed out while waiting for the goal to be accepted"
            )
            self.last_reason_code = contract.REASON_EXECUTION_TIMEOUT
            return contract.STATUS_FAILED

        goal_handle = send_goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self._logger.warning("Nav2 rejected the navigation goal")
            self.last_reason_code = contract.REASON_INTERNAL_ERROR
            return contract.STATUS_FAILED

        with self._goal_lock:
            self._active_goal_handle = goal_handle
        result_future = goal_handle.get_result_async()

        if not self._spin_until_complete(result_future, deadline):
            self._logger.error(
                "Navigation did not finish before timeout; cancelling goal"
            )
            self._cancel_active_goal_quietly()
            self.last_reason_code = contract.REASON_EXECUTION_TIMEOUT
            return contract.STATUS_FAILED

        # 결과를 받았으므로 진행 중 목표를 정리한다.
        with self._goal_lock:
            self._active_goal_handle = None

        result = result_future.result()
        if result is None:
            self._logger.error("Navigation result was empty")
            self.last_reason_code = contract.REASON_INTERNAL_ERROR
            return contract.STATUS_FAILED

        if result.status == GoalStatus.STATUS_SUCCEEDED:
            self._logger.info(f"Navigation succeeded: reached {waypoint.name}")
            return contract.STATUS_ARRIVED

        if result.status == GoalStatus.STATUS_CANCELED:
            # 수신 스레드의 cancel() 이 요청한 취소가 여기서 관측된다.
            # 브릿지가 outcome=CANCELLED 로 번역한다.
            self._logger.info("Navigation goal was cancelled")
            return contract.STATUS_CANCELLED

        # ABORTED 등 — Nav2 가 목표를 포기한 경우다. 가장 흔한 원인은 경로
        # 계획 실패(장애물·미지 영역)라 PATH_BLOCKED 로 보고한다.
        self._logger.warning(
            f"Navigation finished without success: status={result.status}"
        )
        self.last_reason_code = contract.REASON_PATH_BLOCKED
        return contract.STATUS_FAILED

    def _wait_for_action_server(self, client: Any, deadline: float) -> bool:
        """전용 executor를 spin하며 액션 서버가 준비될 때까지 기다린다."""
        while not client.server_is_ready():
            if time.monotonic() >= deadline:
                return False
            self._executor.spin_once(timeout_sec=_SPIN_ONCE_TIMEOUT_SECONDS)
        return True

    def _build_zigzag_poses(
        self, waypoint: Waypoint, target: str
    ) -> list[PoseStamped]:
        """현관이면 지그재그 경유 PoseStamped 목록을, 아니면 빈 목록을 만든다.

        빈 목록은 "지그재그 없이 평소대로 가라"는 뜻이다. 아래 어느 조건에서든
        조용히 빈 목록으로 내려간다 — 애교는 있으면 좋은 것이지, 이것 때문에
        귀가 대본이 실패해서는 안 된다.

        * 킬 스위치가 꺼져 있다(기본값).
        * 목적지가 현관이 아니다.
        * NavigateThroughPoses 클라이언트나 TF 버퍼가 없다(단위 테스트의
          Fake 주입 경로).
        * 현재 위치를 제때 얻지 못했다(TF 미준비).
        * 거리가 짧아 zigzag_path 가 목표 하나만 돌려줬다.
        """
        if not self._zigzag_enabled:
            return []
        if target != contract.TARGET_ENTRANCE:
            return []
        if self._through_poses_client is None or self._tf_buffer is None:
            return []

        current = self._current_pose()
        if current is None:
            self._logger.warning(
                "Could not read the current pose; "
                "falling back to a straight approach"
            )
            return []

        try:
            path = zigzag_path(
                current[0],
                current[1],
                waypoint.x,
                waypoint.y,
                waypoint.yaw,
                angle_deg=self._zigzag_angle_deg,
                leg_length_m=self._zigzag_leg_length_m,
                min_distance_m=self._zigzag_min_distance_m,
            )
        except ValueError as error:
            # 잘못된 파라미터는 설정 실수다. 주행을 막지 않고 직선으로 간다.
            self._logger.warning(f"Zigzag parameters are invalid: {error}")
            return []

        # 목표 하나뿐이면 지그재그가 아니다 — 평소 경로로 보내는 편이
        # NavigateToPose 한 번으로 끝나 더 단순하다.
        if len(path) <= 1:
            return []

        return [
            self._create_pose_stamped(pose.x, pose.y, pose.yaw)
            for pose in path
        ]

    def _current_pose(self) -> tuple[float, float] | None:
        """TF map->base_link 로 현재 위치를 읽는다. 못 얻으면 None.

        /amcl_pose 구독이 아니라 TF 를 쓰는 이유: AMCL 은 갱신 임계값을 넘을
        때만 pose 를 발행하므로 로봇이 서 있는 동안에는 한참 조용할 수 있다.
        반면 map->odom(AMCL)과 odom->base_link(EKF) 변환은 계속 발행되므로
        멈춰 있어도 언제나 읽힌다.
        """
        deadline = time.monotonic() + _POSE_LOOKUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                transform = self._tf_buffer.lookup_transform(
                    self._frame_id, self._base_frame_id, Time())
            except Exception:  # noqa: BLE001 - TF 미준비는 정상 상황이다
                # 버퍼를 채우려면 spin 해야 한다. 여기서 도는 executor 는
                # 드라이버 전용이라 상위 노드와 부딪히지 않는다.
                self._executor.spin_once(
                    timeout_sec=_SPIN_ONCE_TIMEOUT_SECONDS)
                continue
            translation = transform.transform.translation
            return (translation.x, translation.y)

        # 원인은 호출자가 경고로 남긴다 — 여기서 또 남기면 2초 동안 쌓인
        # 같은 실패가 로그를 덮는다.
        return None

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
        """진행 중 목표가 있으면 조용히 취소를 요청하고 핸들을 정리한다.

        navigate() 를 부른 스레드(= spin 을 소유한 스레드)에서만 호출한다.
        여기서는 취소 응답을 짧게 기다려도 안전하다.
        """
        with self._goal_lock:
            goal_handle = self._active_goal_handle
            self._active_goal_handle = None
        if goal_handle is None:
            return
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
        return self._create_pose_stamped(
            waypoint.x, waypoint.y, waypoint.yaw)

    def _create_pose_stamped(
        self, x: float, y: float, yaw: float
    ) -> PoseStamped:
        """좌표 셋을 Nav2 PoseStamped로 채운다(경유점·목표 공용)."""
        pose = PoseStamped()
        pose.header.frame_id = self._frame_id
        pose.header.stamp = self._navigation_node.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y

        qx, qy, qz, qw = yaw_to_quaternion(yaw)
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
    through_poses_action_name: str = "navigate_through_poses",
    base_frame_id: str = "base_link",
    zigzag_enabled: bool = False,
    zigzag_angle_deg: float = DEFAULT_ZIGZAG_ANGLE_DEG,
    zigzag_leg_length_m: float = DEFAULT_ZIGZAG_LEG_LENGTH_M,
    zigzag_min_distance_m: float = DEFAULT_ZIGZAG_MIN_DISTANCE_M,
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

    # 지그재그를 쓸 때만 필요한 자원이다. 꺼져 있으면 만들지 않는다 — 액션
    # 클라이언트와 TF 리스너는 각각 구독을 열므로, 안 쓰는 기능이 토픽
    # 그래프에 나타나 있으면 실기에서 원인을 찾을 때 혼란만 준다.
    through_poses_client = None
    tf_buffer = None
    if zigzag_enabled:
        through_poses_client = ActionClient(
            navigation_node, NavigateThroughPoses, through_poses_action_name)
        tf_buffer = Buffer()
        # TransformListener 는 생성만으로 navigation_node 에 구독을 건다.
        # 참조를 노드에 붙여 두지 않으면 GC 되어 버퍼가 채워지지 않는다.
        navigation_node._bomi_tf_listener = TransformListener(  # noqa: SLF001
            tf_buffer, navigation_node, spin_thread=False)

    return Nav2RobotDriver(
        navigation_node=navigation_node,
        action_client=action_client,
        executor=executor,
        waypoint_file=resolved_waypoint_file,
        frame_id=frame_id,
        goal_timeout_seconds=goal_timeout_seconds,
        through_poses_client=through_poses_client,
        tf_buffer=tf_buffer,
        base_frame_id=base_frame_id,
        zigzag_enabled=zigzag_enabled,
        zigzag_angle_deg=zigzag_angle_deg,
        zigzag_leg_length_m=zigzag_leg_length_m,
        zigzag_min_distance_m=zigzag_min_distance_m,
    )
