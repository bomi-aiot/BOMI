#!/usr/bin/env python3
"""하드웨어 없이 회전 탐색을 끝까지 돌려 보는 가짜 로봇 (WSL·개발 PC 용).

무엇을 하는가
    속도 명령(/cmd_vel)을 구독해 "그만큼 실제로 돌았다"고 가정하고 yaw 를
    적분한 뒤, 그 결과를 /odom 으로 되돌려 발행한다. 그래서 wake_search 는
    자기가 낸 명령의 결과를 눈으로 보게 되고, 스텝 회전 → 관찰 → 다음 스텝 →
    한 바퀴 → 복귀까지 **폐루프로** 완주한다.

    이게 없으면 /odom 이 없어서 wake_search 는 첫 줄에서 정지한다:
        "odom 이 없어 탐색을 시작하지 않습니다."

무엇을 하지 않는가
    물리(관성·미끄러짐·모터 지연)를 흉내 내지 않는다. 명령한 각속도가 그대로
    실현된다고 가정하는 이상적인 모델이다. 그러므로 여기서 통과했다고 실기에서
    각도가 맞는다는 뜻은 아니다 — 여기서 검증하는 것은 **상태 전이와 배선**이고,
    실제 회전량은 실기에서 각도기로 재야 한다.

왜 core 패키지에 넣지 않았는가
    운영 코드가 아니라 개발용 도구다. 패키지에 넣으면 setup.py 등록과 재빌드가
    필요하고, 실수로 실기에서 뜨면 가짜 odom 이 진짜를 덮어쓴다. 스크립트로
    두면 부를 때만 돈다.

사용법
    source /opt/ros/humble/setup.bash
    source ~/S15P11E102/robot/ros2_ws/install/setup.bash

    # twist_mux 를 함께 띄운 경우 (최종 출력 /cmd_vel 을 본다)
    python3 robot/scripts/wsl_fake_robot.py

    # wake_search 만 단독으로 볼 때 (twist_mux 없이)
    python3 robot/scripts/wsl_fake_robot.py --ros-args \\
        -p cmd_vel_topic:=/cmd_vel_search

    # 사람이 보이는 상황을 함께 재현 (5초 뒤부터 tracking 발행)
    python3 robot/scripts/wsl_fake_robot.py --ros-args \\
        -p publish_vision:=true -p vision_delay_sec:=5.0
"""

import math

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class FakeRobot(Node):
    """속도 명령을 적분해 /odom 을 만들어 주는 최소 시뮬레이터."""

    def __init__(self) -> None:
        """구독·발행과 적분 타이머를 만든다."""
        super().__init__("wsl_fake_robot")

        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("vision_topic", "/vision/follow_result")
        self.declare_parameter("rate_hz", 50.0)
        self.declare_parameter("print_interval_sec", 0.5)
        # Pico 의 cmd_vel_timeout_sec 와 같은 값. 명령이 끊기면 멈춘 것으로 본다.
        self.declare_parameter("command_timeout_sec", 0.5)
        # 사람이 보이는 상황을 흉내 낼지. false 면 비전 결과를 발행하지 않는다.
        self.declare_parameter("publish_vision", False)
        self.declare_parameter("vision_delay_sec", 5.0)

        cmd_topic = str(self.get_parameter("cmd_vel_topic").value)
        odom_topic = str(self.get_parameter("odom_topic").value)
        vision_topic = str(self.get_parameter("vision_topic").value)
        self._rate_hz = float(self.get_parameter("rate_hz").value)
        self._print_interval = float(
            self.get_parameter("print_interval_sec").value)
        self._command_timeout = float(
            self.get_parameter("command_timeout_sec").value)
        self._publish_vision = bool(
            self.get_parameter("publish_vision").value)
        self._vision_delay = float(
            self.get_parameter("vision_delay_sec").value)

        if self._rate_hz <= 0.0:
            raise ValueError("rate_hz는 양수여야 합니다.")

        self._yaw = 0.0
        self._angular_z = 0.0
        self._last_cmd_sec = 0.0
        self._last_print_sec = 0.0
        self._started_sec = self._now()
        self._total_abs_rad = 0.0

        self._odom_publisher = self.create_publisher(Odometry, odom_topic, 10)
        self._vision_publisher = self.create_publisher(
            String, vision_topic, 10)
        self.create_subscription(Twist, cmd_topic, self._on_cmd_vel, 10)

        self._timer = self.create_timer(1.0 / self._rate_hz, self._on_tick)

        self.get_logger().info(
            f"가짜 로봇 시작: 명령 구독={cmd_topic}, odom 발행={odom_topic}, "
            f"비전 발행={'켬' if self._publish_vision else '끔'}"
            f"{f'({self._vision_delay:.0f}초 뒤 tracking)' if self._publish_vision else ''}"
        )
        self.get_logger().info(
            "이 노드는 물리를 흉내 내지 않습니다 — 명령한 각속도가 그대로 "
            "실현된다고 가정합니다. 상태 전이와 배선 확인용입니다.")

    # ── 콜백 ────────────────────────────────────────────────────────────────

    def _on_cmd_vel(self, message: Twist) -> None:
        """마지막 속도 명령과 도착 시각을 기억한다."""
        angular_z = float(message.angular.z)
        if not math.isfinite(angular_z):
            self.get_logger().warning("유한하지 않은 angular.z 를 무시합니다.")
            return
        self._angular_z = angular_z
        self._last_cmd_sec = self._now()

    def _on_tick(self) -> None:
        """한 주기만큼 yaw 를 적분하고 /odom 과 (선택) 비전 결과를 발행한다."""
        now = self._now()
        dt = 1.0 / self._rate_hz

        # 명령이 끊기면 실물 Pico 처럼 멈춘 것으로 본다.
        if now - self._last_cmd_sec > self._command_timeout:
            self._angular_z = 0.0

        self._yaw = _wrap(self._yaw + self._angular_z * dt)
        self._total_abs_rad += abs(self._angular_z) * dt

        self._publish_odom(now)
        if self._publish_vision:
            self._publish_vision_result(now)

        if now - self._last_print_sec >= self._print_interval:
            self._last_print_sec = now
            self.get_logger().info(
                f"yaw={math.degrees(self._yaw):+7.1f}도  "
                f"명령={self._angular_z:+.2f}rad/s  "
                f"누적회전={math.degrees(self._total_abs_rad):6.0f}도  "
                f"{_dial(self._yaw)}")

    # ── 발행 ────────────────────────────────────────────────────────────────

    def _publish_odom(self, now: float) -> None:
        """현재 yaw 를 Odometry 로 발행한다. 위치는 항상 원점이다."""
        message = Odometry()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "odom"
        message.child_frame_id = "base_link"
        message.pose.pose.orientation.z = math.sin(self._yaw / 2.0)
        message.pose.pose.orientation.w = math.cos(self._yaw / 2.0)
        message.twist.twist.angular.z = self._angular_z
        self._odom_publisher.publish(message)

    def _publish_vision_result(self, now: float) -> None:
        """비전 결과를 흉내 낸다. 지정한 시각이 지나면 tracking 으로 바뀐다."""
        tracking = (now - self._started_sec) >= self._vision_delay
        if tracking:
            payload = (
                '{"status":"tracking","command":"move_forward",'
                '"track_id":1,"reason":"fake"}')
        else:
            payload = (
                '{"status":"not_detected","command":"stop",'
                '"track_id":null,"reason":"fake"}')
        self._vision_publisher.publish(String(data=payload))

    def _now(self) -> float:
        """ROS 시계의 현재 시각(초)."""
        return self.get_clock().now().nanoseconds / 1e9


def _wrap(radians: float) -> float:
    """각도를 -pi ~ pi 로 접는다."""
    wrapped = math.fmod(radians + math.pi, 2.0 * math.pi)
    if wrapped < 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def _dial(yaw_rad: float) -> str:
    """지금 어디를 보고 있는지 글자로 그린다. 로그를 눈으로 따라가기 쉽게 한다."""
    slots = 24
    index = int(round((math.degrees(yaw_rad) % 360.0) / (360.0 / slots))) % slots
    dial = ["."] * slots
    dial[index] = "@"
    return "[" + "".join(dial) + "]"


def main(args=None) -> None:
    """가짜 로봇을 실행한다."""
    rclpy.init(args=args)
    node = None
    try:
        node = FakeRobot()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
