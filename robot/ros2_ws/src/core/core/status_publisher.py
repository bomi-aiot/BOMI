"""BOMI 상태 메시지를 주기적으로 발행하는 ROS 2 노드."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class StatusPublisher(Node):
    """BOMI 준비 상태를 /bomi/status 토픽으로 발행한다."""

    def __init__(self) -> None:
        """상태 발행 publisher와 주기 타이머를 초기화한다."""
        super().__init__("status_publisher")

        self.publisher = self.create_publisher(
            String,
            "/bomi/status",
            10,
        )

        self.timer = self.create_timer(
            1.0,
            self.publish_status,
        )

        self.get_logger().info("Status publisher started.")

    def publish_status(self) -> None:
        """준비 상태 문자열을 한 번 발행한다."""
        message = String()
        message.data = "bomi is ready"

        self.publisher.publish(message)
        self.get_logger().info(f"Published: {message.data}")


def main(args=None) -> None:
    """상태 발행 노드를 실행한다."""
    rclpy.init(args=args)

    node = StatusPublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
