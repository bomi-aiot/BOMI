import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


HELP_MESSAGE = """
키보드 조작
---------------------------
w : 전진
s : 후진
a : 왼쪽 회전
d : 오른쪽 회전

q : 전진 + 왼쪽
e : 전진 + 오른쪽
z : 후진 + 왼쪽
c : 후진 + 오른쪽

space : 정지
x     : 종료
"""


class KeyboardTeleop(Node):
    """키보드 입력을 /cmd_vel 토픽으로 발행하는 테스트 노드."""

    def __init__(self) -> None:
        super().__init__("keyboard_teleop")

        self.publisher = self.create_publisher(
            Twist,
            "/cmd_vel",
            10,
        )

        self.linear_speed = 0.2
        self.angular_speed = 0.5

        self.settings = termios.tcgetattr(sys.stdin)
        self.get_logger().info("Keyboard teleop started.")

        print(HELP_MESSAGE)

    def read_key(self) -> str:
        """키보드 입력을 한 글자씩 읽는다."""
        tty.setraw(sys.stdin.fileno())

        readable, _, _ = select.select(
            [sys.stdin],
            [],
            [],
            0.1,
        )

        key = sys.stdin.read(1) if readable else ""

        termios.tcsetattr(
            sys.stdin,
            termios.TCSADRAIN,
            self.settings,
        )

        return key

    def create_twist(self, key: str) -> Twist:
        message = Twist()

        commands = {
            "w": (self.linear_speed, 0.0),
            "s": (-self.linear_speed, 0.0),
            "a": (0.0, self.angular_speed),
            "d": (0.0, -self.angular_speed),
            "q": (self.linear_speed, self.angular_speed),
            "e": (self.linear_speed, -self.angular_speed),
            "z": (-self.linear_speed, -self.angular_speed),
            "c": (-self.linear_speed, self.angular_speed),
            " ": (0.0, 0.0),
        }

        linear_x, angular_z = commands.get(key, (0.0, 0.0))

        message.linear.x = linear_x
        message.angular.z = angular_z

        return message

    def publish_stop(self) -> None:
        self.publisher.publish(Twist())
        self.get_logger().info("정지 명령 발행")

    def run(self) -> None:
        try:
            while rclpy.ok():
                key = self.read_key()

                if key == "x":
                    self.publish_stop()
                    break

                if key == "":
                    continue

                message = self.create_twist(key)
                self.publisher.publish(message)

                self.get_logger().info(
                    f"명령 발행: linear.x={message.linear.x:.2f}, "
                    f"angular.z={message.angular.z:.2f}"
                )

        finally:
            self.publish_stop()

            termios.tcsetattr(
                sys.stdin,
                termios.TCSADRAIN,
                self.settings,
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = KeyboardTeleop()

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
