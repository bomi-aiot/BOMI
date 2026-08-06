"""BOMI의 YDLIDAR X4-PRO 드라이버와 장착 위치 정적 TF를 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """X4-PRO 드라이버와 base_link 기준 LiDAR 좌표계를 실행한다.

    입력:
        launch 인자로 LiDAR 시리얼 경로, scan 토픽과 TF 프레임을 받는다.

    출력:
        YDLIDAR 드라이버 노드와 base_link → laser_frame 정적 TF 노드를
        포함하는 LaunchDescription을 반환한다.

    주의사항:
        정적 TF 기본값은 실측 전 임시값이다. 실제 장착 위치와 방향을
        launch 인자로 전달해야 한다.
    """

    # bomi_lidar 패키지의 설치 경로에서 X4-PRO 설정 파일을 찾는다.
    package_share = Path(get_package_share_directory("bomi_lidar"))
    parameter_file = package_share / "config" / "x4_pro.yaml"

    # 실행 환경에 따라 장치 경로와 ROS 인터페이스를 변경할 수 있다.
    lidar_port = LaunchConfiguration("port")
    scan_topic = LaunchConfiguration("scan_topic")
    base_frame = LaunchConfiguration("base_frame")
    laser_frame = LaunchConfiguration("laser_frame")
    laser_x = LaunchConfiguration("laser_x")
    laser_y = LaunchConfiguration("laser_y")
    laser_z = LaunchConfiguration("laser_z")
    laser_roll = LaunchConfiguration("laser_roll")
    laser_pitch = LaunchConfiguration("laser_pitch")
    laser_yaw = LaunchConfiguration("laser_yaw")

    # YDLIDAR X4-PRO 드라이버 노드이다.
    # YAML 설정을 먼저 적용하고 launch 인자로 전달된 port 값을 덮어쓴다.
    lidar_driver = Node(
        package="ydlidar_ros2_driver",
        executable="ydlidar_ros2_driver_node",
        name="ydlidar_ros2_driver_node",
        output="screen",
        parameters=[
            str(parameter_file),
            {
                "port": lidar_port,
                "frame_id": laser_frame,
            },
        ],
        remappings=[
            ("scan", scan_topic),
        ],
    )

    # 기본값은 LiDAR와 로봇 중심을 같은 위치로 가정한다. 실기 지도 생성 시에는
    # 측정한 x, y, z, roll, pitch, yaw 값을 launch 인자로 전달한다.
    lidar_static_transform = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="laser_static_transform",
        output="screen",
        arguments=[
            "--x",
            laser_x,
            "--y",
            laser_y,
            "--z",
            laser_z,
            "--roll",
            laser_roll,
            "--pitch",
            laser_pitch,
            "--yaw",
            laser_yaw,
            "--frame-id",
            base_frame,
            "--child-frame-id",
            laser_frame,
        ],
    )

    return LaunchDescription(
        [
            # LiDAR 포트를 실행 시 변경할 수 있도록 launch 인자를 선언한다.
            DeclareLaunchArgument(
                "port",
                default_value="/dev/ttyUSB0",
                description="YDLIDAR가 연결된 시리얼 장치 경로",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan",
                description="LaserScan을 발행할 ROS 2 토픽",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="LiDAR 정적 TF의 부모 프레임",
            ),
            DeclareLaunchArgument(
                "laser_frame",
                default_value="laser_frame",
                description="LaserScan과 정적 TF에서 사용할 LiDAR 프레임",
            ),
            DeclareLaunchArgument(
                "laser_x",
                default_value="0.0",
                description="base_link 기준 LiDAR 전방 위치(m), 실측 전 0.0",
            ),
            DeclareLaunchArgument(
                "laser_y",
                default_value="0.0",
                description="base_link 기준 LiDAR 좌측 위치(m), 실측 전 0.0",
            ),
            DeclareLaunchArgument(
                "laser_z",
                default_value="0.0",
                description="base_link 기준 LiDAR 높이(m), 실측 전 0.0",
            ),
            DeclareLaunchArgument(
                "laser_roll",
                default_value="0.0",
                description="base_link 기준 LiDAR roll(rad), 실측 전 0.0",
            ),
            DeclareLaunchArgument(
                "laser_pitch",
                default_value="0.0",
                description="base_link 기준 LiDAR pitch(rad), 실측 전 0.0",
            ),
            DeclareLaunchArgument(
                "laser_yaw",
                default_value="0.0",
                description="base_link 기준 LiDAR yaw(rad), 실측 전 0.0",
            ),
            lidar_driver,
            lidar_static_transform,
        ]
    )
