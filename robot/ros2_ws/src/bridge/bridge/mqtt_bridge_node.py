"""백엔드 MQTT와 로봇 내부 ROS 2 토픽을 잇는 통역 브릿지 노드다.

이 노드는 얇은 진입점이다. ROS 2 파라미터(robot_id, broker_host/port, 인증)를
읽어 :class:`MqttBridgeRunner` 를 구동하고 ROS 2 생명주기를 관리하기만 한다.
명령 해석·주행 실행·결과/상태 발행 같은 규칙은 모두 브릿지 코어와 러너에 있다.

주행 실행은 러너 기본값인 :class:`MockRobotDriver` 를 사용한다. 로봇 하드웨어와
Nav2가 준비되면 러너에 실물 드라이버를 주입하는 지점만 바꾸면 된다
(``docs/decisions/0001-nav2-driver-owns-action-client.md`` 참고).

실행 예:

.. code-block:: bash

    ros2 run bridge mqtt_bridge --ros-args \\
        -p robot_id:=robot-01 -p broker_host:=localhost -p broker_port:=1883
"""

import rclpy
from rclpy.node import Node

from bridge.mqtt_client import MqttBridgeRunner


class MqttBridgeNode(Node):
    """MqttBridgeRunner를 ROS 2 노드로 감싸 구동하는 얇은 래퍼다."""

    def __init__(self) -> None:
        super().__init__("mqtt_bridge")

        self.declare_parameter("robot_id", "robot-01")
        self.declare_parameter("broker_host", "localhost")
        self.declare_parameter("broker_port", 1883)
        self.declare_parameter("username", "")
        self.declare_parameter("password", "")

        robot_id = str(self.get_parameter("robot_id").value)
        host = str(self.get_parameter("broker_host").value)
        port = int(self.get_parameter("broker_port").value)
        username = str(self.get_parameter("username").value) or None
        password = str(self.get_parameter("password").value) or None

        self._runner = MqttBridgeRunner(
            robot_id, host, port, username=username, password=password
        )
        self._runner.connect_and_loop_start()
        self.get_logger().info(
            f"MQTT bridge node started: robot_id={robot_id}, broker={host}:{port}"
        )

    def destroy_node(self) -> bool:
        """종료 시 MQTT 러너 루프를 멈추고 연결을 정리한다."""
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
