from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    """조이스틱으로 시뮬레이션 로봇을 조종하며 SLAM 지도를 생성한다."""

    core_share = Path(get_package_share_directory("core"))
    mapping_share = Path(get_package_share_directory("mapping"))

    mapping_launch_file = (
        mapping_share
        / "launch"
        / "mapping_sim.launch.py"
    )

    manual_control_launch_file = (
        core_share
        / "launch"
        / "manual_control.launch.py"
    )

    final_cmd_vel_topic = LaunchConfiguration(
        "final_cmd_vel_topic"
    )

    mapping = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(mapping_launch_file)
        )
    )

    manual_control = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(manual_control_launch_file)
        ),
        launch_arguments={
            "final_cmd_vel_topic": final_cmd_vel_topic,
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "final_cmd_vel_topic",
                default_value="/cmd_vel",
                description=(
                    "조이스틱 명령을 전달할 최종 속도 토픽"
                ),
            ),
            mapping,
            manual_control,
        ]
    )
