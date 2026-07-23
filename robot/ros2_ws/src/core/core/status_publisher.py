import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class StatusPublisher(Node):
    def __init__(self) -> None:
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
        message = String()
        message.data = "bomi is ready"

        self.publisher.publish(message)
        self.get_logger().info(f"Published: {message.data}")


def main(args=None) -> None:
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
