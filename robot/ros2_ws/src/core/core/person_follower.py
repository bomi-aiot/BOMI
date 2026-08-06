"""
비전 AI 결과와 LiDAR 거리를 사람 추종 속도 명령으로 변환한다.

비전 AI가 발행한 사람 추적 결과를 JSON 문자열로 구독한다.
사람 추종 상태 머신으로 이동 허용 여부를 판단하고, LiDAR의
사람 접근 거리와 긴급 장애물 거리를 함께 사용해 최종
geometry_msgs/Twist 명령을 생성한다.

여러 사람이 감지되면 즉시 정지하고, 다시 한 명만 감지되면
자동으로 추종을 재개한다.
"""

import json
import math
from typing import Any

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger

from core.follow_state_machine import (
    FollowState,
    FollowStateMachine,
    VisionTrackingStatus,
)
from core.person_following_controller import (
    PersonFollowingController,
    VelocityCommand,
)


class PersonFollower(Node):
    """비전 추적 결과를 안전한 사람 추종 속도로 변환하는 ROS2 노드."""

    def __init__(self) -> None:
        """파라미터, 상태 머신, 구독자, 발행자와 서비스를 생성한다."""
        super().__init__("person_follower")

        self._declare_parameters()

        input_topic = str(
            self.get_parameter("input_topic").value
        )
        output_topic = str(
            self.get_parameter("output_topic").value
        )
        scan_topic = str(
            self.get_parameter("scan_topic").value
        )

        self._command_timeout_sec = float(
            self.get_parameter("command_timeout_sec").value
        )
        self._lidar_timeout_sec = float(
            self.get_parameter("lidar_timeout_sec").value
        )
        self._use_lidar = bool(
            self.get_parameter("use_lidar").value
        )
        self._require_lidar_before_motion = bool(
            self.get_parameter(
                "require_lidar_before_motion"
            ).value
        )

        obstacle_half_angle_deg = float(
            self.get_parameter(
                "obstacle_check_half_angle_deg"
            ).value
        )
        person_half_angle_deg = float(
            self.get_parameter(
                "person_check_half_angle_deg"
            ).value
        )

        self._obstacle_half_angle_rad = math.radians(
            obstacle_half_angle_deg
        )
        self._person_half_angle_rad = math.radians(
            person_half_angle_deg
        )

        self._validate_node_parameters()

        self._state_machine = FollowStateMachine(
            multiple_observation_sec=float(
                self.get_parameter(
                    "multiple_observation_sec"
                ).value
            ),
            single_recovery_sec=float(
                self.get_parameter(
                    "single_recovery_sec"
                ).value
            ),
            lost_timeout_sec=float(
                self.get_parameter(
                    "lost_timeout_sec"
                ).value
            ),
            target_confirm_sec=float(
                self.get_parameter(
                    "target_confirm_sec"
                ).value
            ),
        )

        self._controller = PersonFollowingController(
            linear_speed=float(
                self.get_parameter("linear_speed").value
            ),
            angular_speed=float(
                self.get_parameter("angular_speed").value
            ),
            person_stop_distance_m=float(
                self.get_parameter(
                    "person_stop_distance_m"
                ).value
            ),
            person_resume_distance_m=float(
                self.get_parameter(
                    "person_resume_distance_m"
                ).value
            ),
            emergency_stop_distance_m=float(
                self.get_parameter(
                    "emergency_stop_distance_m"
                ).value
            ),
        )

        self._last_vision_time: Time | None = None
        self._last_scan_time: Time | None = None

        self._front_obstacle_distance_m: float | None = None
        self._front_person_distance_m: float | None = None
        self._last_scan_valid = False

        self._last_velocity = VelocityCommand(
            linear_x=0.0,
            angular_z=0.0,
            reason="node_started",
        )
        self._last_logged_state: FollowState | None = None

        self._vision_timeout_handled = True
        self._lidar_timeout_stop_sent = True

        self._velocity_publisher = self.create_publisher(
            Twist,
            output_topic,
            10,
        )

        self._vision_subscription = self.create_subscription(
            String,
            input_topic,
            self._vision_callback,
            10,
        )

        self._scan_subscription = self.create_subscription(
            LaserScan,
            scan_topic,
            self._scan_callback,
            qos_profile_sensor_data,
        )

        self._reset_lock_service = self.create_service(
            Trigger,
            "/person_following/reset_lock",
            self._reset_lock_callback,
        )

        self._safety_timer = self.create_timer(
            0.1,
            self._check_timeouts,
        )

        self.get_logger().info(
            "사람 추종 노드를 시작했습니다. "
            f"비전 입력={input_topic}, "
            f"LiDAR 입력={scan_topic}, "
            f"속도 출력={output_topic}"
        )

    def _declare_parameters(self) -> None:
        """사람 추종 동작에 사용하는 ROS2 파라미터를 선언한다."""
        self.declare_parameter(
            "input_topic",
            "/vision/follow_result",
        )
        self.declare_parameter(
            "output_topic",
            "/cmd_vel_follow",
        )
        self.declare_parameter(
            "scan_topic",
            "/scan",
        )

        self.declare_parameter(
            "linear_speed",
            0.15,
        )
        self.declare_parameter(
            "angular_speed",
            0.5,
        )

        self.declare_parameter(
            "command_timeout_sec",
            1.0,
        )
        self.declare_parameter(
            "multiple_observation_sec",
            3.0,
        )
        self.declare_parameter(
            "single_recovery_sec",
            1.0,
        )
        self.declare_parameter(
            "lost_timeout_sec",
            1.0,
        )
        self.declare_parameter(
            "target_confirm_sec",
            0.5,
        )

        self.declare_parameter(
            "use_lidar",
            True,
        )
        self.declare_parameter(
            "require_lidar_before_motion",
            True,
        )
        self.declare_parameter(
            "person_stop_distance_m",
            0.5,
        )
        self.declare_parameter(
            "person_resume_distance_m",
            1.0,
        )
        self.declare_parameter(
            "emergency_stop_distance_m",
            0.3,
        )
        self.declare_parameter(
            "obstacle_check_half_angle_deg",
            20.0,
        )
        self.declare_parameter(
            "person_check_half_angle_deg",
            8.0,
        )
        self.declare_parameter(
            "lidar_timeout_sec",
            0.5,
        )

    def _validate_node_parameters(self) -> None:
        """ROS2 노드에서 직접 사용하는 설정값을 검사한다."""
        if not self._is_positive_finite(
            self._command_timeout_sec
        ):
            raise ValueError(
                "command_timeout_sec는 유한한 양수여야 합니다."
            )

        if not self._is_positive_finite(
            self._lidar_timeout_sec
        ):
            raise ValueError(
                "lidar_timeout_sec는 유한한 양수여야 합니다."
            )

        if (
            not math.isfinite(self._obstacle_half_angle_rad)
            or not 0.0
            < self._obstacle_half_angle_rad
            <= math.pi
        ):
            raise ValueError(
                "obstacle_check_half_angle_deg의 범위가 "
                "올바르지 않습니다."
            )

        if (
            not math.isfinite(self._person_half_angle_rad)
            or not 0.0
            < self._person_half_angle_rad
            <= self._obstacle_half_angle_rad
        ):
            raise ValueError(
                "person_check_half_angle_deg는 0보다 크고 "
                "obstacle_check_half_angle_deg 이하여야 합니다."
            )

    def _vision_callback(self, message: String) -> None:
        """비전 JSON 결과를 상태 판단과 속도 계산에 반영한다."""
        now = self.get_clock().now()
        now_sec = self._time_to_sec(now)

        self._last_vision_time = now
        self._vision_timeout_handled = False

        try:
            payload = self._parse_vision_message(message.data)
        except ValueError as error:
            decision = self._state_machine.update(
                VisionTrackingStatus.INVALID,
                None,
                now_sec,
            )

            self._publish_stop("invalid_vision_message")

            self._log_state_change(
                decision.state,
                decision.reason,
                decision.target_track_id,
            )

            self.get_logger().warning(str(error))
            return

        decision = self._state_machine.update(
            status=payload["status"],
            track_id=payload["track_id"],
            now_sec=now_sec,
        )

        movement_allowed = decision.movement_allowed
        person_distance_m: float | None = None
        emergency_obstacle_distance_m: float | None = None
        node_stop_reason: str | None = None

        if self._use_lidar:
            if not self._lidar_is_ready(now):
                if self._require_lidar_before_motion:
                    movement_allowed = False
                    node_stop_reason = "lidar_not_ready"
            else:
                emergency_obstacle_distance_m = (
                    self._front_obstacle_distance_m
                )

                if payload["command"] == "move_forward":
                    person_distance_m = (
                        self._front_person_distance_m
                    )

        velocity = self._controller.calculate_velocity(
            command=payload["command"],
            movement_allowed=movement_allowed,
            person_distance_m=person_distance_m,
            emergency_obstacle_distance_m=(
                emergency_obstacle_distance_m
            ),
        )

        if node_stop_reason is not None:
            velocity = VelocityCommand(
                linear_x=0.0,
                angular_z=0.0,
                reason=node_stop_reason,
            )

        self._publish_velocity(velocity)

        self._log_state_change(
            decision.state,
            decision.reason,
            decision.target_track_id,
        )

        self.get_logger().debug(
            "비전 명령 처리: "
            f"status={payload['status']}, "
            f"command={payload['command']}, "
            f"track_id={payload['track_id']}, "
            f"person_distance={person_distance_m}, "
            f"obstacle_distance={emergency_obstacle_distance_m}, "
            f"linear.x={velocity.linear_x:.2f}, "
            f"angular.z={velocity.angular_z:.2f}, "
            f"reason={velocity.reason}"
        )

    def _scan_callback(self, message: LaserScan) -> None:
        """LiDAR에서 사람 접근 거리와 긴급 장애물 거리를 계산한다."""
        if not self._use_lidar:
            return

        now = self.get_clock().now()

        obstacle_scan_valid, obstacle_distance = (
            self._minimum_front_distance(
                message,
                self._obstacle_half_angle_rad,
            )
        )
        person_scan_valid, person_distance = (
            self._minimum_front_distance(
                message,
                self._person_half_angle_rad,
            )
        )

        self._last_scan_time = now
        self._last_scan_valid = (
            obstacle_scan_valid
            and person_scan_valid
        )
        self._front_obstacle_distance_m = obstacle_distance
        self._front_person_distance_m = person_distance

        if self._last_scan_valid:
            self._lidar_timeout_stop_sent = False
        elif (
            self._require_lidar_before_motion
            and not self._is_stopped(self._last_velocity)
        ):
            self._publish_stop("invalid_lidar_scan")
            self._lidar_timeout_stop_sent = True

            self.get_logger().warning(
                "유효하지 않은 LiDAR 데이터가 수신되어 "
                "로봇을 정지합니다."
            )
            return

        if not self._last_scan_valid:
            return

        if (
            obstacle_distance is not None
            and obstacle_distance
            <= self._controller.emergency_stop_distance_m
            and not self._is_stopped(self._last_velocity)
        ):
            velocity = self._controller.calculate_velocity(
                command="stop",
                movement_allowed=True,
                emergency_obstacle_distance_m=(
                    obstacle_distance
                ),
            )
            self._publish_velocity(velocity)

            self.get_logger().warning(
                "전방 장애물이 긴급 정지 거리 안에 감지되어 "
                f"즉시 정지합니다: {obstacle_distance:.2f} m"
            )
            return

        if (
            person_distance is not None
            and person_distance
            <= self._controller.person_stop_distance_m
            and self._last_velocity.linear_x > 0.0
        ):
            velocity = self._controller.calculate_velocity(
                command="stop",
                movement_allowed=True,
                person_distance_m=person_distance,
                emergency_obstacle_distance_m=(
                    obstacle_distance
                ),
            )
            self._publish_velocity(velocity)

            self.get_logger().info(
                "중앙 대상이 접근 정지 거리 안에 들어와 "
                f"정지합니다: {person_distance:.2f} m"
            )

    def _reset_lock_callback(
        self,
        request: Trigger.Request,
        response: Trigger.Response,
    ) -> Trigger.Response:
        """기존 클라이언트 호환을 위해 추종 잠금 초기화를 처리한다."""
        del request

        now_sec = self._time_to_sec(
            self.get_clock().now()
        )
        decision = self._state_machine.reset_lock(now_sec)

        if decision.reason != "following_lock_reset":
            response.success = False
            response.message = (
                "현재 다중 인물 잠금 상태가 아닙니다. "
                f"현재 상태: {decision.state.value}"
            )

            self.get_logger().info(response.message)
            return response

        self._publish_stop("following_lock_reset")
        self._vision_timeout_handled = True

        self._log_state_change(
            decision.state,
            decision.reason,
            decision.target_track_id,
        )

        response.success = True
        response.message = (
            "사람 추종 잠금을 해제했습니다. "
            f"현재 상태: {decision.state.value}"
        )

        self.get_logger().info(response.message)
        return response

    def _check_timeouts(self) -> None:
        """비전과 LiDAR 입력의 시간 초과 여부를 주기적으로 확인한다."""
        self._check_vision_timeout()
        self._check_lidar_timeout()

    def _check_vision_timeout(self) -> None:
        """비전 결과 수신이 끊기면 로봇을 정지하고 대상을 해제한다."""
        if self._last_vision_time is None:
            return

        if self._vision_timeout_handled:
            return

        now = self.get_clock().now()
        elapsed_sec = (
            now - self._last_vision_time
        ).nanoseconds / 1_000_000_000

        if (
            elapsed_sec >= 0.0
            and elapsed_sec <= self._command_timeout_sec
        ):
            return

        decision = self._state_machine.handle_vision_timeout(
            self._time_to_sec(now)
        )

        self._publish_stop("vision_command_timeout")
        self._vision_timeout_handled = True

        self._log_state_change(
            decision.state,
            decision.reason,
            decision.target_track_id,
        )

        self.get_logger().warning(
            "비전 결과 수신이 중단되어 로봇을 정지합니다."
        )

    def _check_lidar_timeout(self) -> None:
        """주행 중 LiDAR 입력이 끊기면 즉시 정지한다."""
        if not self._use_lidar:
            return

        if not self._require_lidar_before_motion:
            return

        if self._is_stopped(self._last_velocity):
            return

        if self._lidar_timeout_stop_sent:
            return

        now = self.get_clock().now()

        if self._last_scan_time is None:
            self._publish_stop("lidar_not_received")
            self._lidar_timeout_stop_sent = True
            return

        elapsed_sec = (
            now - self._last_scan_time
        ).nanoseconds / 1_000_000_000

        if (
            self._last_scan_valid
            and elapsed_sec >= 0.0
            and elapsed_sec <= self._lidar_timeout_sec
        ):
            return

        self._publish_stop("lidar_timeout")
        self._lidar_timeout_stop_sent = True

        self.get_logger().warning(
            "LiDAR 결과 수신이 중단되거나 유효하지 않아 "
            "로봇을 정지합니다."
        )

    def _lidar_is_ready(self, now: Time) -> bool:
        """최근 유효한 LiDAR 측정값이 존재하는지 확인한다."""
        if self._last_scan_time is None:
            return False

        if not self._last_scan_valid:
            return False

        elapsed_sec = (
            now - self._last_scan_time
        ).nanoseconds / 1_000_000_000

        return (
            elapsed_sec >= 0.0
            and elapsed_sec <= self._lidar_timeout_sec
        )

    @staticmethod
    def _minimum_front_distance(
        message: LaserScan,
        obstacle_half_angle_rad: float,
    ) -> tuple[bool, float | None]:
        """전방 범위에서 유효성 여부와 가장 가까운 거리를 반환한다."""
        if not math.isfinite(message.angle_min):
            return False, None

        if (
            not math.isfinite(message.angle_increment)
            or message.angle_increment == 0.0
        ):
            return False, None

        if (
            not math.isfinite(message.range_min)
            or message.range_min < 0.0
        ):
            return False, None

        if (
            math.isnan(message.range_max)
            or message.range_max <= message.range_min
        ):
            return False, None

        if not message.ranges:
            return False, None

        front_sample_found = False
        valid_measurement_found = False
        valid_distances: list[float] = []

        for index, distance in enumerate(message.ranges):
            angle = (
                message.angle_min
                + index * message.angle_increment
            )
            normalized_angle = math.atan2(
                math.sin(angle),
                math.cos(angle),
            )

            if abs(normalized_angle) > obstacle_half_angle_rad:
                continue

            front_sample_found = True

            if math.isnan(distance):
                continue

            if distance == math.inf:
                valid_measurement_found = True
                continue

            if distance == -math.inf:
                continue

            if distance < message.range_min:
                continue

            if distance > message.range_max:
                continue

            valid_measurement_found = True
            valid_distances.append(float(distance))

        if not front_sample_found:
            return False, None

        if not valid_measurement_found:
            return False, None

        if not valid_distances:
            # 전방 모든 측정값이 +inf이면 장애물이 없는 정상 상태다.
            return True, None

        return True, min(valid_distances)

    @staticmethod
    def _parse_vision_message(
        raw_message: str,
    ) -> dict[str, Any]:
        """비전 JSON 문자열을 검증하고 표준 입력 구조로 변환한다."""
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError as error:
            raise ValueError(
                "비전 결과가 올바른 JSON 형식이 아닙니다."
            ) from error

        if not isinstance(payload, dict):
            raise ValueError(
                "비전 결과는 JSON 객체여야 합니다."
            )

        status = payload.get("status")
        command = payload.get("command")
        track_id = payload.get("track_id")

        if not isinstance(status, str):
            raise ValueError(
                "비전 결과의 status는 문자열이어야 합니다."
            )

        if not isinstance(command, str):
            raise ValueError(
                "비전 결과의 command는 문자열이어야 합니다."
            )

        status = status.strip().lower()
        command = command.strip().lower()

        if not status:
            raise ValueError(
                "비전 결과의 status는 비어 있을 수 없습니다."
            )

        if not command:
            raise ValueError(
                "비전 결과의 command는 비어 있을 수 없습니다."
            )

        if (
            track_id is not None
            and (
                isinstance(track_id, bool)
                or not isinstance(track_id, int)
                or track_id < 0
            )
        ):
            raise ValueError(
                "비전 결과의 track_id는 null 또는 "
                "비음수 정수여야 합니다."
            )

        return {
            "status": status,
            "command": command,
            "track_id": track_id,
        }

    def _publish_velocity(
        self,
        velocity: VelocityCommand,
    ) -> None:
        """계산된 속도를 geometry_msgs/Twist로 발행한다."""
        twist = Twist()
        twist.linear.x = velocity.linear_x
        twist.angular.z = velocity.angular_z

        self._velocity_publisher.publish(twist)
        self._last_velocity = velocity

    def _publish_stop(self, reason: str) -> None:
        """선속도와 각속도가 모두 0인 정지 명령을 발행한다."""
        self._publish_velocity(
            VelocityCommand(
                linear_x=0.0,
                angular_z=0.0,
                reason=reason,
            )
        )

    def _log_state_change(
        self,
        state: FollowState,
        reason: str,
        target_track_id: int | None,
    ) -> None:
        """사람 추종 상태가 변경됐을 때만 상태 로그를 남긴다."""
        if state is self._last_logged_state:
            return

        self._last_logged_state = state

        self.get_logger().info(
            "사람 추종 상태 변경: "
            f"state={state.value}, "
            f"target_track_id={target_track_id}, "
            f"reason={reason}"
        )

    @staticmethod
    def _is_stopped(
        velocity: VelocityCommand,
    ) -> bool:
        """선속도와 각속도가 모두 0인지 확인한다."""
        return (
            velocity.linear_x == 0.0
            and velocity.angular_z == 0.0
        )

    @staticmethod
    def _is_positive_finite(value: float) -> bool:
        """값이 유한한 양수인지 확인한다."""
        return math.isfinite(value) and value > 0.0

    @staticmethod
    def _time_to_sec(time_value: Time) -> float:
        """ROS2 시각을 초 단위 실수로 변환한다."""
        return time_value.nanoseconds / 1_000_000_000


def main(args=None) -> None:
    """사람 추종 ROS2 노드를 실행한다."""
    rclpy.init(args=args)

    node: PersonFollower | None = None

    try:
        node = PersonFollower()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node._publish_stop("node_shutdown")
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
