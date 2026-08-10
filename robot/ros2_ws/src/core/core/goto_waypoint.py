r"""이름으로 지정한 웨이포인트 한 곳으로 한 번만 주행한다.

순찰(``nav2_waypoint_patrol``)은 YAML의 모든 지점을 순서대로 돌기 때문에
"현관 좌표를 찍고 바로 거기로 가는지 확인"하는 용도로는 쓸 수 없다. 이
노드는 같은 ``room_waypoints.yaml``을 읽되 이름으로 한 지점만 골라 Nav2
목표를 한 번 보내고, 도착하거나 실패하면 바로 종료한다. 좌표를 고친 뒤
결과를 즉시 눈으로 확인하는 것이 목적이다.

MQTT 브릿지나 백엔드 계약과는 무관하다. 실물에서 좌표 자체가 맞는지
먼저 분리해서 확인하고, 그다음에 브릿지 경로를 붙이기 위한 도구다.

실행 예 (소스 트리의 YAML을 그대로 가리키면 다시 빌드하지 않아도 된다):

    ros2 run core goto_waypoint --ros-args \\
        -p waypoint_name:=entrance \\
        -p waypoint_file:=/절대/경로/room_waypoints.yaml
"""

from pathlib import Path
import sys

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node

from core.waypoint_route import (
    Waypoint,
    WaypointConfigError,
    load_patrol_route,
    yaw_to_quaternion,
)


def select_waypoint(
    waypoints: list[Waypoint],
    waypoint_name: str,
) -> Waypoint:
    """웨이포인트 목록에서 이름이 일치하는 하나를 고른다.

    역할: 이름으로 지점을 찾고, 없으면 고를 수 있는 이름을 알려주는
        오류를 낸다.
    입력값: waypoints - YAML에서 읽은 지점 목록. waypoint_name - 찾을
        이름.
    반환값: 이름이 일치하는 Waypoint.
    실패: 이름이 목록에 없으면 WaypointConfigError를 던진다. 오타로
        엉뚱한 곳에 주행하는 것보다 멈추는 편이 안전하므로 대체 지점을
        임의로 고르지 않는다.
    """
    for waypoint in waypoints:
        if waypoint.name == waypoint_name:
            return waypoint

    available = ", ".join(waypoint.name for waypoint in waypoints)
    raise WaypointConfigError(
        f"'{waypoint_name}' 웨이포인트가 없다. 사용 가능: {available}"
    )


class GotoWaypoint(Node):
    """지정한 웨이포인트로 Nav2 목표를 한 번 보내고 종료하는 노드."""

    def __init__(self) -> None:
        """설정을 읽고 Nav2 액션 클라이언트를 준비한다."""
        super().__init__("goto_waypoint")

        self.declare_parameter("waypoint_file", "")
        self.declare_parameter("waypoint_name", "entrance")
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("action_name", "navigate_to_pose")
        self.declare_parameter(
            "navigator_state_service",
            "/bt_navigator/get_state",
        )
        self.declare_parameter("wait_timeout_sec", 30.0)

        # 상태 조회 하나가 이 시간 안에 안 오면 유실로 보고 다시 건다.
        # wait_timeout_sec 보다 충분히 짧아야 재시도할 여유가 생긴다.
        self.declare_parameter("state_request_timeout_sec", 5.0)

        waypoint_file = self._get_waypoint_file()
        self.frame_id = self.get_parameter("frame_id").value
        waypoint_name = str(self.get_parameter("waypoint_name").value)
        action_name = self.get_parameter("action_name").value
        navigator_state_service = self.get_parameter(
            "navigator_state_service"
        ).value
        self.wait_timeout_sec = float(
            self.get_parameter("wait_timeout_sec").value
        )
        self.state_request_timeout_sec = float(
            self.get_parameter("state_request_timeout_sec").value
        )

        route = load_patrol_route(waypoint_file)
        self.waypoint = select_waypoint(route.waypoints, waypoint_name)

        self.action_client = ActionClient(
            self,
            NavigateToPose,
            action_name,
        )
        self.navigator_state_client = self.create_client(
            GetState,
            str(navigator_state_service),
        )
        self.active_goal_handle = None
        self.nav2_state_request_pending = False
        self.state_request_pending_sec = 0.0
        self.last_nav2_state_id = None
        self.finished = False
        self.arrived = False
        self.waited_sec = 0.0
        self.warned_action_server_missing = False

        self.start_timer = self.create_timer(1.0, self.wait_for_nav2)
        self.get_logger().info(f"waypoint_file={waypoint_file}")
        self.get_logger().info(
            f"목표 지점: {self.waypoint.name} "
            f"(x={self.waypoint.x:.3f}, y={self.waypoint.y:.3f}, "
            f"yaw={self.waypoint.yaw:.3f})"
        )
        self.get_logger().info("Nav2 bt_navigator 활성화 대기 중")

    def wait_for_nav2(self) -> None:
        """Nav2 활성 상태를 비동기로 조회하고 대기 시간을 제한한다."""
        # 대기 시간은 조회가 밀려 있든 말든 먼저 센다. 예전에는 pending
        # 검사를 먼저 해서, 응답이 한 번 유실되면 플래그가 영원히 True로
        # 남고 이 카운터가 아예 안 올라갔다. 그러면 타임아웃 에러조차 못
        # 찍고 바깥의 timeout 명령에 잘릴 때까지 조용히 매달린다.
        # 2026-08-07 실기에서 실제로 그랬다 — bt_navigator 는 active 인데
        # "활성화 대기 중"만 찍고 200초를 버린 뒤 주행 실패로 끝났다.
        self.waited_sec += 1.0

        if self.waited_sec > self.wait_timeout_sec:
            self.start_timer.cancel()
            self.get_logger().error(
                f"Nav2가 {self.wait_timeout_sec:g}초 안에 활성화되지 "
                "않았다. bringup launch가 떠 있는지 확인하라"
            )
            self.finished = True
            return

        if self.nav2_state_request_pending:
            # 응답이 오지 않는 요청에 계속 매달리지 않는다. 몇 초 안에
            # 안 오면 유실로 보고 다시 건다.
            self.state_request_pending_sec += 1.0

            if (
                self.state_request_pending_sec
                < self.state_request_timeout_sec
            ):
                return

            self.get_logger().warning(
                "Nav2 상태 조회에 응답이 없어 다시 건다 "
                f"({self.state_request_pending_sec:g}초 대기)"
            )
            self.nav2_state_request_pending = False

        if not self.navigator_state_client.service_is_ready():
            return

        self.nav2_state_request_pending = True
        self.state_request_pending_sec = 0.0
        state_future = self.navigator_state_client.call_async(
            GetState.Request()
        )
        state_future.add_done_callback(self._handle_nav2_state)

    def _handle_nav2_state(self, future) -> None:
        """bt_navigator가 active이고 액션 서버가 준비되면 목표를 보낸다."""
        self.nav2_state_request_pending = False

        try:
            response = future.result()
        except Exception as error:
            self.get_logger().warning(
                f"Nav2 상태 조회 실패: {error}"
            )
            return

        state = response.current_state
        if state.id != State.PRIMARY_STATE_ACTIVE:
            if state.id != self.last_nav2_state_id:
                self.get_logger().info(
                    f"Nav2 상태 대기: {state.label}"
                )
                self.last_nav2_state_id = state.id
            return

        if not self.action_client.wait_for_server(timeout_sec=0.0):
            # 이 경로는 조용히 되돌아가므로, 한 번은 반드시 알려야 한다.
            # 그러지 않으면 "Nav2는 active인데 액션 서버만 없는" 상태와
            # "상태 서비스조차 못 찾은" 상태를 로그로 구분할 수 없다.
            if not self.warned_action_server_missing:
                self.warned_action_server_missing = True
                self.get_logger().info(
                    "bt_navigator는 active인데 navigate_to_pose 액션 "
                    "서버를 아직 못 찾았다. 계속 기다린다"
                )
            return

        self.start_timer.cancel()
        self.get_logger().info("Nav2 bt_navigator 활성화 완료")
        self._send_goal()

    def _send_goal(self) -> None:
        goal = NavigateToPose.Goal()
        goal.pose = self._create_pose(self.waypoint)

        self.get_logger().info(f"목표 전송: {self.waypoint.name}")
        send_future = self.action_client.send_goal_async(goal)
        send_future.add_done_callback(self._handle_goal_response)

    def _handle_goal_response(self, future) -> None:
        self.active_goal_handle = future.result()

        if (
            self.active_goal_handle is None
            or not self.active_goal_handle.accepted
        ):
            self.active_goal_handle = None
            self.get_logger().error(
                "Nav2가 목표를 거부했다. 좌표가 지도의 미탐색 영역이나 "
                "장애물 위인지 확인하라"
            )
            self.finished = True
            return

        result_future = self.active_goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_goal_result)

    def _handle_goal_result(self, future) -> None:
        result = future.result()
        self.active_goal_handle = None

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().error(
                f"주행 실패: status={result.status}"
            )
            self.finished = True
            return

        self.arrived = True
        self.finished = True
        self.get_logger().info(f"도착: {self.waypoint.name}")

    def destroy_node(self) -> bool:
        """종료 시 진행 중인 Nav2 목표 취소를 요청한다."""
        if self.active_goal_handle is not None:
            self.active_goal_handle.cancel_goal_async()

        return super().destroy_node()

    def _create_pose(self, waypoint: Waypoint) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = str(self.frame_id)
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = waypoint.x
        pose.pose.position.y = waypoint.y

        qx, qy, qz, qw = yaw_to_quaternion(waypoint.yaw)
        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        pose.pose.orientation.w = qw

        return pose

    def _get_waypoint_file(self) -> Path:
        waypoint_file = self.get_parameter("waypoint_file").value
        if waypoint_file:
            return Path(str(waypoint_file)).expanduser()

        share_dir = Path(get_package_share_directory("core"))
        return share_dir / "config" / "room_waypoints.yaml"


def main(args=None) -> int:
    """지정한 웨이포인트로 한 번 주행하는 노드를 실행한다.

    도착했으면 0, 아니면 1을 돌려준다. 이 값이 그대로 프로세스 종료 코드가
    되므로 부르는 쪽 스크립트가 성패를 판단할 수 있다. 예전에는 항상 None을
    돌려줘 종료 코드가 늘 0이었고, Nav2가 목표를 중단(status=6)했는데도
    bomi_goto.sh 가 "2단계 완료"를 찍었다. 2026-08-07 실기에서 실제로 그랬다.
    """
    rclpy.init(args=args)

    try:
        node = GotoWaypoint()
    except WaypointConfigError as error:
        temp_node = Node("goto_waypoint_config_error")
        temp_node.get_logger().error(f"웨이포인트 설정 오류: {error}")
        temp_node.destroy_node()
        rclpy.shutdown()
        return 1

    # rclpy.spin_once 를 쓰면 호출마다 노드를 executor에 넣었다 빼기
    # 때문에, 액션 클라이언트가 서버를 찾는 중에 그래프 탐색이 계속
    # 끊긴다(실제로 wait_for_server가 영원히 False였다). executor를 한 번
    # 만들어 계속 spin해야 한다.
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    try:
        while rclpy.ok() and not node.finished:
            executor.spin_once(timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        arrived = node.arrived
        executor.remove_node(node)
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()

    return 0 if arrived else 1


if __name__ == "__main__":
    sys.exit(main())
