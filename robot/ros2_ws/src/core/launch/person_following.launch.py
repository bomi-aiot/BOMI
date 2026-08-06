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
    start_enabled = LaunchConfiguration("start_enabled")

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
            # "도착 후 사람 접근"(CLAUDE.md §3a, bridge 의 ApproachController)
            # 대본에서는 output_topic:=/cmd_vel start_enabled:=false 로 띄운다
            # — Nav2 유휴 시간에만 bridge 가 /person_following/enable 로 잠깐
            # 켠다. 기본값 true 는 이 launch 단독 사용(조이스틱 검증 등)의
            # 기존 동작을 그대로 유지한다.
            DeclareLaunchArgument(
                "start_enabled",
                default_value="true",
                description="시작 시 추종 활성 여부. 접근 대본에서는 false — "
                            "bridge 가 /person_following/enable 로 켠다",
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
                        "start_enabled": ParameterValue(
                            start_enabled,
                            value_type=bool,
                        ),
                    },
                ],
            ),
        ]
    )
