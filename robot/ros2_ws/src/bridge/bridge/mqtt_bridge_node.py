"""백엔드 MQTT와 로봇 내부 ROS 2 토픽을 잇는 통역 브릿지 노드다.

이 노드는 얇은 진입점이다. ROS 2 파라미터(robot_id, broker_host/port, 인증)를
읽어 :class:`MqttBridgeRunner` 를 구동하고 ROS 2 생명주기를 관리하기만 한다.
명령 해석·주행 실행·결과/상태 발행 같은 규칙은 모두 브릿지 코어와 러너에 있다.

주행 실행은 ``driver_type`` 파라미터로 고른다. 기본값 ``mock`` 은 기존 동작을
유지하며 :class:`MockRobotDriver` 를 사용하고, ``nav2`` 는 실제 Nav2 주행을
실행하는 :class:`Nav2RobotDriver` 를, ``timed`` 는 지도 없이 정해진 시간만큼
직진하는 :class:`TimedDriveRobotDriver` 를, ``forward_test`` 는 전용 속도
토픽(`/cmd_vel_backend_test`)으로 저속 전진 통신 테스트를 수행하는
:class:`ForwardTestRobotDriver` 를 사용한다. ROS 2 자원이 필요한 드라이버는
전부 이 노드 실행 경로에서만 생성한다
(``docs/decisions/0001-nav2-driver-owns-action-client.md`` 참고).

실행 예:

.. code-block:: bash

    ros2 run bridge mqtt_bridge --ros-args \\
        -p robot_id:=robot-01 -p broker_host:=localhost -p broker_port:=1883

    ros2 run bridge mqtt_bridge --ros-args \\
        -p driver_type:=nav2 -p goal_timeout_seconds:=120.0

    # 실브로커(i15e102.p.ssafy.io:8883)에 붙일 때 — use_tls 를 반드시 켠다.
    ros2 run bridge mqtt_bridge --ros-args \\
        -p broker_host:=i15e102.p.ssafy.io -p broker_port:=8883 \\
        -p use_tls:=true -p username:=<계정> -p password:=<토큰>
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool

from bridge.approach import DEFAULT_APPROACH_DURATION_SEC, ApproachController
from bridge.forward_test_robot_driver import ForwardTestRobotDriver
from bridge.mqtt_client import MqttBridgeRunner
from bridge.nav2_robot_driver import create_nav2_robot_driver
from bridge.robot_driver import (
    DRIVER_TYPE_MOCK,
    DRIVER_TYPE_TIMED,
    MockRobotDriver,
    create_driver,
)
from bridge.timed_drive_driver import (
    DEFAULT_DRIVE_DURATION_SEC,
    DEFAULT_LINEAR_SPEED,
    TimedDriveRobotDriver,
)


class MqttBridgeNode(Node):
    """MqttBridgeRunner를 ROS 2 노드로 감싸 구동하는 얇은 래퍼다."""

    def __init__(self) -> None:
        super().__init__("mqtt_bridge")

        self.declare_parameter("robot_id", "robot-01")
        self.declare_parameter("broker_host", "localhost")
        self.declare_parameter("broker_port", 1883)
        self.declare_parameter("username", "")
        self.declare_parameter("password", "")
        # TLS: 실브로커(i15e102.p.ssafy.io:8883)에 붙으려면 필요하다. 과거
        # ROS2 launch 경로는 이 파라미터를 아예 선언하지 않아 순수 paho
        # 경로(mqtt_client.main)에서만 TLS 를 쓸 수 있었다 — 노드 경로로는
        # 실브로커 접속이 원천 불가능했다.
        self.declare_parameter("use_tls", False)
        self.declare_parameter("ca_certs", "")
        self.declare_parameter("tls_insecure", False)
        # 주행 드라이버 선택과 Nav2 주행 설정. driver_type 기본값은 기존 동작을
        # 유지하기 위해 mock 이다.
        self.declare_parameter("driver_type", DRIVER_TYPE_MOCK)
        self.declare_parameter("goal_timeout_seconds", 120.0)
        self.declare_parameter("waypoint_file", "")
        self.declare_parameter("nav_action_name", "navigate_to_pose")
        self.declare_parameter("nav_frame_id", "map")
        self.declare_parameter("test_forward_speed_m_s", 0.08)
        self.declare_parameter("test_forward_duration_sec", 2.0)
        self.declare_parameter("test_publish_rate_hz", 10.0)
        self.declare_parameter(
            "test_cmd_vel_topic", "/cmd_vel_backend_test"
        )

        # driver_type:=timed 전용. 지도 없이 "2초 직진"으로 이동을 대체한다.
        # cmd_vel_topic 을 파라미터로 둔 이유: 사람 접근(person_follower)과
        # 같은 토픽을 공유하므로 실험 중 분리할 수 있어야 한다.
        self.declare_parameter("timed_drive_duration_seconds",
                               DEFAULT_DRIVE_DURATION_SEC)
        self.declare_parameter("timed_drive_linear_speed", DEFAULT_LINEAR_SPEED)
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")

        # 도착 후 사람 접근 (CLAUDE.md §3a, 2-5). 킬 스위치 — 기본 꺼짐.
        # V4 실기에서 처음 검증되는 기능이라, 불안정하면 이 파라미터 하나로
        # "거실 좌표 도착"까지의 검증된 동작으로 즉시 되돌릴 수 있어야 한다.
        self.declare_parameter("approach_enabled", False)
        self.declare_parameter(
            "approach_duration_seconds", DEFAULT_APPROACH_DURATION_SEC)
        self.declare_parameter(
            "approach_enable_topic", "/person_following/enable")

        robot_id = str(self.get_parameter("robot_id").value)
        host = str(self.get_parameter("broker_host").value)
        port = int(self.get_parameter("broker_port").value)
        username = str(self.get_parameter("username").value) or None
        password = str(self.get_parameter("password").value) or None
        use_tls = bool(self.get_parameter("use_tls").value)
        ca_certs = str(self.get_parameter("ca_certs").value) or None
        tls_insecure = bool(self.get_parameter("tls_insecure").value)

        driver_type = str(self.get_parameter("driver_type").value)
        goal_timeout_seconds = float(
            self.get_parameter("goal_timeout_seconds").value
        )
        waypoint_file = str(self.get_parameter("waypoint_file").value)
        nav_action_name = str(self.get_parameter("nav_action_name").value)
        nav_frame_id = str(self.get_parameter("nav_frame_id").value)
        test_forward_speed_m_s = float(
            self.get_parameter("test_forward_speed_m_s").value
        )
        test_forward_duration_sec = float(
            self.get_parameter("test_forward_duration_sec").value
        )
        test_publish_rate_hz = float(
            self.get_parameter("test_publish_rate_hz").value
        )
        test_cmd_vel_topic = str(
            self.get_parameter("test_cmd_vel_topic").value
        )

        timed_drive_duration_seconds = float(
            self.get_parameter("timed_drive_duration_seconds").value)
        timed_drive_linear_speed = float(
            self.get_parameter("timed_drive_linear_speed").value)
        cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)

        approach_enabled = bool(self.get_parameter("approach_enabled").value)
        approach_duration_seconds = float(
            self.get_parameter("approach_duration_seconds").value)
        approach_enable_topic = str(
            self.get_parameter("approach_enable_topic").value)

        # timed 를 고른 경우에만 속도 발행자를 만든다. 다른 드라이버에서
        # /cmd_vel 발행자가 떠 있으면 혼동을 부른다.
        self._cmd_vel_publisher = None
        if driver_type == DRIVER_TYPE_TIMED:
            self._cmd_vel_publisher = self.create_publisher(
                Twist, cmd_vel_topic, 10)

        # nav2 를 고른 경우에만 create_nav2 팩터리가 호출되어 전용 ROS 2 노드가
        # 만들어진다. mock 을 고르면 Nav2 자원을 전혀 생성하지 않는다.
        self._driver = create_driver(
            driver_type,
            create_mock=lambda: MockRobotDriver(),
            create_nav2=lambda: create_nav2_robot_driver(
                waypoint_file=(waypoint_file or None),
                action_name=nav_action_name,
                frame_id=nav_frame_id,
                goal_timeout_seconds=goal_timeout_seconds,
            ),
            create_timed=lambda: TimedDriveRobotDriver(
                self._publish_linear_velocity,
                duration_sec=timed_drive_duration_seconds,
                linear_speed=timed_drive_linear_speed,
                logger=self.get_logger(),
            ),
            create_forward_test=lambda: ForwardTestRobotDriver(
                self,
                forward_speed_m_s=test_forward_speed_m_s,
                forward_duration_seconds=test_forward_duration_sec,
                publish_rate_hz=test_publish_rate_hz,
                command_topic=test_cmd_vel_topic,
            ),
        )

        # publish 는 rclpy 발행자 기준 스레드 안전이다 — bridge 워커 스레드
        # (on_arrival)와 접근 타이머 스레드(만료 시 끄기) 양쪽에서 안전하게
        # 호출된다(approach.py 모듈 docstring "스레드 모델" 참고).
        self._approach_enable_publisher = self.create_publisher(
            Bool, approach_enable_topic, 10)
        self._approach = ApproachController(
            self._publish_approach_enable,
            duration_sec=approach_duration_seconds,
            enabled=approach_enabled,
        )

        self._runner = MqttBridgeRunner(
            robot_id,
            host,
            port,
            driver=self._driver,
            username=username,
            password=password,
            use_tls=use_tls,
            ca_certs=ca_certs,
            tls_insecure=tls_insecure,
            on_arrival=self._approach.on_arrival,
        )
        self._runner.connect_and_loop_start()
        self.get_logger().info(
            f"MQTT bridge node started: robot_id={robot_id}, "
            f"broker={host}:{port}, driver_type={driver_type}, "
            f"approach_enabled={approach_enabled}"
        )

    def _publish_approach_enable(self, enable: bool) -> None:
        self._approach_enable_publisher.publish(Bool(data=enable))

    def _publish_linear_velocity(self, linear_x: float) -> None:
        """timed 드라이버가 부르는 속도 발행. 전진/정지만 쓴다."""
        if self._cmd_vel_publisher is None:
            return
        message = Twist()
        message.linear.x = float(linear_x)
        self._cmd_vel_publisher.publish(message)

    def destroy_node(self) -> bool:
        """종료 시 MQTT 러너 루프를 멈추고 드라이버 자원을 정리한다."""
        # 접근 중에 종료되면 추종을 켠 채로 죽는다 — 먼저 끈다.
        self._approach.stop()
        self._runner.stop()
        return super().destroy_node()


def main(args=None) -> None:
    """브릿지 노드를 초기화하고 종료 시 자원을 정리한다."""
    rclpy.init(args=args)
    node = MqttBridgeNode()

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
