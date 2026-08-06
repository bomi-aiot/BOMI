"""실물 LiDAR 지도 생성 설정의 핵심 연결을 정적으로 검증한다."""

import ast
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REAL_LAUNCH = PACKAGE_ROOT / "launch" / "mapping_real.launch.py"
REAL_SLAM_CONFIG = PACKAGE_ROOT / "config" / "slam_toolbox_real.yaml"


def test_real_mapping_launch_has_valid_python_syntax():
    """통합 launch 파일이 Python 문법에 맞는지 검증한다."""
    ast.parse(REAL_LAUNCH.read_text(encoding="utf-8"))


def test_real_slam_config_uses_wall_time_and_expected_frames():
    """실물 SLAM 설정이 RF2O TF와 동일한 프레임을 사용하는지 검증한다."""
    config = yaml.safe_load(REAL_SLAM_CONFIG.read_text(encoding="utf-8"))
    parameters = config["slam_toolbox"]["ros__parameters"]

    assert parameters["use_sim_time"] is False
    assert parameters["mode"] == "mapping"
    assert parameters["map_frame"] == "map"
    assert parameters["odom_frame"] == "odom"
    assert parameters["base_frame"] == "base_link"
    assert parameters["scan_topic"] == "/scan"


def test_real_mapping_reuses_lidar_launch_without_static_tf_duplication():
    """기존 LiDAR TF를 포함하고 새 정적 TF를 만들지 않는지 검증한다."""
    launch_source = REAL_LAUNCH.read_text(encoding="utf-8")

    assert "x4_pro.launch.py" in launch_source
    assert "static_transform_publisher" not in launch_source
    assert '"odom_topic": odom_topic' in launch_source
    assert '"publish_tf": True' in launch_source


def test_real_mapping_launch_forwards_measured_lidar_transform():
    """실측 LiDAR 위치와 자세를 하위 launch에 전달하는지 검증한다."""
    launch_source = REAL_LAUNCH.read_text(encoding="utf-8")

    for argument in (
        "laser_x",
        "laser_y",
        "laser_z",
        "laser_roll",
        "laser_pitch",
        "laser_yaw",
    ):
        assert f'"{argument}": {argument}' in launch_source
