from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    mapping_share = Path(get_package_share_directory("mapping"))
    params_file = mapping_share / "config" / "slam_toolbox.yaml"

    slam_toolbox = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        output="screen",
        parameters=[str(params_file)],
    )

    return LaunchDescription([
        slam_toolbox,
    ])
