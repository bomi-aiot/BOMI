# 거북이 조이스틱 주행후 추가된 파일
# joy_node와 teleop_twist_joy를 같이 켜는 코드
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('core')

    config_file = os.path.join(
        package_share,
        'config',
        'xbox360_sim.yaml',
    )

    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')

    return LaunchDescription([
        DeclareLaunchArgument(
            'cmd_vel_topic',
            default_value='/cmd_vel',
            description='조이스틱 속도 명령을 보낼 토픽',
        ),

        Node(
            package='joy_linux',
            executable='joy_linux_node',
            name='joy_node',
            parameters=[config_file],
            output='screen',
        ),

        Node(
            package='teleop_twist_joy',
            executable='teleop_node',
            name='teleop_node',
            parameters=[config_file],
            remappings=[
                ('cmd_vel', cmd_vel_topic),
            ],
            output='screen',
        ),
    ])
