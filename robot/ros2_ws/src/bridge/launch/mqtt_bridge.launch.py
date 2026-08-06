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
    approach_enabled = LaunchConfiguration("approach_enabled")
    approach_duration_seconds = LaunchConfiguration("approach_duration_seconds")
    timed_drive_duration_seconds = LaunchConfiguration(
        "timed_drive_duration_seconds")
    timed_drive_linear_speed = LaunchConfiguration("timed_drive_linear_speed")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", default_value="robot-01"),
            DeclareLaunchArgument("broker_host", default_value="localhost"),
            DeclareLaunchArgument("broker_port", default_value="1883"),
            DeclareLaunchArgument("username", default_value=""),
            DeclareLaunchArgument("password", default_value=""),
            # 실브로커(i15e102.p.ssafy.io:8883)에 붙으려면 이 셋이 필요하다.
            # 과거엔 노드가 TLS 파라미터를 선언하지 않아 launch 경로로는 실브로커
            # 접속이 원천 불가능했다 — mqtt_bridge_node.py 참고.
            DeclareLaunchArgument(
                "use_tls", default_value="false",
                description="Enable TLS (required for the real EC2 broker on 8883)",
            ),
            DeclareLaunchArgument("ca_certs", default_value=""),
            DeclareLaunchArgument("tls_insecure", default_value="false"),
            DeclareLaunchArgument(
                "driver_type",
                default_value="mock",
                description="Robot driver to use: mock, nav2, timed, or forward_test",
            ),
            # driver_type:=timed — 지도·좌표 없이 "정해진 시간 직진"으로
            # 이동을 대체한다. Nav2(지도 작성) 병목을 우회해 계약 왕복·대화·
            # DB 종결까지 검증하기 위한 임시 수단이며, 목적지 구분이 없다.
            DeclareLaunchArgument(
                "timed_drive_duration_seconds", default_value="2.0",
                description="How long one NAVIGATE drives forward (timed driver)",
            ),
            DeclareLaunchArgument(
                "timed_drive_linear_speed", default_value="0.08",
                description="Forward speed in m/s (timed driver). Start low.",
            ),
            DeclareLaunchArgument(
                "cmd_vel_topic", default_value="/cmd_vel",
                description="Velocity topic the timed driver publishes to",
            ),
            DeclareLaunchArgument(
                "goal_timeout_seconds",
                default_value="120.0",
                description="Max seconds to wait for a Nav2 goal to finish",
            ),
            # driver_type:=forward_test — 백엔드 → MQTT → 모터 배선만 확인하는
            # 통신 테스트. 전용 토픽으로 발행해 twist_mux 아래에 두므로 조이스틱이
            # 항상 우선한다(launch/backend_drive_test.launch.py 가 이걸 감싼다).
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
            # 도착 후 사람 접근(CLAUDE.md §3a). 킬 스위치 — 기본 꺼짐. V4
            # 실기에서 불안정하면 approach_enabled:=false 로 재실행해 검증된
            # "거실 좌표 도착까지"로 되돌린다(person_follower 재시작 불필요 —
            # 그쪽 노드는 start_enabled 와 무관하게 항상 이 스위치를 따른다).
            DeclareLaunchArgument(
                "approach_enabled", default_value="false",
                description="Enable follow-the-person after LIVING_ROOM arrival",
            ),
            DeclareLaunchArgument(
                "approach_duration_seconds", default_value="15.0",
                description="Max seconds to keep person-following on after arrival",
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
                        "driver_type": driver_type,
                        # 문자열 substitution 을 bool/float 으로 명시 변환한다 —
                        # 안 하면 rclpy 가 declare_parameter(..., False) 의 기본
                        # 타입과 문자열 "false" 를 맞춰 보다
                        # ParameterTypeException 을 던진다(core 의 다른 launch
                        # 파일과 같은 패턴).
                        "use_tls": ParameterValue(use_tls, value_type=bool),
                        "ca_certs": ca_certs,
                        "tls_insecure": ParameterValue(tls_insecure, value_type=bool),
                        "goal_timeout_seconds": ParameterValue(
                            goal_timeout_seconds, value_type=float),
                        "test_forward_speed_m_s": ParameterValue(
                            test_forward_speed_m_s, value_type=float),
                        "test_forward_duration_sec": ParameterValue(
                            test_forward_duration_sec, value_type=float),
                        "test_publish_rate_hz": ParameterValue(
                            test_publish_rate_hz, value_type=float),
                        "test_cmd_vel_topic": test_cmd_vel_topic,
                        "approach_enabled": ParameterValue(
                            approach_enabled, value_type=bool),
                        "approach_duration_seconds": ParameterValue(
                            approach_duration_seconds, value_type=float),
                        "timed_drive_duration_seconds": ParameterValue(
                            timed_drive_duration_seconds, value_type=float),
                        "timed_drive_linear_speed": ParameterValue(
                            timed_drive_linear_speed, value_type=float),
                        "cmd_vel_topic": cmd_vel_topic,
                    }
                ],
            ),
        ]
    )
