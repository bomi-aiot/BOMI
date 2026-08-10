"""실제 조이스틱, Pico, X4-PRO와 SLAM Toolbox를 함께 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, NotSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """실제 로봇의 수동 주행과 온라인 지도 생성을 구성한다.

    Pico가 /odom과 /imu를 발행하고, EKF가 둘을 융합해 odom → base_link TF를
    발행한다. 이때 Pico의 TF 발행은 끈다. LiDAR 스캔만 쓰는 RF2O는 실행하지
    않는다.
    """

    mapping_share = Path(get_package_share_directory("mapping"))
    core_share = Path(get_package_share_directory("core"))
    lidar_share = Path(get_package_share_directory("bomi_lidar"))

    joystick_launch = core_share / "launch" / "joystick_teleop.launch.py"
    pico_launch = core_share / "launch" / "pico_driver.launch.py"
    lidar_launch = lidar_share / "launch" / "x4_pro.launch.py"

    slam_params = mapping_share / "config" / "slam_toolbox_real.yaml"
    ekf_params = core_share / "config" / "ekf.yaml"
    rviz_config = mapping_share / "rviz" / "mapping.rviz"

    use_sim_time = LaunchConfiguration("use_sim_time")
    use_rviz = LaunchConfiguration("use_rviz")
    use_ekf = LaunchConfiguration("use_ekf")
    use_scan_matching = LaunchConfiguration("use_scan_matching")
    do_loop_closing = LaunchConfiguration("do_loop_closing")

    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")
    pico_port = LaunchConfiguration("pico_port")
    lidar_port = LaunchConfiguration("lidar_port")

    scan_topic = LaunchConfiguration("scan_topic")
    raw_scan_topic = LaunchConfiguration("raw_scan_topic")
    scan_span_tolerance_deg = LaunchConfiguration("scan_span_tolerance_deg")
    scan_minimum_interval_sec = LaunchConfiguration(
        "scan_minimum_interval_sec"
    )
    base_frame = LaunchConfiguration("base_frame")
    odom_frame = LaunchConfiguration("odom_frame")
    laser_frame = LaunchConfiguration("laser_frame")
    laser_x = LaunchConfiguration("laser_x")
    laser_y = LaunchConfiguration("laser_y")
    laser_z = LaunchConfiguration("laser_z")
    laser_roll = LaunchConfiguration("laser_roll")
    laser_pitch = LaunchConfiguration("laser_pitch")
    laser_yaw = LaunchConfiguration("laser_yaw")

    joystick = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(joystick_launch)),
        launch_arguments={
            "cmd_vel_topic": cmd_vel_topic,
        }.items(),
    )

    # EKF가 odom → base_link TF를 발행하므로 Pico의 TF 발행을 끈다.
    # 두 노드가 같은 변환을 발행하면 TF가 충돌한다.
    pico_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(pico_launch)),
        launch_arguments={
            "serial_port": pico_port,
            "publish_tf": NotSubstitution(use_ekf),
        }.items(),
    )

    # 엔코더의 직진 속도와 자이로의 회전 속도만 융합한다.
    # 스키드 스티어는 회전에서 바퀴가 미끄러져 엔코더 회전각을 믿을 수 없다.
    ekf = Node(
        package="robot_localization",
        executable="ekf_node",
        name="ekf_filter_node",
        condition=IfCondition(use_ekf),
        output="screen",
        parameters=[
            str(ekf_params),
            {
                "use_sim_time": ParameterValue(
                    use_sim_time,
                    value_type=bool,
                ),
                "odom_frame": odom_frame,
                "base_link_frame": base_frame,
            },
        ],
    )

    # LiDAR는 원시 토픽으로 내고, 위생 노드가 성한 스캔만 scan_topic으로
    # 넘긴다. 모터가 돌면 드라이버가 한 바퀴 경계를 놓쳐 각도 범위가 402°인
    # 스캔을 섞어 보내므로 그대로 SLAM에 주면 회전마다 지도가 어긋난다.
    # 근거와 실측값은 core/core/scan_sanitizer.py에 적혀 있다.
    # GroupAction으로 감싸 launch 인자가 부모 스코프로 새지 않게 한다.
    # 감싸지 않으면 여기 넘긴 scan_topic(=/scan_raw)이 부모의
    # scan_topic까지 덮어써서, 위생 노드의 출력과 slam_toolbox의 입력이
    # 모두 원시 토픽을 가리킨다.
    lidar = GroupAction(
        [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(lidar_launch)),
                launch_arguments={
                    "port": lidar_port,
                    "scan_topic": raw_scan_topic,
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
        ]
    )

    scan_sanitizer = Node(
        package="core",
        executable="scan_sanitizer",
        name="scan_sanitizer",
        output="screen",
        parameters=[
            {
                "use_sim_time": ParameterValue(
                    use_sim_time,
                    value_type=bool,
                ),
                "input_topic": raw_scan_topic,
                "output_topic": scan_topic,
                "span_tolerance_deg": ParameterValue(
                    scan_span_tolerance_deg,
                    value_type=float,
                ),
                "minimum_interval_sec": ParameterValue(
                    scan_minimum_interval_sec,
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
                # 지도가 90°씩 돌아가 겹칠 때 원인을 나누기 위해 launch에서
                # 켜고 끈다. 값의 뜻과 기본값 근거는 설정 파일에 적혀 있다.
                "use_scan_matching": ParameterValue(
                    use_scan_matching,
                    value_type=bool,
                ),
                "do_loop_closing": ParameterValue(
                    do_loop_closing,
                    value_type=bool,
                ),
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
                "use_ekf",
                default_value="true",
                description=(
                    "엔코더와 자이로를 EKF로 융합할지 여부. "
                    "false면 이전처럼 Pico가 odom → base_link TF를 발행한다."
                ),
            ),
            DeclareLaunchArgument(
                "use_scan_matching",
                default_value="true",
                description=(
                    "SLAM이 스캔 매칭으로 odometry를 보정할지 여부. "
                    "false면 지도는 odometry만 따라간다."
                ),
            ),
            DeclareLaunchArgument(
                "do_loop_closing",
                default_value="false",
                description=(
                    "루프 클로저 사용 여부. 정사각형 공간에서는 90° 돌아간 "
                    "후보가 잘못 채택되므로 기본값은 끔이다."
                ),
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
                "raw_scan_topic",
                default_value="/scan_raw",
                description=(
                    "LiDAR 드라이버가 내는 원시 LaserScan 토픽. "
                    "위생 노드가 이걸 받아 scan_topic으로 다시 낸다."
                ),
            ),
            DeclareLaunchArgument(
                "scan_span_tolerance_deg",
                default_value="5.0",
                description=(
                    "스캔의 각도 범위가 360°에서 이만큼 벗어나면 버린다. "
                    "360으로 주면 모두 통과시켜 위생 노드를 사실상 끈다."
                ),
            ),
            DeclareLaunchArgument(
                "scan_minimum_interval_sec",
                default_value="0.07",
                description=(
                    "직전 통과 스캔과 이 간격보다 붙어 오면 버린다. "
                    "0으로 주면 간격 기준을 끈다."
                ),
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
            joystick,
            pico_driver,
            lidar,
            scan_sanitizer,
            ekf,
            slam_toolbox,
            rviz,
        ]
    )
