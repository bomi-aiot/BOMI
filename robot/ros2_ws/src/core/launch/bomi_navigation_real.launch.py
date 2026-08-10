"""실물 로봇에서 저장된 지도로 Nav2 자율주행을 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, NotSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from nav2_common.launch import RewrittenYaml


def generate_launch_description() -> LaunchDescription:
    """실물 센서·AMCL·Nav2를 연결해 저장된 지도 위에서 자율주행하게 한다.

    Pico가 /odom과 /imu를 발행하고, use_ekf가 true면 EKF가 이를 융합해
    odom → base_link TF를 발행한다(mapping 때와 동일하게 Pico의 TF 발행은
    끈다). AMCL이 map → odom TF를 발행해 map 프레임 기준 위치를 잡고,
    그 위에서 controller_server/planner_server/bt_navigator가 목표
    지점까지 주행한다.

    속도·가속도 파라미터(nav2_safe_params_real.yaml)는 실측 튜닝 전
    초안이다.
    """

    core_share = Path(get_package_share_directory("core"))
    lidar_share = Path(get_package_share_directory("bomi_lidar"))
    nav2_share = Path(get_package_share_directory("nav2_bringup"))

    joystick_launch = core_share / "launch" / "joystick_teleop.launch.py"
    pico_launch = core_share / "launch" / "pico_driver.launch.py"
    lidar_launch = lidar_share / "launch" / "x4_pro.launch.py"

    ekf_params = core_share / "config" / "ekf.yaml"
    default_params = core_share / "config" / "nav2_safe_params_real.yaml"
    safe_bt_xml = core_share / "behavior_trees" / "nav_to_pose_safe.xml"
    rviz_config = core_share / "rviz" / "bomi_navigation.rviz"

    use_sim_time = LaunchConfiguration("use_sim_time")
    use_rviz = LaunchConfiguration("use_rviz")
    use_ekf = LaunchConfiguration("use_ekf")
    use_joystick = LaunchConfiguration("use_joystick")

    map_file = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")
    pico_port = LaunchConfiguration("pico_port")
    lidar_port = LaunchConfiguration("lidar_port")
    scan_topic = LaunchConfiguration("scan_topic")
    raw_scan_topic = LaunchConfiguration("raw_scan_topic")
    scan_span_tolerance_deg = LaunchConfiguration(
        "scan_span_tolerance_deg"
    )
    scan_minimum_interval_sec = LaunchConfiguration(
        "scan_minimum_interval_sec"
    )
    base_frame = LaunchConfiguration("base_frame")
    laser_x = LaunchConfiguration("laser_x")
    laser_y = LaunchConfiguration("laser_y")
    laser_z = LaunchConfiguration("laser_z")
    odom_frame = LaunchConfiguration("odom_frame")
    robot_radius = LaunchConfiguration("robot_radius")

    configured_params = RewrittenYaml(
        source_file=params_file,
        param_rewrites={
            "base_frame_id": base_frame,
            "default_nav_to_pose_bt_xml": str(safe_bt_xml),
            "robot_radius": robot_radius,
        },
        convert_types=True,
    )

    joystick = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(joystick_launch)),
        condition=IfCondition(use_joystick),
        launch_arguments={
            "cmd_vel_topic": cmd_vel_topic,
        }.items(),
    )

    # AMCL이 map → odom TF를 발행하므로, mapping 때처럼 Pico의 TF 발행은
    # EKF 사용 여부에 따라 결정한다(EKF on이면 EKF가 odom → base_link를
    # 발행하고, off이면 Pico가 직접 발행한다). 어느 쪽이든 AMCL이 그 위에
    # map → odom을 얹는다.
    pico_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(pico_launch)),
        launch_arguments={
            "serial_port": pico_port,
            "publish_tf": NotSubstitution(use_ekf),
        }.items(),
    )

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

    # LiDAR는 원시 토픽으로 내고 위생 노드가 성한 스캔만 넘긴다. 모터가
    # 돌면 드라이버가 한 바퀴 경계를 놓쳐 각도 범위가 402°인 스캔을 섞어
    # 보내는데, 그대로 두면 AMCL과 코스트맵에 유령 장애물이 박힌다.
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
                    "laser_x": laser_x,
                    "laser_y": laser_y,
                    "laser_z": laser_z,
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

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(nav2_share / "launch" / "localization_launch.py")
        ),
        launch_arguments={
            "namespace": "",
            "map": map_file,
            "params_file": configured_params,
            "use_sim_time": use_sim_time,
            "use_composition": "False",
            "autostart": "True",
            "use_respawn": "False",
        }.items(),
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(nav2_share / "launch" / "navigation_launch.py")
        ),
        launch_arguments={
            "namespace": "",
            "params_file": configured_params,
            "use_sim_time": use_sim_time,
            "use_composition": "False",
            "autostart": "True",
            "use_respawn": "False",
        }.items(),
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

    # 센서·odom 노드가 먼저 자리를 잡을 시간을 준 뒤 AMCL·Nav2를 올린다.
    # 초기 위치는 여기서 자동으로 넣지 않는다 — 로봇을 지도 위 어디에
    # 세워뒀는지는 RViz "2D Pose Estimate"로 사람이 알려줘야 한다.
    start_navigation = TimerAction(
        period=3.0,
        actions=[
            localization,
            navigation,
            rviz,
        ],
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
                    "false면 Pico가 odom → base_link TF를 직접 발행한다."
                ),
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
                    "360으로 주면 모두 통과시켜 위생 노드를 끈다."
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
                "use_joystick",
                default_value="false",
                description=(
                    "조이스틱 수동 개입을 함께 켤지 여부. "
                    "자율주행만 확인할 때는 false로 둔다."
                ),
            ),
            DeclareLaunchArgument(
                "map",
                description=(
                    "Nav2가 쓸 map.yaml 경로. mapping_real.launch.py로 "
                    "만든 지도를 지정한다(필수, 기본값 없음)."
                ),
            ),
            DeclareLaunchArgument(
                "params_file",
                default_value=str(default_params),
                description="Nav2 파라미터 YAML 경로",
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
                description="YDLIDAR와 AMCL/costmap이 공유할 LaserScan 토픽",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="로봇 기준 프레임",
            ),
            DeclareLaunchArgument(
                "odom_frame",
                default_value="odom",
                description="odom 부모 프레임",
            ),
            # LiDAR가 회전 중심에서 벗어나 있으면, 제자리 회전에서 스캔
            # 원점이 원을 그린다. 이 값을 0으로 두면 그 이동분이 통째로
            # 오차가 되어 AMCL이 회전마다 위치를 놓친다. 매핑 쪽과 같은
            # 실측값을 기본값으로 둔다(joystick_slam_robot.launch.py는
            # 아직 0이 기본이므로 그쪽은 스크립트가 넘긴다).
            #
            # ★ 이 세 값은 robot/scripts/bomi_map.sh 의 LASER_X/Y/Z 와 **항상
            #   같아야 한다.** 지도는 LiDAR 높이에서 잘라낸 단면이라, 그릴 때와
            #   다른 높이로 주행하면 스캔이 지도와 매칭되지 않는다. 그 실패는
            #   에러가 아니라 "AMCL이 조용히 위치를 놓침"으로 나타나므로 찾기
            #   어렵다. 한쪽을 고치면 반드시 다른 쪽도 고치고, 재매핑한다.
            #
            # 2026-08-10: 마운트를 높여 z가 0.240 -> 0.466 이 되었다. x, y는
            # 아직 2026-08-07 실측값이라 재측정이 필요하다(bomi_map.sh 참고).
            DeclareLaunchArgument(
                "laser_x",
                default_value="0.135",
                description="base_link 기준 LiDAR 전방 위치(m). 실측값",
            ),
            DeclareLaunchArgument(
                "laser_y",
                default_value="0.0",
                description="base_link 기준 LiDAR 좌측 위치(m). 실측값",
            ),
            DeclareLaunchArgument(
                "laser_z",
                default_value="0.466",
                description="base_link 기준 LiDAR 높이(m). 실측값",
            ),
            DeclareLaunchArgument(
                "robot_radius",
                default_value="0.20",
                description=(
                    "costmap이 쓰는 로봇 반경(m). 2026-08-07 줄자 실측 "
                    "28.5 x 15.5cm 의 외접 반경 16.2cm 에 여유를 둔 값. "
                    "이전 0.30 은 실물이 아니라 시뮬 모델(0.45 x 0.32)에서 "
                    "나온 값이었다. RewrittenYaml이 params 파일 값을 이 인자로 "
                    "덮어쓰므로, YAML만 고치면 반영되지 않는다."
                ),
            ),
            joystick,
            pico_driver,
            ekf,
            lidar,
            scan_sanitizer,
            start_navigation,
        ]
    )
