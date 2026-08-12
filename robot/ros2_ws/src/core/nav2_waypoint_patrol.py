"""순찰 지점을 Nav2 목표로 전달한다."""

from pathlib import Path

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from core.waypoint_route import (
    Waypoint,
    WaypointConfigError,
    load_patrol_route,
    yaw_to_quaternion,
)


class Nav2WaypointPatrol(Node):
    """YAML 지점을 읽고 Nav2 목표 pose를 전송하는 노드."""

    def __init__(self) -> None:
        """설정을 읽고 Nav2 액션 클라이언트를 준비한다."""
        super().__init__("nav2_waypoint_patrol")

        self.declare_parameter("waypoint_file", "")
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("action_name", "navigate_to_pose")
        self.declare_parameter(
            "navigator_state_service",
            "/bt_navigator/get_state",
        )

        waypoint_file = self._get_waypoint_file()
        self.frame_id = self.get_parameter("frame_id").value
        action_name = self.get_parameter("action_name").value
        navigator_state_service = self.get_parameter(
            "navigator_state_service"
        ).value

        self.route = load_patrol_route(waypoint_file)
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
        self.goal_in_progress = False
        self.nav2_state_request_pending = False
        self.last_nav2_state_id = None
        self.loop_delay_timer = None
        self.waypoint_delay_timer = None
        self.goal_retry_timer = None

        self.start_timer = self.create_timer(1.0, self.start_patrol)
        count = len(self.route.waypoints)
        self.get_logger().info(f"순찰 지점 {count}개 로드")
        self.get_logger().info(f"waypoint_file={waypoint_file}")
        self.get_logger().info("Nav2 bt_navigator 활성화 대기 중")

    def start_patrol(self) -> None:
        """Nav2 활성 상태를 비동기로 조회한다."""
        if self.nav2_state_request_pending:
            return

        if not self.navigator_state_client.service_is_ready():
            return

        self.nav2_state_request_pending = True
        state_future = self.navigator_state_client.call_async(
            GetState.Request()
        )
        state_future.add_done_callback(self._handle_nav2_state)

    def _handle_nav2_state(self, future) -> None:
        """bt_navigator가 active이고 액션 서버가 준비되면 순찰한다."""
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
            return

        self.start_timer.cancel()
        self.get_logger().info("Nav2 bt_navigator 활성화 완료")
        self._send_current_goal()

    def destroy_node(self) -> bool:
        """종료 시 진행 중인 Nav2 목표 취소를 요청한다."""
        if self.active_goal_handle is not None:
            self.active_goal_handle.cancel_goal_async()

        return super().destroy_node()

    def _send_current_goal(self) -> None:
        waypoint = self.route.current()
        if waypoint is None:
            self.get_logger().info("순찰 경로 완료")
            return

        goal = NavigateToPose.Goal()
        goal.pose = self._create_pose(waypoint)
        self.goal_in_progress = True

        self.get_logger().info(f"목표 전송: {waypoint.name}")
        send_future = self.action_client.send_goal_async(goal)
        send_future.add_done_callback(self._handle_goal_response)

    def _handle_goal_response(self, future) -> None:
        self.active_goal_handle = future.result()

        if (
            self.active_goal_handle is None
            or not self.active_goal_handle.accepted
        ):
            self.active_goal_handle = None
            self.goal_in_progress = False
            self._schedule_current_goal_retry(
                "Nav2가 목표를 거부함"
            )
            return

        result_future = self.active_goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_goal_result)

    def _handle_goal_result(self, future) -> None:
        result = future.result()
        self.goal_in_progress = False
        self.active_goal_handle = None

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            status = result.status
            self._schedule_current_goal_retry(
                f"Nav2 목표 실패: status={status}"
            )
            return

        completed_waypoint = self.route.current()
        if completed_waypoint is not None:
            self.get_logger().info(f"도착: {completed_waypoint.name}")

        completed_last_waypoint = (
            self.route.current_index == len(self.route.waypoints) - 1
        )

        self.route.move_to_next()

        waypoint_delay = self.route.waypoint_delay_sec

        if waypoint_delay > 0.0:
            waypoint_name = (
                completed_waypoint.name
                if completed_waypoint is not None
                else "현재 지점"
            )
            self.get_logger().info(
                f"{waypoint_name}에서 {waypoint_delay:g}초 대기"
            )
            self.waypoint_delay_timer = self.create_timer(
                waypoint_delay,
                lambda: self._resume_after_waypoint_delay(
                    completed_last_waypoint
                ),
            )
            return

        self._continue_after_waypoint(completed_last_waypoint)

    def _schedule_current_goal_retry(self, failure_reason: str) -> None:
        """거부되거나 실패한 현재 목표를 제한된 횟수로 재시도한다."""
        retry_number = self.route.record_goal_failure()
        max_retries = self.route.max_goal_retries

        if retry_number is None:
            self.get_logger().error(
                f"{failure_reason}, 재시도 {max_retries}회 소진. "
                "안전을 위해 현재 지점에서 순찰을 정지함"
            )
            return

        delay = self.route.goal_retry_delay_sec
        self.get_logger().warning(
            f"{failure_reason}, {delay:g}초 후 같은 지점 재시도 "
            f"({retry_number}/{max_retries})"
        )
        self.goal_retry_timer = self.create_timer(
            delay,
            self._retry_current_goal,
        )

    def _retry_current_goal(self) -> None:
        """재시도 대기가 끝나면 현재 지점을 다시 전송한다."""
        timer = self.goal_retry_timer
        self.goal_retry_timer = None

        if timer is not None:
            timer.cancel()
            self.destroy_timer(timer)

        self._send_current_goal()

    def _resume_after_waypoint_delay(
        self,
        completed_last_waypoint: bool,
    ) -> None:
        """지점 대기가 끝나면 다음 이동을 처리한다."""
        timer = self.waypoint_delay_timer
        self.waypoint_delay_timer = None

        if timer is not None:
            timer.cancel()
            self.destroy_timer(timer)

        self._continue_after_waypoint(completed_last_waypoint)

    def _continue_after_waypoint(
        self,
        completed_last_waypoint: bool,
    ) -> None:
        """다음 지점 이동 또는 순찰 반복 대기를 시작한다."""
        if (
            completed_last_waypoint
            and self.route.loop
            and self.route.loop_delay_sec > 0.0
        ):
            delay = self.route.loop_delay_sec
            self.get_logger().info(
                f"순찰 한 바퀴 완료, {delay:g}초 대기"
            )
            self.loop_delay_timer = self.create_timer(
                delay,
                self._resume_patrol_after_delay,
            )
            return

        self._send_current_goal()

    def _resume_patrol_after_delay(self) -> None:
        """대기 시간이 끝나면 다음 순찰을 시작한다."""
        timer = self.loop_delay_timer
        self.loop_delay_timer = None

        if timer is not None:
            timer.cancel()
            self.destroy_timer(timer)

        self.get_logger().info("다음 순찰 시작")
        self._send_current_goal()

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


def main(args=None) -> None:
    """Nav2 waypoint 순찰 노드를 실행한다."""
    rclpy.init(args=args)

    try:
        node = Nav2WaypointPatrol()
    except WaypointConfigError as error:
        temp_node = Node("nav2_waypoint_patrol_config_error")
        temp_node.get_logger().error(f"순찰 설정 오류: {error}")
        temp_node.destroy_node()
        rclpy.shutdown()
        return

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
