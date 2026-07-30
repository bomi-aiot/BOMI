import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class JoyCmdFilter(Node):
    """조이스틱이 실제로 움직일 때만 twist_mux로 명령을 전달한다."""

    def __init__(self):
        super().__init__('joy_cmd_filter')

        self.declare_parameter('epsilon', 0.001)
        self.epsilon = float(self.get_parameter('epsilon').value)

        self.was_active = False

        self.subscription = self.create_subscription(
            Twist,
            '/cmd_vel_joy_raw',
            self.cmd_callback,
            10,
        )

        self.publisher = self.create_publisher(
            Twist,
            '/cmd_vel_joy',
            10,
        )

    def is_active(self, msg: Twist) -> bool:
        values = [
            msg.linear.x,
            msg.linear.y,
            msg.linear.z,
            msg.angular.x,
            msg.angular.y,
            msg.angular.z,
        ]

        return any(abs(value) > self.epsilon for value in values)

    def cmd_callback(self, msg: Twist):
        active = self.is_active(msg)

        if active:
            # 조이스틱이 실제로 움직이고 있으면 계속 전달
            self.publisher.publish(msg)
            self.was_active = True

        elif self.was_active:
            # 스틱을 놓는 순간 정지 명령은 한 번만 전달
            self.publisher.publish(Twist())
            self.was_active = False

        # 중앙 상태에서 반복되는 0 명령은 전달하지 않음


def main(args=None):
    rclpy.init(args=args)

    node = JoyCmdFilter()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()