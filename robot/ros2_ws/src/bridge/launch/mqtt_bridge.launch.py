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
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """브릿지 노드와 그 실행 인자를 정의한 launch 설명을 생성한다."""
    robot_id = LaunchConfiguration("robot_id")
    broker_host = LaunchConfiguration("broker_host")
    broker_port = LaunchConfiguration("broker_port")
    driver_type = LaunchConfiguration("driver_type")
    goal_timeout_seconds = LaunchConfiguration("goal_timeout_seconds")
    use_tls = LaunchConfiguration("use_tls")
    ca_certs = LaunchConfiguration("ca_certs")
    tls_insecure = LaunchConfiguration("tls_insecure")
    username = LaunchConfiguration("username")
    password = LaunchConfiguration("password")

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
            # 실브로커(i15e102.p.ssafy.io:8883)에 붙으려면 이 셋이 필요하다.
            # 과거엔 노드가 TLS 파라미터를 선언하지 않아 launch 경로로는 실브로커
            # 접속이 원천 불가능했다 — mqtt_bridge_node.py 참고.
            DeclareLaunchArgument(
                "use_tls", default_value="false",
                description="Enable TLS (required for the real EC2 broker on 8883)",
            ),
            DeclareLaunchArgument("ca_certs", default_value=""),
            DeclareLaunchArgument("tls_insecure", default_value="false"),
            DeclareLaunchArgument("username", default_value=""),
            DeclareLaunchArgument("password", default_value=""),
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
                        # 문자열 substitution 을 bool 로 명시 변환한다 — 안 하면
                        # rclpy 가 declare_parameter(..., False) 의 기본 타입과
                        # 문자열 "false" 를 맞춰 보다 ParameterTypeException 을
                        # 던진다(core 의 다른 launch 파일과 같은 패턴).
                        "use_tls": ParameterValue(use_tls, value_type=bool),
                        "ca_certs": ca_certs,
                        "tls_insecure": ParameterValue(tls_insecure, value_type=bool),
                        "username": username,
                        "password": password,
                    }
                ],
            ),
        ]
    )
