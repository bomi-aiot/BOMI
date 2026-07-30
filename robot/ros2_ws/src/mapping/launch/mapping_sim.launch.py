from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    simulation_share = Path(
        get_package_share_directory("simulation")
    )

    mapping_share = Path(
        get_package_share_directory("mapping")
    )

    simulation_launch = (
        simulation_share
        / "launch"
        / "bomi_sim.launch.py"
    )

    slam_params = (
        mapping_share
        / "config"
        / "slam_toolbox.yaml"
    )

    rviz_config = (
        mapping_share
        / "rviz"
        / "mapping.rviz"
    )

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(simulation_launch)
        )
    )

    slam_toolbox = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        output="screen",
        parameters=[
            str(slam_params),
            {"use_sim_time": True},
        ],
    )

    delayed_slam = TimerAction(
        period=5.0,
        actions=[slam_toolbox],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=[
            "-d",
            str(rviz_config),
        ],
        parameters=[
            {"use_sim_time": True},
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            simulation,
            delayed_slam,
            rviz,
        ]
    )
