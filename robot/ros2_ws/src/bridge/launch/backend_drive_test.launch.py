"""
MQTT NAVIGATE 2초 전진 테스트용 브릿지와 twist_mux를 실행한다.

실제 Pico 드라이버는 자동으로 시작하지 않는다. 속도 토픽과 MQTT 결과를 먼저
확인한 뒤 별도 터미널에서 core의 pico_driver.launch.py를 실행한다.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """forward_test 브릿지와 전용 mux 입력을 구성한다."""
    bridge_share = get_package_share_directory("bridge")
    core_share = get_package_share_directory("core")
    bridge_launch = os.path.join(
        bridge_share, "launch", "mqtt_bridge.launch.py"
    )
    mux_config = os.path.join(core_share, "config", "twist_mux.yaml")

    launch_arguments = {
        "robot_id": LaunchConfiguration("robot_id"),
        "broker_host": LaunchConfiguration("broker_host"),
        "broker_port": LaunchConfiguration("broker_port"),
        "username": LaunchConfiguration("username"),
        "password": LaunchConfiguration("password"),
        "use_tls": LaunchConfiguration("use_tls"),
        "ca_certs": LaunchConfiguration("ca_certs"),
        "tls_insecure": LaunchConfiguration("tls_insecure"),
        "driver_type": "forward_test",
        "test_forward_speed_m_s": LaunchConfiguration(
            "forward_speed_m_s"
        ),
        "test_forward_duration_sec": LaunchConfiguration(
            "forward_duration_sec"
        ),
        "test_publish_rate_hz": LaunchConfiguration("publish_rate_hz"),
        "test_cmd_vel_topic": "/cmd_vel_backend_test",
    }

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", default_value="robot-01"),
            DeclareLaunchArgument("broker_host", default_value="localhost"),
            DeclareLaunchArgument("broker_port", default_value="1883"),
            DeclareLaunchArgument("username", default_value=""),
            DeclareLaunchArgument("password", default_value=""),
            DeclareLaunchArgument("use_tls", default_value="false"),
            DeclareLaunchArgument("ca_certs", default_value=""),
            DeclareLaunchArgument("tls_insecure", default_value="false"),
            DeclareLaunchArgument("forward_speed_m_s", default_value="0.08"),
            DeclareLaunchArgument("forward_duration_sec", default_value="2.0"),
            DeclareLaunchArgument("publish_rate_hz", default_value="10.0"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(bridge_launch),
                launch_arguments=launch_arguments.items(),
            ),
            Node(
                package="twist_mux",
                executable="twist_mux",
                name="twist_mux",
                parameters=[mux_config],
                remappings=[("/cmd_vel_out", "/cmd_vel")],
                output="screen",
            ),
        ]
    )
