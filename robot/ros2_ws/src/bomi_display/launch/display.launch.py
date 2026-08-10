"""BOMI LCD 표정 노드를 실행한다."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """전체 화면 LCD 노드 하나를 구성한다."""
    return LaunchDescription(
        [
            Node(
                package="bomi_display",
                executable="face_display",
                name="bomi_face_display",
                output="screen",
            )
        ]
    )
