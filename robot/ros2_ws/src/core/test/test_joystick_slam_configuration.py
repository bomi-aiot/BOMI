"""실물 조이스틱 SLAM 통합 launch의 핵심 연결을 검증한다."""

import ast
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROBOT_LAUNCH = PACKAGE_ROOT / "launch" / "joystick_slam_robot.launch.py"
PICO_CONFIG = PACKAGE_ROOT / "config" / "pico_driver.yaml"


def test_joystick_slam_launch_has_valid_python_syntax():
    """통합 launch 파일이 Python 문법에 맞는지 검증한다."""
    ast.parse(ROBOT_LAUNCH.read_text(encoding="utf-8"))


def test_joystick_slam_launch_exposes_scan_matching_switches():
    """스캔 매칭과 루프 클로저를 launch 인자로 켜고 끌 수 있는지 검증한다."""
    launch_source = ROBOT_LAUNCH.read_text(encoding="utf-8")

    for argument in ("use_scan_matching", "do_loop_closing"):
        assert f'"{argument}"' in launch_source
        assert f'{argument},' in launch_source


def test_pico_driver_control_rate_matches_firmware_period():
    """
    V 전송과 텔레메트리 처리 주기가 펌웨어 20 ms 주기와 같은지 검증한다.

    이보다 낮으면 텔레메트리 여러 줄이 한 주기에 몰려 stamp가 실제 표본
    시각과 어긋난다. robot/docs/pico-serial-protocol.md `## 4` 참고.
    """
    config = yaml.safe_load(PICO_CONFIG.read_text(encoding="utf-8"))
    parameters = config["pico_driver"]["ros__parameters"]

    assert parameters["control_hz"] == 50.0


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
