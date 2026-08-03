"""BOMI Gazebo 시뮬레이션과 ROS 2 토픽 브리지를 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """WSLg에서 안정적으로 동작하는 BOMI Gazebo 실행 구성을 반환한다."""
    simulation_share = Path(
        get_package_share_directory("simulation")
    )

    description_share = Path(
        get_package_share_directory("description")
    )

    world_path = (
        simulation_share
        / "worlds"
        / "bomi_test_world.sdf"
    )

    robot_path = (
        description_share
        / "models"
        / "bomi_robot"
        / "model.sdf"
    )

    headless = LaunchConfiguration("headless")

    gazebo_with_gui = ExecuteProcess(
        condition=UnlessCondition(headless),
        cmd=[
            "ign",
            "gazebo",
            "-r",
            "-v",
            "4",
            "--render-engine",
            "ogre2",
            str(world_path),
        ],
        additional_env={
            "GALLIUM_DRIVER": "llvmpipe",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "LP_NUM_THREADS": "2",
        },
        output="screen",
    )

    gazebo_server = ExecuteProcess(
        condition=IfCondition(headless),
        cmd=[
            "ign",
            "gazebo",
            "-s",
            "-r",
            "-v",
            "4",
            "--render-engine",
            "ogre2",
            str(world_path),
        ],
        additional_env={
            "GALLIUM_DRIVER": "llvmpipe",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "LP_NUM_THREADS": "2",
        },
        output="screen",
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-file",
            str(robot_path),
            "-name",
            "bomi_robot",
            "-x",
            "0",
            "-y",
            "0",
            "-z",
            "0.01",
        ],
        output="screen",
    )

    delayed_spawn = TimerAction(
        period=3.0,
        actions=[spawn_robot],
    )

    cmd_vel_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="cmd_vel_bridge",
        arguments=[
            "/cmd_vel@geometry_msgs/msg/Twist]ignition.msgs.Twist",
        ],
        output="screen",
    )

    sensor_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="sensor_bridge",
        arguments=[
            "/scan@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan",
            "/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry",
            "/model/bomi_robot/tf@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V",
            "/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock",
        ],
        remappings=[
            ("/model/bomi_robot/tf", "/tf"),
        ],
        output="screen",
    )

    lidar_static_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=[
            "0.12", "0.0", "0.12",
            "0.0", "0.0", "0.0",
            "base_link", "lidar_link",
        ],
        output="screen",
    )

    lidar_sensor_static_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=[
            "0.0", "0.0", "0.03",
            "0.0", "0.0", "0.0",
            "lidar_link",
            "bomi_robot/lidar_link/lidar",
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "headless",
                default_value="False",
                description="Gazebo GUI 없이 서버와 센서만 실행할지 여부",
            ),
            gazebo_with_gui,
            gazebo_server,
            delayed_spawn,
            cmd_vel_bridge,
            sensor_bridge,
            lidar_static_tf,
            lidar_sensor_static_tf,
        ]
    )
