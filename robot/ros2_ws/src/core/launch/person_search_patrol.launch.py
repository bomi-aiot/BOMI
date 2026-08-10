"""웨이포인트 사용자 탐색과 비활성 상태의 사람 추종 노드를 실행한다."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Nav2와 함께 사용할 사용자 탐색·추종 노드를 구성한다."""
    core_share = Path(get_package_share_directory("core"))
    search_params = core_share / "config" / "person_search_patrol.yaml"
    follow_params = core_share / "config" / "person_following.yaml"

    waypoint_file = LaunchConfiguration("waypoint_file")
    scan_topic = LaunchConfiguration("scan_topic")
    output_topic = LaunchConfiguration("output_topic")
    start_automatically = LaunchConfiguration("start_automatically")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "waypoint_file",
                default_value=str(core_share / "config" / "room_waypoints.yaml"),
                description="사용자 탐색에 사용할 웨이포인트 YAML 경로",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan_real",
                description="사람 추종 안전거리에 사용할 LaserScan 토픽",
            ),
            DeclareLaunchArgument(
                "output_topic",
                default_value="/cmd_vel",
                description="Nav2 취소 후 사람 추종 속도를 발행할 토픽",
            ),
            DeclareLaunchArgument(
                "start_automatically",
                default_value="true",
                description="launch 시작과 함께 한 바퀴 탐색을 시작할지 여부",
            ),
            Node(
                package="core",
                executable="person_follower",
                name="person_follower",
                output="screen",
                parameters=[
                    str(follow_params),
                    {
                        "start_enabled": False,
                        "scan_topic": scan_topic,
                        "output_topic": output_topic,
                    },
                ],
            ),
            Node(
                package="core",
                executable="person_search_patrol",
                name="person_search_patrol",
                output="screen",
                parameters=[
                    str(search_params),
                    {
                        "waypoint_file": waypoint_file,
                        "start_automatically": start_automatically,
                    },
                ],
            ),
        ]
    )
