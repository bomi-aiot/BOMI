"""보미야 호출 → 회전 탐색 → 사람 추종 시나리오를 명령 한 줄로 실행한다.

무엇이 함께 뜨는가
    ROS 2 노드      LiDAR, Pico 드라이버, 비전 UDP 브릿지, person_follower,
                    twist_mux, wake_search, (선택) MQTT 브릿지
    일반 프로세스   ai_vision(카메라+YOLO), ai_chat(마이크+웨이크워드)

왜 ExecuteProcess 로 파이썬 프로그램을 띄우는가
    ai_vision 과 ai_chat 은 ROS 2 노드가 아니고, 서로 다른 가상환경을 쓴다.
    특히 paho-mqtt 는 ai_chat 이 1.x, ROS 2 쪽 bridge 가 2.x 로 서로 호환되지
    않는다. 각 가상환경의 python 실행 파일 경로를 직접 지정하면 activate 없이
    환경이 섞이지 않는다.

왜 순서를 지연시키는가
    USB 장치와 모델 로딩이 끝나기 전에 다음 프로세스가 말을 걸면 죽는다.
    LiDAR·Pico(0초) → ai_vision(모델 로딩 여유) → ai_chat → wake_search 순으로
    띄운다. wake_search 는 /odom 이 이미 흐르고 있어야 탐색을 시작할 수 있다.

하나가 죽으면 전부 내린다 (구현계획 결정 8)
    카메라가 죽었는데 바퀴 드라이버만 살아 있으면 마지막 명령대로 계속 돌 수
    있다. on_exit=Shutdown() 으로 한 배를 타게 한다.

실행 예:

.. code-block:: bash

    ros2 launch core bomi_wake_search.launch.py

    # 장치 경로가 udev 로 고정돼 있지 않다면
    ros2 launch core bomi_wake_search.launch.py \\
        pico_port:=/dev/ttyACM0 lidar_port:=/dev/ttyUSB0

    # MQTT 까지 함께 (백엔드 연동 시연)
    ros2 launch core bomi_wake_search.launch.py \\
        use_mqtt_bridge:=true robot_id:=bomi-AA001 \\
        broker_host:=i15e102.p.ssafy.io broker_port:=8883 use_tls:=true

    # 선언된 인자 전체 보기
    ros2 launch core bomi_wake_search.launch.py --show-args
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    Shutdown,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _default_repo_root() -> str:
    """저장소 루트 기본값. 환경변수 BOMI_ROOT 가 있으면 그것을 쓴다.

    젯슨 기본 설치 경로는 /home/ssafy/S15P11E102 다
    (iot/jetson/bomi-robot.service 의 WorkingDirectory 기준). 개발 PC 에서는
    BOMI_ROOT 를 지정해 그대로 재사용한다.
    """
    return os.environ.get("BOMI_ROOT", "/home/ssafy/S15P11E102")


def generate_launch_description() -> LaunchDescription:
    """시나리오에 필요한 모든 프로세스를 하나의 launch 로 묶는다."""
    core_share = get_package_share_directory("core")
    repo_root = _default_repo_root()

    pico_port = LaunchConfiguration("pico_port")
    lidar_port = LaunchConfiguration("lidar_port")
    scan_topic = LaunchConfiguration("scan_topic")
    vision_topic = LaunchConfiguration("vision_topic")
    vision_udp_port = LaunchConfiguration("vision_udp_port")

    use_ai_vision = LaunchConfiguration("use_ai_vision")
    use_ai_chat = LaunchConfiguration("use_ai_chat")
    use_mqtt_bridge = LaunchConfiguration("use_mqtt_bridge")

    ai_vision_python = LaunchConfiguration("ai_vision_python")
    ai_vision_dir = LaunchConfiguration("ai_vision_dir")
    ai_chat_python = LaunchConfiguration("ai_chat_python")
    ai_chat_dir = LaunchConfiguration("ai_chat_dir")
    robot_udp_host = LaunchConfiguration("robot_udp_host")

    robot_id = LaunchConfiguration("robot_id")
    broker_host = LaunchConfiguration("broker_host")
    broker_port = LaunchConfiguration("broker_port")
    mqtt_username = LaunchConfiguration("mqtt_username")
    mqtt_password = LaunchConfiguration("mqtt_password")
    use_tls = LaunchConfiguration("use_tls")

    wake_search_params = os.path.join(
        core_share, "config", "wake_search.yaml")
    twist_mux_params = os.path.join(core_share, "config", "twist_mux.yaml")

    # ── 1) 하드웨어 + 추종 (기존 launch 재사용) ─────────────────────────────
    # output_topic 을 /cmd_vel_follow 로 되돌린다. twist_mux 가 우선순위로
    # 중재해 최종 /cmd_vel 을 만들기 때문이다. start_enabled 는 false —
    # wake_search 가 사람을 찾은 뒤에만 켠다.
    robot_stack = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(core_share, "launch",
                         "person_following_robot.launch.py")
        ),
        launch_arguments={
            "pico_port": pico_port,
            "lidar_port": lidar_port,
            "scan_topic": scan_topic,
            "vision_topic": vision_topic,
            "udp_bind_port": vision_udp_port,
            "output_topic": "/cmd_vel_follow",
            "start_enabled": "false",
        }.items(),
    )

    # ── 2) 속도 명령 중재 ───────────────────────────────────────────────────
    # 조이스틱(100) > 추종(85) > 회전 탐색(80) > 통신 테스트(75) > 키보드(50).
    # 조이스틱이 항상 이기므로 실기 테스트 중 사람이 언제든 개입할 수 있다.
    twist_mux = Node(
        package="twist_mux",
        executable="twist_mux",
        name="twist_mux",
        output="screen",
        parameters=[twist_mux_params],
        remappings=[("cmd_vel_out", "/cmd_vel")],
        on_exit=Shutdown(),
    )

    # ── 3) 회전 탐색 ────────────────────────────────────────────────────────
    wake_search = Node(
        package="core",
        executable="wake_search",
        name="wake_search",
        output="screen",
        parameters=[
            wake_search_params,
            {
                "vision_topic": vision_topic,
            },
        ],
        on_exit=Shutdown(),
    )

    # ── 4) AI 비전 (별도 가상환경) ──────────────────────────────────────────
    ai_vision_process = ExecuteProcess(
        condition=IfCondition(use_ai_vision),
        cmd=[
            ai_vision_python, "-m", "bomi_vision.udp_main",
            "--host", robot_udp_host,
            "--port", vision_udp_port,
        ],
        cwd=ai_vision_dir,
        name="ai_vision",
        output="screen",
        # PYTHONPATH 가 ROS 2 것으로 오염되면 가상환경 패키지가 가려진다.
        additional_env={"PYTHONPATH": ""},
        on_exit=Shutdown(),
    )

    # ── 5) AI 대화 (별도 가상환경) ──────────────────────────────────────────
    # AI_CHAT_ENV_FILE 을 절대경로로 준다. .env 는 실행 폴더 기준으로 읽히므로
    # systemd 처럼 작업 폴더가 다른 환경에서 조용히 비활성화되는 것을 막는다.
    ai_chat_process = ExecuteProcess(
        condition=IfCondition(use_ai_chat),
        cmd=[ai_chat_python, "-m", "bomi_ai_chat"],
        cwd=ai_chat_dir,
        name="ai_chat",
        output="screen",
        additional_env={
            "PYTHONPATH": "",
            "AI_CHAT_ENV_FILE": PathJoinSubstitution([ai_chat_dir, ".env"]),
        },
        on_exit=Shutdown(),
    )

    # ── 6) MQTT 브릿지 (선택) ───────────────────────────────────────────────
    # 백엔드 FOLLOW_START 를 받아 /wake_search/start 를 켠다.
    mqtt_bridge = Node(
        condition=IfCondition(use_mqtt_bridge),
        package="bridge",
        executable="mqtt_bridge",
        name="mqtt_bridge",
        output="screen",
        parameters=[{
            "robot_id": robot_id,
            "broker_host": broker_host,
            "broker_port": ParameterValue(broker_port, value_type=int),
            "username": mqtt_username,
            "password": mqtt_password,
            "use_tls": ParameterValue(use_tls, value_type=bool),
            # 회전 탐색이 이 시나리오의 주행이므로 주행 드라이버는 쓰지 않는다.
            "driver_type": "mock",
            "search_enabled": True,
            "search_start_topic": "/wake_search/start",
        }],
        on_exit=Shutdown(),
    )

    return LaunchDescription([
        # ── 장치 ────────────────────────────────────────────────────────────
        DeclareLaunchArgument(
            "pico_port", default_value="/dev/ttyACM0",
            description="Pico H 시리얼 장치. udev 를 쓰면 /dev/bomi-pico"),
        DeclareLaunchArgument(
            "lidar_port", default_value="/dev/ttyUSB0",
            description="YDLIDAR 시리얼 장치. udev 를 쓰면 /dev/bomi-lidar"),
        DeclareLaunchArgument("scan_topic", default_value="/scan"),
        DeclareLaunchArgument(
            "vision_topic", default_value="/vision/follow_result"),
        DeclareLaunchArgument(
            "vision_udp_port", default_value="5005",
            description="ai_vision → vision_udp_bridge 수신 포트"),

        # ── 구성 요소 켜고 끄기 ─────────────────────────────────────────────
        DeclareLaunchArgument(
            "use_ai_vision", default_value="true",
            description="카메라+YOLO 프로세스를 함께 띄울지"),
        DeclareLaunchArgument(
            "use_ai_chat", default_value="true",
            description="마이크+웨이크워드 프로세스를 함께 띄울지"),
        DeclareLaunchArgument(
            "use_mqtt_bridge", default_value="false",
            description="백엔드 MQTT 브릿지를 함께 띄울지"),

        # ── 가상환경 경로 (젯슨 기본 설치 경로 기준) ────────────────────────
        DeclareLaunchArgument(
            "ai_vision_dir",
            default_value=os.path.join(repo_root, "robot", "ai_vision"),
            description="ai_vision 프로젝트 폴더"),
        DeclareLaunchArgument(
            "ai_vision_python",
            default_value=os.path.join(
                repo_root, "robot", "ai_vision", "venv", "bin", "python"),
            description="ai_vision 가상환경의 python 실행 파일"),
        DeclareLaunchArgument(
            "ai_chat_dir",
            default_value=os.path.join(repo_root, "robot", "ai_chat"),
            description="ai_chat 프로젝트 폴더"),
        DeclareLaunchArgument(
            "ai_chat_python",
            default_value=os.path.join(
                repo_root, "robot", "ai_chat", "venv", "bin", "python"),
            description="ai_chat 가상환경의 python 실행 파일"),
        DeclareLaunchArgument(
            "robot_udp_host", default_value="127.0.0.1",
            description="ai_vision 이 결과를 보낼 주소. 같은 젯슨이면 루프백"),

        # ── MQTT ────────────────────────────────────────────────────────────
        DeclareLaunchArgument("robot_id", default_value="bomi-AA001"),
        DeclareLaunchArgument("broker_host", default_value="localhost"),
        DeclareLaunchArgument("broker_port", default_value="1883"),
        DeclareLaunchArgument("mqtt_username", default_value=""),
        DeclareLaunchArgument("mqtt_password", default_value=""),
        DeclareLaunchArgument("use_tls", default_value="false"),

        # ── 기동 순서 ───────────────────────────────────────────────────────
        # 0초: 하드웨어와 중재기. /odom 과 /scan 이 먼저 흘러야 한다.
        robot_stack,
        twist_mux,
        # 3초: 카메라와 YOLO. 모델 로딩에 시간이 걸린다.
        TimerAction(period=3.0, actions=[ai_vision_process]),
        # 6초: 마이크와 웨이크워드.
        TimerAction(period=6.0, actions=[ai_chat_process]),
        # 8초: 탐색 노드. 이 시점이면 /odom 이 확실히 흐른다.
        TimerAction(period=8.0, actions=[wake_search]),
        # 10초: MQTT 브릿지. 로봇이 명령을 받을 준비가 끝난 뒤에 붙는다.
        TimerAction(period=10.0, actions=[mqtt_bridge]),
    ])
