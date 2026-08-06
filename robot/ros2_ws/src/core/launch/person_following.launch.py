"""사람 추종 ROS2 노드를 실행한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """사람 추종 노드와 실행 인자를 구성한다."""
    package_share = get_package_share_directory("core")

    parameter_file = os.path.join(
        package_share,
        "config",
        "person_following.yaml",
    )

    output_topic = LaunchConfiguration("output_topic")
    use_lidar = LaunchConfiguration("use_lidar")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "output_topic",
                default_value="/cmd_vel_follow",
                description="사람 추종 속도 명령을 발행할 토픽",
            ),
            DeclareLaunchArgument(
                "use_lidar",
                default_value="true",
                description="LiDAR 장애물 정지 기능 사용 여부",
            ),
            Node(
                package="core",
                executable="person_follower",
                name="person_follower",
                output="screen",
                parameters=[
                    parameter_file,
                    {
                        "output_topic": output_topic,
                        "use_lidar": ParameterValue(
                            use_lidar,
                            value_type=bool,
                        ),
                    },
                ],
            ),
        ]
    )
