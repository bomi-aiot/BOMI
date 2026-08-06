"""백엔드 MQTT와 로봇 내부 ROS 2 토픽을 잇는 통역 브릿지 노드다.

이 노드는 얇은 진입점이다. ROS 2 파라미터(robot_id, broker_host/port, 인증)를
읽어 :class:`MqttBridgeRunner` 를 구동하고 ROS 2 생명주기를 관리하기만 한다.
명령 해석·주행 실행·결과/상태 발행 같은 규칙은 모두 브릿지 코어와 러너에 있다.

주행 실행은 ``driver_type`` 파라미터로 고른다. 기본값 ``mock`` 은 기존 동작을
유지하며 :class:`MockRobotDriver` 를 사용하고, ``nav2`` 는 실제 Nav2 주행을
실행하는 :class:`Nav2RobotDriver` 를 사용한다. Nav2 드라이버는 이 ROS 2 노드
실행 경로에서만 생성한다(``docs/decisions/0001-nav2-driver-owns-action-client.md``
참고).

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
from rclpy.node import Node

from bridge.mqtt_client import MqttBridgeRunner
from bridge.nav2_robot_driver import create_nav2_robot_driver
from bridge.robot_driver import (
    DRIVER_TYPE_MOCK,
    DRIVER_TYPE_NAV2,
    MockRobotDriver,
    create_driver,
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
        )
        self._runner.connect_and_loop_start()
        self.get_logger().info(
            f"MQTT bridge node started: robot_id={robot_id}, "
            f"broker={host}:{port}, driver_type={driver_type}"
        )

    def destroy_node(self) -> bool:
        """종료 시 MQTT 러너 루프를 멈추고 드라이버 자원을 정리한다."""
        self._runner.stop()
        self._driver.shutdown()
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
