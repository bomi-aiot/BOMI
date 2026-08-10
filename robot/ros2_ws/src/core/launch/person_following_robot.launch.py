"""실제 로봇의 사람 추종 구성 요소를 한 번에 실행한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """UDP 수신, LiDAR, 사람 추종 및 Pico 드라이버를 구성한다."""
    core_share = get_package_share_directory("core")
    lidar_share = get_package_share_directory("bomi_lidar")

    udp_bind_host = LaunchConfiguration("udp_bind_host")
    udp_bind_port = LaunchConfiguration("udp_bind_port")
    vision_topic = LaunchConfiguration("vision_topic")

    output_topic = LaunchConfiguration("output_topic")
    start_enabled = LaunchConfiguration("start_enabled")
    pico_port = LaunchConfiguration("pico_port")

    lidar_port = LaunchConfiguration("lidar_port")
    scan_topic = LaunchConfiguration("scan_topic")
    base_frame = LaunchConfiguration("base_frame")
    laser_frame = LaunchConfiguration("laser_frame")

    lidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                lidar_share,
                "launch",
                "x4_pro.launch.py",
            )
        ),
        launch_arguments={
            "port": lidar_port,
            "scan_topic": scan_topic,
            "base_frame": base_frame,
            "laser_frame": laser_frame,
        }.items(),
    )

    pico_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                core_share,
                "launch",
                "pico_driver.launch.py",
            )
        ),
        launch_arguments={
            "serial_port": pico_port,
        }.items(),
    )

    vision_udp_bridge = Node(
        package="core",
        executable="vision_udp_bridge",
        name="vision_udp_bridge",
        output="screen",
        parameters=[
            {
                "bind_host": udp_bind_host,
                "bind_port": ParameterValue(
                    udp_bind_port,
                    value_type=int,
                ),
                "output_topic": vision_topic,
            }
        ],
    )

    person_following_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                core_share,
                "launch",
                "person_following.launch.py",
            )
        ),
        launch_arguments={
            "input_topic": vision_topic,
            "output_topic": output_topic,
            "scan_topic": scan_topic,
            "use_lidar": "true",
            "start_enabled": start_enabled,
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "udp_bind_host",
                default_value="0.0.0.0",
                description="비전 UDP 패킷을 수신할 주소",
            ),
            DeclareLaunchArgument(
                "udp_bind_port",
                default_value="5005",
                description="비전 UDP 패킷을 수신할 포트",
            ),
            DeclareLaunchArgument(
                "vision_topic",
                default_value="/vision/follow_result",
                description="비전 추종 결과를 발행할 ROS 2 토픽",
            ),
            DeclareLaunchArgument(
                "output_topic",
                default_value="/cmd_vel",
                description="Pico에 전달할 속도 명령 토픽",
            ),
            # 보미야 회전 탐색(bomi_wake_search.launch.py)에서는 false 로 띄운다
            # — 탐색 노드가 사람을 찾은 뒤에야 /person_following/enable 로 켠다.
            # 기본값 true 는 이 launch 단독 사용의 기존 동작을 그대로 유지한다.
            DeclareLaunchArgument(
                "start_enabled",
                default_value="true",
                description="시작 시 추종 활성 여부. 회전 탐색 대본에서는 "
                            "false — wake_search 가 켠다",
            ),
            DeclareLaunchArgument(
                "pico_port",
                default_value="/dev/ttyACM0",
                description="Pico H 시리얼 장치 경로",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ttyUSB0",
                description="YDLIDAR 시리얼 장치 경로",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan",
                description="LiDAR LaserScan 토픽",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="로봇 기준 TF 프레임",
            ),
            DeclareLaunchArgument(
                "laser_frame",
                default_value="laser_frame",
                description="LiDAR TF 프레임",
            ),
            lidar_launch,
            pico_launch,
            vision_udp_bridge,
            person_following_launch,
        ]
    )
