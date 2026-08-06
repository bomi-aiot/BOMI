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
    username = LaunchConfiguration("username")
    password = LaunchConfiguration("password")
    use_tls = LaunchConfiguration("use_tls")
    ca_certs = LaunchConfiguration("ca_certs")
    tls_insecure = LaunchConfiguration("tls_insecure")
    driver_type = LaunchConfiguration("driver_type")
    goal_timeout_seconds = LaunchConfiguration("goal_timeout_seconds")
    test_forward_speed_m_s = LaunchConfiguration("test_forward_speed_m_s")
    test_forward_duration_sec = LaunchConfiguration("test_forward_duration_sec")
    test_publish_rate_hz = LaunchConfiguration("test_publish_rate_hz")
    test_cmd_vel_topic = LaunchConfiguration("test_cmd_vel_topic")

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
            DeclareLaunchArgument(
                "driver_type",
                default_value="mock",
                description="Robot driver: mock, nav2 or forward_test",
            ),
            DeclareLaunchArgument(
                "goal_timeout_seconds",
                default_value="120.0",
                description="Max seconds to wait for a Nav2 goal to finish",
            ),
            DeclareLaunchArgument(
                "test_forward_speed_m_s",
                default_value="0.08",
                description="Forward-test linear speed in m/s",
            ),
            DeclareLaunchArgument(
                "test_forward_duration_sec",
                default_value="2.0",
                description="Forward-test movement duration in seconds",
            ),
            DeclareLaunchArgument(
                "test_publish_rate_hz",
                default_value="10.0",
                description="Forward-test Twist publish rate in Hz",
            ),
            DeclareLaunchArgument(
                "test_cmd_vel_topic",
                default_value="/cmd_vel_backend_test",
                description="Forward-test twist_mux input topic",
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
                        "username": username,
                        "password": password,
                        "use_tls": use_tls,
                        "ca_certs": ca_certs,
                        "tls_insecure": tls_insecure,
                        "driver_type": driver_type,
                        "goal_timeout_seconds": goal_timeout_seconds,
                        "test_forward_speed_m_s": test_forward_speed_m_s,
                        "test_forward_duration_sec": test_forward_duration_sec,
                        "test_publish_rate_hz": test_publish_rate_hz,
                        "test_cmd_vel_topic": test_cmd_vel_topic,
                    }
                ],
            ),
        ]
    )
