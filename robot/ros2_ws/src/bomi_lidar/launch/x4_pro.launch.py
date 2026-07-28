"""BOMI의 YDLIDAR X4-PRO 드라이버와 임시 정적 TF를 함께 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """X4-PRO 드라이버와 base_link 기준 LiDAR 좌표계를 실행한다.

    입력:
        launch 인자 port를 통해 LiDAR 시리얼 장치 경로를 전달받는다.

    출력:
        YDLIDAR 드라이버 노드와 base_link → laser_frame 정적 TF 노드를
        포함하는 LaunchDescription을 반환한다.

    주의사항:
        정적 TF 좌표는 실제 로봇 장착 전 임시값이다.
        실제 장착 후 LiDAR 위치와 방향을 측정해 수정해야 한다.
    """

    # bomi_lidar 패키지의 설치 경로에서 X4-PRO 설정 파일을 찾는다.
    package_share = Path(get_package_share_directory("bomi_lidar"))
    parameter_file = package_share / "config" / "x4_pro.yaml"

    # 실행 시 변경 가능한 LiDAR 시리얼 포트 경로이다.
    # 별도 인자를 지정하지 않으면 /dev/ttyUSB0을 사용한다.
    lidar_port = LaunchConfiguration("port")

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
            },
        ],
    )

    # 실제 로봇에 장착하기 전이므로 LiDAR와 로봇 중심을 같은 위치로 가정한다.
    # 실제 장착 후 x, y, z, roll, pitch, yaw 값을 측정해 수정해야 한다.
    lidar_static_transform = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="laser_static_transform",
        output="screen",
        arguments=[
            "--x",
            "0",
            "--y",
            "0",
            "--z",
            "0",
            "--roll",
            "0",
            "--pitch",
            "0",
            "--yaw",
            "0",
            "--frame-id",
            "base_link",
            "--child-frame-id",
            "laser_frame",
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
            lidar_driver,
            lidar_static_transform,
        ]
    )