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
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from core.follow_state_machine import (
    FollowState,
    FollowStateMachine,
    VisionTrackingStatus,
)
from core.person_following_controller import (
    PersonFollowingController,
    VelocityCommand,
    ramp_toward,
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
        enable_topic = str(
            self.get_parameter("enable_topic").value
        )
        status_topic = str(
            self.get_parameter("status_topic").value
        )

        # 추종 스위치. False 인 동안은 _publish_velocity 가 아무것도 발행하지
        # 않는다(끄는 순간의 정지 1회는 스위치를 내리기 '전'에 내보낸다 —
        # _enable_callback 참고). 발행 지점마다 조건을 흩뿌리는 대신 단일
        # 초크포인트에서 막는다.
        self._enabled = bool(
            self.get_parameter("start_enabled").value
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
        self._approach_uses_lidar_only = bool(
            self.get_parameter(
                "approach_uses_lidar_only"
            ).value
        )
        self._hold_motion_on_brief_loss = bool(
            self.get_parameter("hold_motion_on_brief_loss").value
        )
        self._linear_accel_limit = float(
            self.get_parameter("linear_accel_limit").value
        )
        self._angular_accel_limit = float(
            self.get_parameter("angular_accel_limit").value
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
            turn_linear_ratio=float(
                self.get_parameter("turn_linear_ratio").value
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
        self._last_logged_velocity_reason: str | None = None
        self._last_publish_sec: float | None = None
        self._arrival_sent = False

        self._vision_timeout_handled = True
        self._lidar_timeout_stop_sent = True

        self._velocity_publisher = self.create_publisher(
            Twist,
            output_topic,
            10,
        )

        # wake_search 가 "추종을 포기했다"를 알 수 있는 유일한 통로
        # (S15P11E102-376, 엉뚱한 사람 락온 후 영구 정지 버그 수정).
        # 상태 자체가 아니라 상태 '전이'를 알려야 하므로 QoS depth 는
        # 작게 두고 최신 전이만 흘려보낸다.
        self._status_publisher = self.create_publisher(
            String,
            status_topic,
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

        # 추종 켜기/끄기 (S15P11E102 통합 스프린트 2-5, "도착 후 사람 접근").
        # bridge 의 ApproachController 가 거실 도착 직후 True, 시간 상한 뒤
        # False 를 발행한다. 서비스가 아니라 토픽인 이유: 발행자(bridge 워커
        # 스레드)가 응답을 기다리며 spin 할 필요가 없어야 하기 때문이다.
        self._enable_subscription = self.create_subscription(
            Bool,
            enable_topic,
            self._enable_callback,
            10,
        )

        # 꺼진 채 시작하면 상태 머신도 DISABLED 로 맞춘다 — 안 맞추면
        # 첫 enable 때 enable() 호출이 '이미 켜져 있던' 상태 머신을 리셋해
        # 버리는 어긋남이 생긴다.
        if not self._enabled:
            self._state_machine.disable(
                self._time_to_sec(self.get_clock().now())
            )

        self._safety_timer = self.create_timer(
            0.1,
            self._check_timeouts,
        )

        self.get_logger().info(
            "사람 추종 노드를 시작했습니다. "
            f"비전 입력={input_topic}, "
            f"LiDAR 입력={scan_topic}, "
            f"속도 출력={output_topic}, "
            f"시작 상태={'켜짐' if self._enabled else '꺼짐'} "
            f"(스위치 토픽={enable_topic})"
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

        # 추종을 켜고 끄는 런타임 스위치 (S15P11E102 통합 스프린트 2-5).
        #
        # 왜 필요한가
        #   "도착 후 사람 접근" 대본에서는 이 노드가 output_topic=/cmd_vel 로
        #   직결된 채 상시 떠 있고, bridge 의 ApproachController 가 거실 도착
        #   직후 잠깐 켰다가 시간 상한 뒤 끈다. 끔 = "발행 자체를 멈춤"이다 —
        #   상태 머신의 DISABLED 에만 맡기면 매 프레임 정지 Twist 가 계속
        #   나가서, /cmd_vel 을 공유하는 Nav2 주행을 0으로 짓밟는다.
        #
        # start_enabled 기본값이 True 인 이유: 기존 person_following.launch.py
        # 사용자(출력 /cmd_vel_follow, 스위치 없던 시절)의 동작을 바꾸지
        # 않는다. 접근 대본 launch 만 명시적으로 false 로 시작한다.
        self.declare_parameter(
            "start_enabled",
            True,
        )
        self.declare_parameter(
            "enable_topic",
            "/person_following/enable",
        )
        self.declare_parameter(
            "status_topic",
            "/person_following/status",
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
            "turn_linear_ratio",
            0.0,
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
        # 기본값 False — 카메라가 사람 전신을 담을 수 있게 달린 기존 구성의
        # 동작을 바꾸지 않는다. 이 로봇처럼 카메라가 낮은 경우에만 켠다.
        self.declare_parameter(
            "approach_uses_lidar_only",
            False,
        )
        # 정지 상태에서 목표 속도로 튀어나가면 바로 앞의 사람에게 위협적으로
        # 느껴진다(2026-08-09 실기 피드백). 0 이면 제한하지 않는다.
        # 짧은 미검출에 정지를 내보내지 않는다. 기본 False 로 두어 기존
        # 사용처(순찰 등)의 동작을 바꾸지 않는다.
        self.declare_parameter(
            "hold_motion_on_brief_loss",
            False,
        )
        self.declare_parameter(
            "linear_accel_limit",
            0.0,
        )
        self.declare_parameter(
            "angular_accel_limit",
            0.0,
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

        # 한 프레임만 놓쳐도 비전은 temporarily_lost 를 낸다(실측: 9.4FPS 중
        # 20%). 그때마다 정지를 발행하면 다가가는 내내 가다 서다를 반복해
        # 앞에서 깔짝거리는 것처럼 보인다(2026-08-09 실기). 짧은 누락에는
        # 아무것도 발행하지 않고 직전 명령이 흐르게 둔다 — 진짜로 끊기면
        # Pico 워치독(0.5초)이 알아서 세우므로 정지가 늦어지지 않는다.
        if (
            self._hold_motion_on_brief_loss
            and decision.state is FollowState.TEMPORARILY_LOST
        ):
            self._log_state_change(
                decision.state,
                decision.reason,
                decision.target_track_id,
            )
            return

        movement_allowed = decision.movement_allowed
        command = self._effective_command(
            payload["command"],
            movement_allowed,
        )
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

                person_distance_m = self._front_person_distance_m

        velocity = self._controller.calculate_velocity(
            command=command,
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

    def _effective_command(
        self,
        command: str,
        movement_allowed: bool,
    ) -> str:
        """비전의 "충분히 가깝다" 판정을 LiDAR 에 넘길지 결정한다.

        비전은 사람 상자가 화면 높이의 얼마를 차지하는지로 거리를 가늠한다.
        카메라가 종아리 높이에 달린 이 로봇에서는 그 비율이 거리와 무관하게
        늘 0.98~1.00(상자가 화면에 잘림)이라, 몇 m 밖에서도 "다 왔다"(stop)만
        나와 로봇이 전진을 시작조차 못 한다(2026-08-09 실측).

        approach_uses_lidar_only 가 켜져 있으면 그 판정을 무시하고 전진으로
        바꾼다. 실제 정지는 LiDAR 가 person_stop_distance_m 에서 시킨다.
        좌우 정렬(turn_left/turn_right)은 화면 좌우 위치로 판단하므로 카메라
        높이와 무관하다 — 그대로 둔다.

        movement_allowed 가 False 면 대상이 확정되지 않은 상태(다중 인물·
        추적 상실 등)이므로 어떤 것도 전진으로 바꾸지 않는다.
        """
        if not self._approach_uses_lidar_only:
            return command
        if not movement_allowed:
            return command
        if command != "stop":
            return command
        return "move_forward"

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

    def _enable_callback(self, message: Bool) -> None:
        """추종 스위치를 켜거나 끈다 (2-5 도착 후 사람 접근).

        끄기: 정지 1회를 **스위치를 내리기 전에** 발행한다 — 내린 뒤에는
        _publish_velocity 초크포인트가 모든 발행을 막기 때문이다. 상태
        머신도 DISABLED 로 보내 잔여 추적 후보를 지운다.

        켜기: 상태 머신을 enable() 으로 WAITING_TARGET 에서 새로 시작한다.
        비전 신호가 흐르고 있으면 target_confirm_sec(0.5초) 뒤부터
        움직인다. 켠 시점의 낡은 비전 타임아웃이 곧바로 발화하지 않도록
        타임아웃 플래그를 처리됨으로 되돌린다.

        같은 값이 다시 오면 아무 일도 하지 않는다(멱등) — QoS 재전송이나
        발행측의 방어적 재발행이 로그를 어지럽히지 않게 한다.
        """
        requested = bool(message.data)
        if requested == self._enabled:
            return

        now_sec = self._time_to_sec(self.get_clock().now())
        if requested:
            self._enabled = True
            decision = self._state_machine.enable(now_sec)
            self._vision_timeout_handled = True
            self._lidar_timeout_stop_sent = True
            self._arrival_sent = False
            self.get_logger().info("사람 추종을 켭니다 (접근 단계 시작)")
        else:
            # 순서 중요: 정지 발행이 먼저, 스위치 내리기가 나중.
            self._publish_stop("following_disabled")
            self._enabled = False
            decision = self._state_machine.disable(now_sec)
            self.get_logger().info("사람 추종을 끕니다 (접근 단계 종료)")

        self._log_state_change(
            decision.state,
            decision.reason,
            decision.target_track_id,
        )

    def _publish_velocity(
        self,
        velocity: VelocityCommand,
    ) -> None:
        """계산된 속도를 geometry_msgs/Twist로 발행한다.

        ★ 추종 스위치가 꺼져 있으면 발행하지 않는다. 이 노드가
        output_topic=/cmd_vel 로 직결된 접근 대본에서, 꺼진 상태의 매 프레임
        정지 발행은 Nav2 주행 명령을 0으로 짓밟는다 — 발행 지점이 여럿이라
        (비전 콜백·스캔 콜백·타임아웃 타이머) 여기 한 곳에서 막는 것이
        빠뜨림이 없다. 끄는 순간의 마지막 정지 1회는 _enable_callback 이
        스위치를 내리기 전에 이 함수를 통과시킨다.
        """
        if not self._enabled:
            return

        now_sec = self._time_to_sec(self.get_clock().now())
        elapsed_sec = (
            0.0
            if self._last_publish_sec is None
            else now_sec - self._last_publish_sec
        )
        self._last_publish_sec = now_sec

        previous = self._last_velocity
        linear_x = ramp_toward(
            velocity.linear_x,
            0.0 if previous is None else previous.linear_x,
            self._linear_accel_limit,
            elapsed_sec,
        )
        angular_z = ramp_toward(
            velocity.angular_z,
            0.0 if previous is None else previous.angular_z,
            self._angular_accel_limit,
            elapsed_sec,
        )
        velocity = VelocityCommand(
            linear_x=linear_x,
            angular_z=angular_z,
            reason=velocity.reason,
        )

        twist = Twist()
        twist.linear.x = velocity.linear_x
        twist.angular.z = velocity.angular_z

        self._velocity_publisher.publish(twist)

        # 판단 근거가 바뀔 때만 남긴다. "사람은 찾았는데 왜 안 다가가는가"는
        # 이 reason(person_distance_unavailable, lidar_not_ready,
        # waiting_for_person_resume_distance …) 없이는 밖에서 알 수 없다.
        if velocity.reason != self._last_logged_velocity_reason:
            self._last_logged_velocity_reason = velocity.reason
            self.get_logger().info(
                "추종 속도 판단: "
                f"reason={velocity.reason}, "
                f"linear.x={velocity.linear_x:.2f}, "
                f"angular.z={velocity.angular_z:.2f}"
            )

        # 사람 앞에 다 왔다는 사실은 상태(FollowState)가 아니라 속도 판단
        # 근거로만 나타난다. 도착 뒤에도 추종을 켜 둔 채로 두면 대화 중
        # 어르신이 조금만 움직여도 계속 재정렬·재접근해서 앞에서 좌우로
        # 깔짝거린다(2026-08-09 실기) — wake_search 가 추종을 끌 수 있도록
        # 한 번만 알린다.
        if velocity.reason == "person_too_close" and not self._arrival_sent:
            self._arrival_sent = True
            self._publish_status(
                state="arrived",
                reason=velocity.reason,
                target_track_id=self._state_machine.target_track_id,
            )

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

        self._publish_status(
            state=state.value,
            reason=reason,
            target_track_id=target_track_id,
        )

    def _publish_status(
        self,
        *,
        state: str,
        reason: str,
        target_track_id: int | None,
    ) -> None:
        """wake_search 가 구독하는 상태 토픽에 한 줄 알린다."""
        status_msg = String()
        status_msg.data = json.dumps(
            {
                "state": state,
                "target_track_id": target_track_id,
                "reason": reason,
            }
        )
        self._status_publisher.publish(status_msg)

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
