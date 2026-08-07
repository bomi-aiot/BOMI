"""AMCL 초기 위치를 발행한다. 사용법: set_initpose.py X Y YAW

``ros2 topic pub`` 으로는 들어가지 않는다. 기본 QoS 가 VOLATILE 이라 AMCL 의
구독과 맞지 않아 콜백이 아예 불리지 않고, 로그에도 아무 흔적이 남지 않는다
(2026-08-07 실기에서 30초를 여기서 날렸다). TRANSIENT_LOCAL + RELIABLE 로
여러 번 발행해야 한다.
"""
import math
import sys
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

PUBLISH_SEC = 8.0
# RViz 의 2D Pose Estimate 가 쓰는 값과 같은 수준의 초기 불확실성.
COV_XY = 0.25
COV_YAW = 0.068


def main() -> int:
    """인자로 받은 좌표를 /initialpose 로 반복 발행한다."""
    if len(sys.argv) < 4:
        print("사용법: set_initpose.py X Y YAW", file=sys.stderr)
        return 2

    x, y, yaw = (float(value) for value in sys.argv[1:4])

    rclpy.init()
    node = Node("set_initpose")
    qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    publisher = node.create_publisher(
        PoseWithCovarianceStamped, "/initialpose", qos
    )

    message = PoseWithCovarianceStamped()
    message.header.frame_id = "map"
    message.pose.pose.position.x = x
    message.pose.pose.position.y = y
    message.pose.pose.orientation.z = math.sin(yaw / 2.0)
    message.pose.pose.orientation.w = math.cos(yaw / 2.0)
    covariance = [0.0] * 36
    covariance[0] = COV_XY
    covariance[7] = COV_XY
    covariance[35] = COV_YAW
    message.pose.covariance = covariance

    deadline = time.time() + PUBLISH_SEC
    count = 0
    while time.time() < deadline:
        message.header.stamp = node.get_clock().now().to_msg()
        publisher.publish(message)
        count += 1
        rclpy.spin_once(node, timeout_sec=0.5)

    print("초기 위치 %d회 발행: %.3f %.3f %.3f" % (count, x, y, yaw))
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
