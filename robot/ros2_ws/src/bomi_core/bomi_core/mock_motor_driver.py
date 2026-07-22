import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class MockMotorDriver(Node):
    def __init__(self) -> None:
        super().__init__("mock_motor_driver")

        self.subscription = self.create_subscription(
            Twist,
            "/cmd_vel",
            self.handle_cmd_vel,
            10,
        )

        self.get_logger().info("Mock motor driver started.")

    def handle_cmd_vel(self, message: Twist) -> None:
        self.get_logger().info(
            f"linear.x={message.linear.x:.2f}, "
            f"angular.z={message.angular.z:.2f}"
        )


def main(args=None) -> None:
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