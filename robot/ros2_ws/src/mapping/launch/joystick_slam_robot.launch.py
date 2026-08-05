"""실제 조이스틱, Pico, X4-PRO와 SLAM Toolbox를 함께 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """실제 로봇의 수동 주행과 온라인 지도 생성을 구성한다.

    Pico가 /odom과 odom → base_link TF를 발행하므로 RF2O는 실행하지 않는다.
    """

    mapping_share = Path(get_package_share_directory("mapping"))
    core_share = Path(get_package_share_directory("core"))
    lidar_share = Path(get_package_share_directory("bomi_lidar"))

    joystick_launch = core_share / "launch" / "joystick_teleop.launch.py"
    pico_launch = core_share / "launch" / "pico_driver.launch.py"
    lidar_launch = lidar_share / "launch" / "x4_pro.launch.py"

    slam_params = mapping_share / "config" / "slam_toolbox_real.yaml"
    rviz_config = mapping_share / "rviz" / "mapping.rviz"

    use_sim_time = LaunchConfiguration("use_sim_time")
    use_rviz = LaunchConfiguration("use_rviz")

    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")
    pico_port = LaunchConfiguration("pico_port")
    lidar_port = LaunchConfiguration("lidar_port")

    scan_topic = LaunchConfiguration("scan_topic")
    base_frame = LaunchConfiguration("base_frame")
    odom_frame = LaunchConfiguration("odom_frame")
    laser_frame = LaunchConfiguration("laser_frame")

    joystick = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(joystick_launch)),
        launch_arguments={
            "cmd_vel_topic": cmd_vel_topic,
        }.items(),
    )

    pico_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(pico_launch)),
        launch_arguments={
            "serial_port": pico_port,
        }.items(),
    )

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(lidar_launch)),
        launch_arguments={
            "port": lidar_port,
            "scan_topic": scan_topic,
            "base_frame": base_frame,
            "laser_frame": laser_frame,
        }.items(),
    )

    slam_toolbox = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        output="screen",
        parameters=[
            str(slam_params),
            {
                "use_sim_time": ParameterValue(
                    use_sim_time,
                    value_type=bool,
                ),
                "scan_topic": scan_topic,
                "base_frame": base_frame,
                "odom_frame": odom_frame,
            },
        ],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        condition=IfCondition(use_rviz),
        arguments=["-d", str(rviz_config)],
        parameters=[
            {
                "use_sim_time": ParameterValue(
                    use_sim_time,
                    value_type=bool,
                )
            }
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="실제 장비에서는 시스템 시간을 사용",
            ),
            DeclareLaunchArgument(
                "use_rviz",
                default_value="true",
                description="RViz를 함께 실행할지 여부",
            ),
            DeclareLaunchArgument(
                "cmd_vel_topic",
                default_value="/cmd_vel",
                description="조이스틱 명령과 Pico가 공유할 속도 토픽",
            ),
            DeclareLaunchArgument(
                "pico_port",
                default_value="/dev/ttyACM0",
                description="Pico H USB CDC 장치 경로",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ttyUSB0",
                description="YDLIDAR 시리얼 장치 경로",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan",
                description="YDLIDAR와 SLAM이 공유할 LaserScan 토픽",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="로봇 기준 프레임",
            ),
            DeclareLaunchArgument(
                "odom_frame",
                default_value="odom",
                description="Pico가 발행하는 odometry 부모 프레임",
            ),
            DeclareLaunchArgument(
                "laser_frame",
                default_value="laser_frame",
                description="LiDAR LaserScan과 정적 TF 프레임",
            ),
            joystick,
            pico_driver,
            lidar,
            slam_toolbox,
            rviz,
        ]
    )
