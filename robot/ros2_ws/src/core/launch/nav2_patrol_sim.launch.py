"""TurtleBot3 Nav2 시뮬레이션과 waypoint 순찰을 한 번에 실행한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    """Gazebo 준비 후 로봇, Nav2, 초기 위치, 순찰을 순서대로 실행한다."""
    nav2_share = get_package_share_directory("nav2_bringup")
    core_share = get_package_share_directory("core")

    turtlebot3_gazebo_share = get_package_share_directory(
        "turtlebot3_gazebo"
    )

    gazebo_model_path = os.pathsep.join([
        path
        for path in [
            os.environ.get("GAZEBO_MODEL_PATH", ""),
            os.path.join(nav2_share, "worlds"),
            os.path.join(turtlebot3_gazebo_share, "models"),
        ]
        if path
    ])

    default_map = os.path.join(
        nav2_share,
        "maps",
        "turtlebot3_world.yaml",
    )

    default_world = os.path.join(
        nav2_share,
        "worlds",
        "world_only.model",
    )

    default_waypoint_file = os.path.join(
        core_share,
        "config",
        "room_waypoints.yaml",
    )

    default_params_file = os.path.join(
        core_share,
        "config",
        "nav2_safe_params.yaml",
    )

    robot_sdf = os.path.join(
        nav2_share,
        "worlds",
        "waffle.model",
    )
    robot_urdf = os.path.join(
        nav2_share,
        "urdf",
        "turtlebot3_waffle.urdf",
    )
    with open(robot_urdf, "r", encoding="utf-8") as urdf_file:
        robot_description = urdf_file.read()

    safe_bt_xml = os.path.join(
        core_share,
        "behavior_trees",
        "nav_to_pose_safe.xml",
    )

    map_file = LaunchConfiguration("map")
    world_file = LaunchConfiguration("world")
    waypoint_file = LaunchConfiguration("waypoint_file")
    params_file = LaunchConfiguration("params_file")
    configured_params = RewrittenYaml(
        source_file=params_file,
        param_rewrites={
            "default_nav_to_pose_bt_xml": safe_bt_xml,
        },
        convert_types=True,
    )
    use_sim_time = LaunchConfiguration("use_sim_time")
    headless = LaunchConfiguration("headless")
    use_rviz = LaunchConfiguration("use_rviz")
    robot_model = LaunchConfiguration("robot_model")
    force_software_rendering = LaunchConfiguration(
        "force_software_rendering"
    )

    # 1. Gazebo 서버만 먼저 실행한다.
    gazebo_server = ExecuteProcess(
        cmd=[
            "gzserver",
            "-s",
            "libgazebo_ros_init.so",
            "-s",
            "libgazebo_ros_factory.so",
            world_file,
        ],
        output="screen",
    )

    gazebo_client = ExecuteProcess(
        condition=UnlessCondition(headless),
        cmd=["gzclient"],
        output="screen",
    )

    # 2. /spawn_entity 서비스가 실제로 생길 때까지 자동 대기한다.
    wait_for_spawn_service = ExecuteProcess(
        cmd=[
            "bash",
            "-c",
            (
                "echo '[core] Gazebo spawn 서비스 대기 중...'; "
                "until ros2 service type /spawn_entity "
                "> /dev/null 2>&1; do sleep 1; done; "
                "echo '[core] Gazebo spawn 서비스 준비 완료'"
            ),
        ],
        output="screen",
    )

    # 3. 로봇을 먼저 생성해 odom과 TF가 준비될 수 있게 한다.
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "robot_description": robot_description,
            }
        ],
        remappings=[
            ("/tf", "tf"),
            ("/tf_static", "tf_static"),
        ],
    )

    spawn_robot = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        output="screen",
        arguments=[
            "-entity",
            "turtlebot3_waffle",
            "-file",
            robot_sdf,
            "-x",
            "-2.0",
            "-y",
            "-0.5",
            "-z",
            "0.01",
        ],
    )

    # 4. 로봇 생성이 완료된 뒤 Nav2를 시작한다.
    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                nav2_share,
                "launch",
                "bringup_launch.py",
            )
        ),
        launch_arguments={
            "namespace": "",
            "use_namespace": "False",
            "slam": "False",
            "map": map_file,
            "params_file": configured_params,
            "use_sim_time": use_sim_time,
            "use_composition": "False",
            "autostart": "True",
            "use_respawn": "False",
        }.items(),
    )

    rviz_node = Node(
        condition=IfCondition(use_rviz),
        package="rviz2",
        executable="rviz2",
        name="rviz",
        output="screen",
        arguments=[
            "-d",
            os.path.join(
                nav2_share,
                "rviz",
                "nav2_default_view.rviz",
            ),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    initial_pose_message = (
        "{header: {stamp: now, frame_id: 'map'}, "
        "pose: {pose: {position: "
        "{x: -2.0, y: -0.5, z: 0.0}, orientation: "
        "{x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, covariance: ["
        "0.25, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.25, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0685"
        "]}}"
    )

    # 5. AMCL에 초기 위치를 자동 전달한다.
    initial_pose_publisher = ExecuteProcess(
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

    # 6. 순찰 노드는 내부에서 bt_navigator 활성 상태를 확인한다.
    patrol_node = Node(
        package="core",
        executable="nav2_waypoint_patrol",
        name="nav2_waypoint_patrol",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "waypoint_file": waypoint_file,
                "frame_id": "map",
                "action_name": "navigate_to_pose",
            }
        ],
    )

    # 초기 위치 발행이 끝난 뒤 순찰 노드의 활성 상태 확인 시작
    start_patrol_after_initial_pose = RegisterEventHandler(
        OnProcessExit(
            target_action=initial_pose_publisher,
            on_exit=[
                TimerAction(
                    period=3.0,
                    actions=[patrol_node],
                )
            ],
        )
    )

    # 로봇 생성이 성공적으로 끝난 뒤 Nav2와 초기 위치 발행 시작
    start_nav2_after_robot_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_robot,
            on_exit=[
                nav2_bringup,
                rviz_node,
                TimerAction(
                    period=3.0,
                    actions=[initial_pose_publisher],
                ),
            ],
        )
    )

    # Gazebo 서비스가 준비된 뒤 로봇부터 생성
    start_robot_after_gazebo_ready = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_spawn_service,
            on_exit=[
                robot_state_publisher,
                spawn_robot,
            ],
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "map",
            default_value=default_map,
            description="Nav2에서 사용할 map.yaml 경로",
        ),
        DeclareLaunchArgument(
            "world",
            default_value=default_world,
            description="Gazebo에서 사용할 world 파일",
        ),
        DeclareLaunchArgument(
            "waypoint_file",
            default_value=default_waypoint_file,
            description="순찰 waypoint YAML 경로",
        ),
        DeclareLaunchArgument(
            "params_file",
            default_value=default_params_file,
            description="Nav2에서 사용할 파라미터 YAML 경로",
        ),
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="True",
        ),
        DeclareLaunchArgument(
            "headless",
            default_value="True",
        ),
        DeclareLaunchArgument(
            "use_rviz",
            default_value="False",
        ),
        DeclareLaunchArgument(
            "robot_model",
            default_value="waffle",
        ),
        DeclareLaunchArgument(
            "force_software_rendering",
            default_value="False",
            description=(
                "Gazebo와 RViz에 llvmpipe 소프트웨어 렌더링을 강제"
            ),
        ),

        SetEnvironmentVariable(
            name="TURTLEBOT3_MODEL",
            value=robot_model,
        ),

        SetEnvironmentVariable(
            name="GAZEBO_MODEL_PATH",
            value=gazebo_model_path,
        ),

        # 그래픽 드라이버 문제가 있을 때만 소프트웨어 렌더링을 사용한다.
        SetEnvironmentVariable(
            condition=IfCondition(force_software_rendering),
            name="LIBGL_ALWAYS_SOFTWARE",
            value="1",
        ),
        SetEnvironmentVariable(
            condition=IfCondition(force_software_rendering),
            name="GALLIUM_DRIVER",
            value="llvmpipe",
        ),
        SetEnvironmentVariable(
            condition=IfCondition(force_software_rendering),
            name="QT_XCB_GL_INTEGRATION",
            value="none",
        ),

        gazebo_server,
        gazebo_client,

        start_robot_after_gazebo_ready,
        start_nav2_after_robot_spawn,
        start_patrol_after_initial_pose,

        wait_for_spawn_service,
    ])
