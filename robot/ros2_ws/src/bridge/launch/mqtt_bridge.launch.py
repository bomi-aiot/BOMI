"""MQTT 브릿지 노드를 드라이버 선택/타임아웃 파라미터와 함께 실행하는 launch.

이 launch는 브릿지 노드 하나만 실행한다. 지도 서버, AMCL, Nav2, MQTT 브로커는
별도로 실행한다(시뮬레이션은 core의 bomi_navigation_sim.launch.py 사용).
driver_type:=nav2 로 실행하면 실제 Nav2 주행 드라이버를 사용하며, 이때는 Nav2가
먼저 활성화되어 있어야 한다.

실행 예:

    ros2 launch bridge mqtt_bridge.launch.py \
        driver_type:=nav2 broker_host:=localhost goal_timeout_seconds:=120.0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """브릿지 노드와 그 실행 인자를 정의한 launch 설명을 생성한다."""
    robot_id = LaunchConfiguration("robot_id")
    broker_host = LaunchConfiguration("broker_host")
    broker_port = LaunchConfiguration("broker_port")
    driver_type = LaunchConfiguration("driver_type")
    goal_timeout_seconds = LaunchConfiguration("goal_timeout_seconds")

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", default_value="robot-01"),
            DeclareLaunchArgument("broker_host", default_value="localhost"),
            DeclareLaunchArgument("broker_port", default_value="1883"),
            DeclareLaunchArgument(
                "driver_type",
                default_value="mock",
                description="Robot driver to use: mock or nav2",
            ),
            DeclareLaunchArgument(
                "goal_timeout_seconds",
                default_value="120.0",
                description="Max seconds to wait for a Nav2 goal to finish",
            ),
            Node(
                package="bridge",
                executable="mqtt_bridge",
                name="mqtt_bridge",
                output="screen",
                parameters=[
                    {
                        "robot_id": robot_id,
                        "broker_host": broker_host,
                        "broker_port": broker_port,
                        "driver_type": driver_type,
                        "goal_timeout_seconds": goal_timeout_seconds,
                    }
                ],
            ),
        ]
    )
