"""LiDAR 전방 스캔에서 가장 가까운 장애물 거리를 발행한다."""

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32

from bomi_obstacle_detection.distance_calculator import (
    calculate_front_distance,
)


class FrontDistanceNode(Node):
    """
    LiDAR 전방의 가장 가까운 유효 거리를 계산하는 ROS 2 노드이다.

    입력:
        /scan 토픽의 sensor_msgs/msg/LaserScan 메시지

    출력:
        /bomi/lidar/front_distance 토픽의 std_msgs/msg/Float32 메시지

    주의사항:
        전방 각도 기본값은 -30도부터 30도까지이다.
        실제 로봇 장착 방향에 따라 값을 조정해야 한다.
    """

    def __init__(self) -> None:
        """ROS 2 파라미터, 구독자, 발행자를 초기화한다."""
        super().__init__("front_distance_node")

        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter(
            "output_topic",
            "/bomi/lidar/front_distance",
        )
        self.declare_parameter("front_angle_min_deg", -30.0)
        self.declare_parameter("front_angle_max_deg", 30.0)

        self.scan_topic = str(
            self.get_parameter("scan_topic").value
        )
        self.output_topic = str(
            self.get_parameter("output_topic").value
        )
        self.front_angle_min_deg = float(
            self.get_parameter("front_angle_min_deg").value
        )
        self.front_angle_max_deg = float(
            self.get_parameter("front_angle_max_deg").value
        )

        if self.front_angle_min_deg > self.front_angle_max_deg:
            raise ValueError(
                "front_angle_min_deg는 "
                "front_angle_max_deg보다 작거나 같아야 합니다."
            )

        # 계산된 전방 거리를 발행한다.
        self.front_distance_publisher = self.create_publisher(
            Float32,
            self.output_topic,
            10,
        )

        # LiDAR의 전체 거리 데이터를 구독한다.
        self.scan_subscription = self.create_subscription(
            LaserScan,
            self.scan_topic,
            self.scan_callback,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            "전방 거리 측정 노드를 시작했습니다. "
            f"입력={self.scan_topic}, "
            f"출력={self.output_topic}, "
            f"각도={self.front_angle_min_deg:.1f}°"
            f"~{self.front_angle_max_deg:.1f}°"
        )

    def scan_callback(self, scan: LaserScan) -> None:
        """
        전방의 가장 가까운 유효 거리를 계산하고 발행한다.

        입력:
            scan: LiDAR의 각도별 거리값이 담긴 LaserScan 메시지

        출력:
            반환값은 없으며 계산한 거리를 Float32 토픽으로 발행한다.

        주의사항:
            유효한 전방 거리값이 없으면 NaN을 발행한다.
        """
        front_distance = calculate_front_distance(
            scan=scan,
            front_angle_min_deg=self.front_angle_min_deg,
            front_angle_max_deg=self.front_angle_max_deg,
        )

        distance_message = Float32()
        distance_message.data = front_distance

        self.front_distance_publisher.publish(distance_message)


def main(args=None) -> None:
    """
    전방 거리 측정 ROS 2 노드를 실행한다.

    입력:
        args: ROS 2 실행 시 전달되는 명령행 인자

    출력:
        반환값은 없으며 노드를 종료할 때 관련 자원을 정리한다.
    """
    rclpy.init(args=args)
    node = FrontDistanceNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
