import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('core')

    joystick_launch_file = os.path.join(
        package_share,
        'launch',
        'joystick_teleop.launch.py',
    )

    twist_mux_config_file = os.path.join(
        package_share,
        'config',
        'twist_mux.yaml',
    )

    # 기존 cmd_vel_topic과 이름이 겹치지 않도록 별도 이름 사용
    final_cmd_vel_topic = LaunchConfiguration('final_cmd_vel_topic')

    return LaunchDescription([
        DeclareLaunchArgument(
            'final_cmd_vel_topic',
            default_value='/cmd_vel',
            description='twist_mux가 최종 속도 명령을 보낼 토픽',
        ),

        # 조이스틱 명령은 /cmd_vel_joy로 전송
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(joystick_launch_file),
            launch_arguments={
                'cmd_vel_topic': '/cmd_vel_joy_raw',
            }.items(),
        ),

        Node(
            package='core',
            executable='joy_cmd_filter',
            name='joy_cmd_filter',
            output='screen',
        ),

        # 키보드와 조이스틱 명령의 우선순위 처리
        Node(
            package='twist_mux',
            executable='twist_mux',
            name='twist_mux',
            parameters=[twist_mux_config_file],
            remappings=[
                ('/cmd_vel_out', final_cmd_vel_topic),
            ],
            output='screen',
        ),
    ])