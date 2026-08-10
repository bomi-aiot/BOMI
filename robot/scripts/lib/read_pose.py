"""map -> base_link 변환을 읽어 "x y yaw" 한 줄로 출력한다.

SLAM(매핑 중)이든 AMCL(주행 중)이든 map 프레임을 발행하는 쪽이 있으면 동작한다.
매핑을 끄기 전에 이 값을 받아 두면, 주행 단계에서 RViz의 2D Pose Estimate를
사람이 찍지 않아도 AMCL 초기 위치를 넣을 수 있다.
"""
import math
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

TIMEOUT_SEC = 25.0


def main() -> int:
    """map -> base_link 를 읽어 표준출력으로 내보낸다."""
    rclpy.init()
    node = Node("read_pose")
    buffer = Buffer()
    TransformListener(buffer, node)

    deadline = time.time() + TIMEOUT_SEC
    transform = None
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        try:
            transform = buffer.lookup_transform("map", "base_link", Time())
            break
        except Exception:
            continue

    if transform is None:
        print(
            "map -> base_link 를 읽지 못했습니다. "
            "slam_toolbox 나 AMCL 이 map 프레임을 내는지 확인하세요.",
            file=sys.stderr,
        )
        node.destroy_node()
        rclpy.shutdown()
        return 1

    position = transform.transform.translation
    rotation = transform.transform.rotation
    yaw = 2.0 * math.atan2(rotation.z, rotation.w)
    print("%.4f %.4f %.4f" % (position.x, position.y, yaw))

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
