"""BOMI의 LiDAR 전방 거리 측정 노드를 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """전방 거리 측정 노드의 실행 구성을 반환한다."""
    package_share = Path(
        get_package_share_directory("bomi_obstacle_detection")
    )
    parameter_file = package_share / "config" / "front_distance.yaml"

    front_distance_node = Node(
        package="bomi_obstacle_detection",
        executable="front_distance_node",
        name="front_distance_node",
        output="screen",
        parameters=[str(parameter_file)],
    )

    return LaunchDescription([front_distance_node])
