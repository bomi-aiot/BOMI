"""저장된 웨이포인트를 한 바퀴 순찰하며 사용자를 탐색한다."""

from __future__ import annotations

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
from std_msgs.msg import Bool, String

from core.person_search_state_machine import (
    PersonSearchState,
    PersonSearchStateMachine,
    parse_person_detection,
)
from core.waypoint_route import (
    Waypoint,
    WaypointConfigError,
    load_patrol_route,
    yaw_to_quaternion,
)


class PersonSearchPatrol(Node):
    """Nav2 순찰 중 사람을 찾으면 목표를 취소하고 추종을 활성화한다."""

    def __init__(self) -> None:
        """탐색 경로, ROS 인터페이스와 안전한 초기 상태를 준비한다."""
        super().__init__("person_search_patrol")
        self._declare_parameters()

        waypoint_file = self._get_waypoint_file()
        route = load_patrol_route(waypoint_file)
        self._waypoints = route.waypoints
        self._waypoint_delay_sec = route.waypoint_delay_sec
        self._current_index = 0
        self._frame_id = str(self.get_parameter("frame_id").value)
        self._machine = PersonSearchStateMachine(
            float(self.get_parameter("target_confirm_sec").value)
        )
        self._start_requested = bool(
            self.get_parameter("start_automatically").value
        )
        self._goal_handle = None
        self._goal_send_pending = False
        self._cancel_when_accepted = False
        self._nav2_state_pending = False
        self._waypoint_timer = None

        self._action_client = ActionClient(
            self,
            NavigateToPose,
            str(self.get_parameter("action_name").value),
        )
        self._navigator_state_client = self.create_client(
            GetState,
            str(self.get_parameter("navigator_state_service").value),
        )
        self._follow_publisher = self.create_publisher(
            Bool,
            str(self.get_parameter("follow_enable_topic").value),
            10,
        )
        self._status_publisher = self.create_publisher(
            String,
            str(self.get_parameter("status_topic").value),
            10,
        )
        self._vision_subscription = self.create_subscription(
            String,
            str(self.get_parameter("vision_topic").value),
            self._vision_callback,
            10,
        )
        self._enable_subscription = self.create_subscription(
            Bool,
            str(self.get_parameter("enable_topic").value),
            self._enable_callback,
            10,
        )
        self._start_timer = self.create_timer(0.5, self._check_start)

        self._publish_follow_enabled(False)
        self._publish_status(PersonSearchState.IDLE)
        self.get_logger().info(
            f"사용자 탐색 웨이포인트 {len(self._waypoints)}개를 로드했습니다: "
            f"{waypoint_file}"
        )

    def _declare_parameters(self) -> None:
        """사용자 탐색 노드의 ROS 파라미터를 선언한다."""
        self.declare_parameter("waypoint_file", "")
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("action_name", "navigate_to_pose")
        self.declare_parameter("navigator_state_service", "/bt_navigator/get_state")
        self.declare_parameter("vision_topic", "/vision/follow_result")
        self.declare_parameter("follow_enable_topic", "/person_following/enable")
        self.declare_parameter("enable_topic", "/person_search/enable")
        self.declare_parameter("status_topic", "/person_search/status")
        self.declare_parameter("target_confirm_sec", 0.5)
        self.declare_parameter("start_automatically", True)

    def _enable_callback(self, message: Bool) -> None:
        """외부의 탐색 시작 또는 취소 요청을 처리한다."""
        if message.data:
            if self._machine.state in {
                PersonSearchState.PATROLLING,
                PersonSearchState.CANCELING_NAV2,
                PersonSearchState.FOLLOWING,
            }:
                return
            self._start_requested = True
            self._current_index = 0
            return

        self._start_requested = False
        self._cancel_when_accepted = self._goal_send_pending
        self._machine.cancel()
        self._publish_follow_enabled(False)
        self._publish_status(PersonSearchState.CANCELLED)
        self._cancel_active_goal()

    def _check_start(self) -> None:
        """Nav2가 활성 상태가 되면 요청된 사용자 탐색을 시작한다."""
        if not self._start_requested or self._machine.state not in {
            PersonSearchState.IDLE,
            PersonSearchState.NOT_FOUND,
            PersonSearchState.FAILED,
            PersonSearchState.CANCELLED,
        }:
            return
        if (
            self._nav2_state_pending
            or not self._navigator_state_client.service_is_ready()
        ):
            return
        self._nav2_state_pending = True
        future = self._navigator_state_client.call_async(GetState.Request())
        future.add_done_callback(self._handle_nav2_state)

    def _handle_nav2_state(self, future) -> None:
        """활성화된 bt_navigator를 확인하고 첫 탐색 목표를 전송한다."""
        self._nav2_state_pending = False
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().warning(f"Nav2 상태 조회 실패: {error}")
            return
        if response.current_state.id != State.PRIMARY_STATE_ACTIVE:
            return
        if not self._action_client.wait_for_server(timeout_sec=0.0):
            return

        self._start_requested = False
        self._current_index = 0
        self._machine.start()
        self._publish_follow_enabled(False)
        self._publish_status(PersonSearchState.PATROLLING)
        self._send_current_goal()

    def _vision_callback(self, message: String) -> None:
        """연속된 단일 사람 감지를 확인하고 Nav2 목표 취소를 시작한다."""
        try:
            status, track_id = parse_person_detection(message.data)
        except ValueError as error:
            self.get_logger().warning(str(error))
            return
        now_sec = self.get_clock().now().nanoseconds / 1_000_000_000.0
        decision = self._machine.observe(status, track_id, now_sec)
        if not decision.person_confirmed:
            return

        self.get_logger().info(
            f"사용자를 확인했습니다(track_id={decision.track_id}). Nav2 목표를 취소합니다."
        )
        self._publish_status(PersonSearchState.CANCELING_NAV2)
        if self._waypoint_timer is not None:
            self._waypoint_timer.cancel()
            self.destroy_timer(self._waypoint_timer)
            self._waypoint_timer = None
        if self._goal_handle is not None:
            self._cancel_active_goal(for_follow=True)
        elif self._goal_send_pending:
            self._cancel_when_accepted = True
        else:
            self._start_following()

    def _send_current_goal(self) -> None:
        """현재 순찰 지점을 Nav2 NavigateToPose 목표로 전송한다."""
        if self._machine.state != PersonSearchState.PATROLLING:
            return
        waypoint = self._waypoints[self._current_index]
        goal = NavigateToPose.Goal()
        goal.pose = self._create_pose(waypoint)
        self._goal_send_pending = True
        self.get_logger().info(
            f"탐색 목표 {self._current_index + 1}/{len(self._waypoints)}: {waypoint.name}"
        )
        future = self._action_client.send_goal_async(goal)
        future.add_done_callback(self._handle_goal_response)

    def _handle_goal_response(self, future) -> None:
        """Nav2 목표 수락 여부를 처리하고 완료 결과를 기다린다."""
        self._goal_send_pending = False
        try:
            self._goal_handle = future.result()
        except Exception as error:
            self._fail(f"Nav2 목표 전송 실패: {error}")
            return
        if self._goal_handle is None or not self._goal_handle.accepted:
            self._goal_handle = None
            self._fail("Nav2가 탐색 목표를 거부했습니다.")
            return
        if self._cancel_when_accepted:
            self._cancel_when_accepted = False
            self._cancel_active_goal(for_follow=True)
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_goal_result)

    def _handle_goal_result(self, future) -> None:
        """목표 도착 후 다음 지점으로 이동하거나 NOT_FOUND로 종료한다."""
        try:
            result = future.result()
        except Exception as error:
            if self._machine.state == PersonSearchState.PATROLLING:
                self._fail(f"Nav2 결과 수신 실패: {error}")
            return
        self._goal_handle = None
        if self._machine.state == PersonSearchState.CANCELING_NAV2:
            if result.status == GoalStatus.STATUS_CANCELED:
                self._start_following()
            else:
                self._fail(
                    f"Nav2가 취소 상태로 끝나지 않았습니다: status={result.status}"
                )
            return
        if self._machine.state != PersonSearchState.PATROLLING:
            return
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            self._fail(f"Nav2 탐색 목표 실패: status={result.status}")
            return

        waypoint_name = self._waypoints[self._current_index].name
        self.get_logger().info(f"탐색 지점 도착: {waypoint_name}")
        if self._waypoint_delay_sec > 0.0:
            self._waypoint_timer = self.create_timer(
                self._waypoint_delay_sec,
                self._continue_after_waypoint,
            )
        else:
            self._continue_after_waypoint()

    def _continue_after_waypoint(self) -> None:
        """지점 관측 대기 후 다음 목표 또는 탐색 종료를 선택한다."""
        if self._waypoint_timer is not None:
            self._waypoint_timer.cancel()
            self.destroy_timer(self._waypoint_timer)
            self._waypoint_timer = None
        if self._machine.state != PersonSearchState.PATROLLING:
            return
        if self._current_index + 1 >= len(self._waypoints):
            self._machine.complete_without_person()
            self._publish_follow_enabled(False)
            self._publish_status(PersonSearchState.NOT_FOUND)
            self.get_logger().info("모든 웨이포인트를 확인했지만 사용자를 찾지 못했습니다.")
            return
        self._current_index += 1
        self._send_current_goal()

    def _cancel_active_goal(self, *, for_follow: bool = False) -> None:
        """진행 중인 Nav2 목표를 비동기로 취소한다."""
        if self._goal_handle is None:
            if for_follow:
                self._start_following()
            return
        future = self._goal_handle.cancel_goal_async()
        if for_follow:
            future.add_done_callback(self._handle_cancel_for_follow)

    def _handle_cancel_for_follow(self, future) -> None:
        """Nav2 취소 응답을 확인한 뒤 사람 추종을 활성화한다."""
        try:
            response = future.result()
        except Exception as error:
            self._fail(f"Nav2 목표 취소 실패: {error}")
            return
        if not response.goals_canceling:
            self._fail("Nav2가 목표 취소를 승인하지 않았습니다.")
            return
        self.get_logger().info("Nav2 목표 취소가 승인되어 완료 결과를 기다립니다.")

    def _start_following(self) -> None:
        """Nav2가 멈춘 뒤 사람 추종 스위치를 켠다."""
        decision = self._machine.nav2_cancelled()
        if decision.state != PersonSearchState.FOLLOWING:
            return
        self._publish_follow_enabled(True)
        self._publish_status(PersonSearchState.FOLLOWING)
        self.get_logger().info("Nav2 취소 완료, 사람 추종을 시작합니다.")

    def _fail(self, reason: str) -> None:
        """탐색을 실패 처리하고 추종을 끈 채 안전하게 정지한다."""
        self._machine.fail(reason)
        if self._waypoint_timer is not None:
            self._waypoint_timer.cancel()
            self.destroy_timer(self._waypoint_timer)
            self._waypoint_timer = None
        self._cancel_active_goal()
        self._publish_follow_enabled(False)
        self._publish_status(PersonSearchState.FAILED)
        self.get_logger().error(reason)

    def _publish_follow_enabled(self, enabled: bool) -> None:
        message = Bool()
        message.data = enabled
        self._follow_publisher.publish(message)

    def _publish_status(self, state: PersonSearchState) -> None:
        message = String()
        message.data = state.value
        self._status_publisher.publish(message)

    def _create_pose(self, waypoint: Waypoint) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = self._frame_id
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

    def destroy_node(self) -> bool:
        """종료 시 추종을 끄고 진행 중인 Nav2 목표를 취소한다."""
        self._publish_follow_enabled(False)
        self._cancel_active_goal()
        return super().destroy_node()


def main(args=None) -> None:
    """웨이포인트 사용자 탐색 ROS 2 노드를 실행한다."""
    rclpy.init(args=args)
    try:
        node = PersonSearchPatrol()
    except (ValueError, WaypointConfigError) as error:
        temp_node = Node("person_search_patrol_config_error")
        temp_node.get_logger().error(f"사용자 탐색 설정 오류: {error}")
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
