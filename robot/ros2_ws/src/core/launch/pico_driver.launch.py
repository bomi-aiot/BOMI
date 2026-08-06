"""Pico H 시리얼 드라이버 ROS2 노드를 실행한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Pico 드라이버 노드와 실행 인자를 구성한다."""
    package_share = get_package_share_directory("core")

    parameter_file = os.path.join(
        package_share,
        "config",
        "pico_driver.yaml",
    )

    serial_port = LaunchConfiguration("serial_port")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/ttyACM0",
                description="Pico H가 잡히는 USB CDC 장치 경로",
            ),
            Node(
                package="core",
                executable="pico_driver",
                name="pico_driver",
                output="screen",
                parameters=[
                    parameter_file,
                    {"serial_port": serial_port},
                ],
            ),
        ]
    )
