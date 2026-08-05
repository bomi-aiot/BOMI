"""실제 YDLIDAR, RF2O 오도메트리와 SLAM Toolbox를 함께 실행한다."""

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
    """
    실물 LiDAR 지도 생성에 필요한 노드와 설정을 구성한다.

    입력:
        launch argument로 장치 경로, 토픽, TF 프레임, RF2O 주기와
        RViz 실행 여부를 받는다.

    출력:
        선택적인 YDLIDAR 드라이버, RF2O, SLAM Toolbox와 RViz를 포함하는
        LaunchDescription을 반환한다.

    주의사항:
        시뮬레이션 launch와 동시에 실행하면 odom TF가 중복되므로 함께
        실행하지 않는다. LiDAR를 별도 실행할 때는 include_lidar를 false로
        지정하고 base_link에서 LaserScan frame까지의 TF를 제공해야 한다.
    """
    mapping_share = Path(get_package_share_directory("mapping"))
    lidar_share = Path(get_package_share_directory("bomi_lidar"))

    slam_params = mapping_share / "config" / "slam_toolbox_real.yaml"
    rviz_config = mapping_share / "rviz" / "mapping.rviz"
    lidar_launch = lidar_share / "launch" / "x4_pro.launch.py"

    use_sim_time = LaunchConfiguration("use_sim_time")
    scan_topic = LaunchConfiguration("scan_topic")
    odom_topic = LaunchConfiguration("odom_topic")
    base_frame = LaunchConfiguration("base_frame")
    odom_frame = LaunchConfiguration("odom_frame")
    laser_frame = LaunchConfiguration("laser_frame")
    laser_x = LaunchConfiguration("laser_x")
    laser_y = LaunchConfiguration("laser_y")
    laser_z = LaunchConfiguration("laser_z")
    laser_roll = LaunchConfiguration("laser_roll")
    laser_pitch = LaunchConfiguration("laser_pitch")
    laser_yaw = LaunchConfiguration("laser_yaw")
    rf2o_frequency = LaunchConfiguration("rf2o_frequency")
    lidar_port = LaunchConfiguration("lidar_port")
    include_lidar = LaunchConfiguration("include_lidar")
    use_rviz = LaunchConfiguration("use_rviz")

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(lidar_launch)),
        condition=IfCondition(include_lidar),
        launch_arguments={
            "port": lidar_port,
            "scan_topic": scan_topic,
            "base_frame": base_frame,
            "laser_frame": laser_frame,
            "laser_x": laser_x,
            "laser_y": laser_y,
            "laser_z": laser_z,
            "laser_roll": laser_roll,
            "laser_pitch": laser_pitch,
            "laser_yaw": laser_yaw,
        }.items(),
    )

    rf2o = Node(
        package="rf2o_laser_odometry",
        executable="rf2o_laser_odometry_node",
        name="rf2o_laser_odometry",
        output="screen",
        parameters=[
            {
                "use_sim_time": ParameterValue(
                    use_sim_time,
                    value_type=bool,
                ),
                "laser_scan_topic": scan_topic,
                "odom_topic": odom_topic,
                "publish_tf": True,
                "base_frame_id": base_frame,
                "odom_frame_id": odom_frame,
                "init_pose_from_topic": "",
                "freq": ParameterValue(
                    rf2o_frequency,
                    value_type=float,
                ),
            }
        ],
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
                description="실물 센서는 시스템 시간을 사용하므로 기본값은 false",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan",
                description="YDLIDAR와 RF2O, SLAM이 공유할 LaserScan 토픽",
            ),
            DeclareLaunchArgument(
                "odom_topic",
                default_value="/odom_rf2o",
                description="RF2O가 발행할 Odometry 토픽",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="RF2O가 추정하는 이동 기준 프레임",
            ),
            DeclareLaunchArgument(
                "odom_frame",
                default_value="odom",
                description="RF2O가 발행할 odometry 부모 프레임",
            ),
            DeclareLaunchArgument(
                "laser_frame",
                default_value="laser_frame",
                description="YDLIDAR LaserScan과 정적 TF의 센서 프레임",
            ),
            DeclareLaunchArgument(
                "laser_x", default_value="0.0",
                description="base_link 기준 LiDAR 전방 위치(m)",
            ),
            DeclareLaunchArgument(
                "laser_y", default_value="0.0",
                description="base_link 기준 LiDAR 좌측 위치(m)",
            ),
            DeclareLaunchArgument(
                "laser_z", default_value="0.0",
                description="base_link 기준 LiDAR 높이(m)",
            ),
            DeclareLaunchArgument(
                "laser_roll", default_value="0.0",
                description="base_link 기준 LiDAR roll(rad)",
            ),
            DeclareLaunchArgument(
                "laser_pitch", default_value="0.0",
                description="base_link 기준 LiDAR pitch(rad)",
            ),
            DeclareLaunchArgument(
                "laser_yaw", default_value="0.0",
                description="base_link 기준 LiDAR yaw(rad)",
            ),
            DeclareLaunchArgument(
                "rf2o_frequency",
                default_value="20.0",
                description="RF2O 처리 주기(Hz), 공식 Humble launch 기본값",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ttyUSB0",
                description="YDLIDAR가 연결된 시리얼 장치 경로",
            ),
            DeclareLaunchArgument(
                "include_lidar",
                default_value="true",
                description="YDLIDAR 드라이버와 기존 정적 TF를 함께 실행",
            ),
            DeclareLaunchArgument(
                "use_rviz",
                default_value="true",
                description="기존 mapping RViz 설정을 함께 실행",
            ),
            lidar,
            rf2o,
            slam_toolbox,
            rviz,
        ]
    )
