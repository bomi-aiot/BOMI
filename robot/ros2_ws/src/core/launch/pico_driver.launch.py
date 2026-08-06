"""Pico H 시리얼 드라이버 ROS2 노드를 실행한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Pico 드라이버 노드와 실행 인자를 구성한다."""
    package_share = get_package_share_directory("core")

    parameter_file = os.path.join(
        package_share,
        "config",
        "pico_driver.yaml",
    )

    serial_port = LaunchConfiguration("serial_port")
    publish_tf = LaunchConfiguration("publish_tf")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/ttyACM0",
                description="Pico H가 잡히는 USB CDC 장치 경로",
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description=(
                    "odom → base_link TF를 직접 발행할지 여부. "
                    "EKF를 함께 실행할 때는 false로 넘겨 TF 충돌을 막는다."
                ),
            ),
            Node(
                package="core",
                executable="pico_driver",
                name="pico_driver",
                output="screen",
                parameters=[
                    parameter_file,
                    {
                        "serial_port": serial_port,
                        "publish_tf": ParameterValue(
                            publish_tf,
                            value_type=bool,
                        ),
                    },
                ],
            ),
        ]
    )
