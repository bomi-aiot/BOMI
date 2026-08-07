"""BOMI Gazebo와 저장 지도 기반 Nav2 내비게이션을 함께 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description() -> LaunchDescription:
    """BOMI 시뮬레이터, AMCL, Nav2와 RViz 실행 구성을 반환한다."""
    core_share = Path(get_package_share_directory("core"))
    mapping_share = Path(get_package_share_directory("mapping"))
    nav2_share = Path(get_package_share_directory("nav2_bringup"))
    simulation_share = Path(get_package_share_directory("simulation"))

    simulation_launch = (
        simulation_share / "launch" / "bomi_sim.launch.py"
    )
    default_map = mapping_share / "maps" / "bomi_test_map.yaml"
    default_params = core_share / "config" / "nav2_safe_params.yaml"
    safe_bt_xml = (
        core_share / "behavior_trees" / "nav_to_pose_safe.xml"
    )
    rviz_config = core_share / "rviz" / "bomi_navigation.rviz"

    map_file = LaunchConfiguration("map")
    headless = LaunchConfiguration("headless")
    params_file = LaunchConfiguration("params_file")
    use_rviz = LaunchConfiguration("use_rviz")
    use_sim_time = LaunchConfiguration("use_sim_time")

    configured_params = RewrittenYaml(
        source_file=params_file,
        param_rewrites={
            "base_frame_id": "base_link",
            "default_nav_to_pose_bt_xml": str(safe_bt_xml),
            "robot_radius": "0.31",
        },
        convert_types=True,
    )

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(simulation_launch)),
        launch_arguments={
            "headless": headless,
        }.items(),
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
        condition=IfCondition(use_rviz),
        package="rviz2",
        executable="rviz2",
        name="rviz",
        output="screen",
        arguments=[
            "-d",
            str(rviz_config),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
        additional_env={
            "GALLIUM_DRIVER": "llvmpipe",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "LP_NUM_THREADS": "2",
            "QT_XCB_GL_INTEGRATION": "none",
        },
    )

    initial_pose_message = (
        "{header: {stamp: now, frame_id: 'map'}, "
        "pose: {pose: {position: "
        "{x: 0.0, y: 0.0, z: 0.0}, orientation: "
        "{x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, covariance: ["
        "0.25, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.25, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0685"
        "]}}"
    )
    initial_pose = ExecuteProcess(
        cmd=[
            "ros2",
            "topic",
            "pub",
            "--rate",
            "1",
            "--times",
            "5",
            "--use-sim-time",
            "/initialpose",
            "geometry_msgs/msg/PoseWithCovarianceStamped",
            initial_pose_message,
        ],
        output="screen",
    )

    start_navigation_after_initial_pose = RegisterEventHandler(
        OnProcessExit(
            target_action=initial_pose,
            on_exit=[navigation],
        )
    )

    start_localization = TimerAction(
        period=5.0,
        actions=[
            localization,
            rviz,
            TimerAction(period=3.0, actions=[initial_pose]),
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "map",
                default_value=str(default_map),
                description="Nav2에서 사용할 BOMI map.yaml 경로",
            ),
            DeclareLaunchArgument(
                "headless",
                default_value="True",
                description="Gazebo GUI 없이 시뮬레이션할지 여부",
            ),
            DeclareLaunchArgument(
                "params_file",
                default_value=str(default_params),
                description="Nav2에서 사용할 파라미터 YAML 경로",
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="True",
                description="Gazebo 시뮬레이션 시간 사용 여부",
            ),
            DeclareLaunchArgument(
                "use_rviz",
                default_value="True",
                description="Nav2 RViz 화면 실행 여부",
            ),
            start_navigation_after_initial_pose,
            simulation,
            start_localization,
        ]
    )
