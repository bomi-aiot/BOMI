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


def test_real_slam_config_keeps_matching_anchored_to_odometry():
    """좁은 정사각형 공간에서 90° 오정합을 막는 값이 유지되는지 검증한다.

    약 3 m x 3 m 정사각형 공간은 90° 돌려도 스캔이 거의 같아 보이므로,
    스캔 매칭이 odometry에서 멀리 벗어난 답을 고를 수 있으면 지도가 90°씩
    돌아간 여러 장으로 겹친다.
    """
    config = yaml.safe_load(REAL_SLAM_CONFIG.read_text(encoding="utf-8"))
    parameters = config["slam_toolbox"]["ros__parameters"]

    # 각도 탐색 범위가 90°에 가까워지면 회전 대칭인 답을 고를 수 있다.
    assert parameters["coarse_search_angle_offset"] <= 0.1

    # 스캔을 드물게 넣으면 이전 스캔과 겹치는 부분을 잃는다.
    assert parameters["minimum_travel_distance"] <= 0.2
    assert parameters["minimum_travel_heading"] <= 0.2

    # 기본 탐색 격자(8 m)는 3 m 공간에서 모든 과거 위치를 후보로 만든다.
    assert parameters["do_loop_closing"] is False
    assert parameters["loop_search_space_dimension"] <= 3.0


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
