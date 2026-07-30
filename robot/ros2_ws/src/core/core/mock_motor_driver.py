"""이동 명령을 로그로 출력하는 Mock 드라이버."""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class MockMotorDriver(Node):
    """하드웨어 없이 /cmd_vel 메시지를 로그로 확인한다."""

    def __init__(self) -> None:
        """이동 명령 구독자를 초기화한다."""
        super().__init__("mock_motor_driver")

        self.subscription = self.create_subscription(
            Twist,
            "/cmd_vel",
            self.handle_cmd_vel,
            10,
        )

        self.get_logger().info("Mock motor driver started.")

    def handle_cmd_vel(self, message: Twist) -> None:
        """수신한 Twist 명령의 주요 값을 로그로 출력한다."""
        self.get_logger().info(
            f"linear.x={message.linear.x:.2f}, "
            f"angular.z={message.angular.z:.2f}"
        )


def main(args=None) -> None:
    """Mock 모터 드라이버 노드를 실행한다."""
    rclpy.init(args=args)
    node = MockMotorDriver()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
