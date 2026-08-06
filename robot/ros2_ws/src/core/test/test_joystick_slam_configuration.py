"""실물 조이스틱 SLAM 통합 launch의 핵심 연결을 검증한다."""

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROBOT_LAUNCH = PACKAGE_ROOT / "launch" / "joystick_slam_robot.launch.py"


def test_joystick_slam_launch_has_valid_python_syntax():
    """통합 launch 파일이 Python 문법에 맞는지 검증한다."""
    ast.parse(ROBOT_LAUNCH.read_text(encoding="utf-8"))


def test_joystick_slam_launch_forwards_measured_lidar_transform():
    """실측 LiDAR 위치와 자세를 LiDAR launch에 전달하는지 검증한다."""
    launch_source = ROBOT_LAUNCH.read_text(encoding="utf-8")

    for argument in (
        "laser_x",
        "laser_y",
        "laser_z",
        "laser_roll",
        "laser_pitch",
        "laser_yaw",
    ):
        assert f'"{argument}": {argument}' in launch_source
