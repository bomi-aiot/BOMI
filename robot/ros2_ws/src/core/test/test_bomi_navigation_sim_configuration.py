"""BOMI 저장 지도 기반 Nav2 시뮬레이션 구성을 검증한다."""

import ast
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_SRC = PACKAGE_ROOT.parent
LAUNCH_FILE = PACKAGE_ROOT / "launch" / "bomi_navigation_sim.launch.py"
MAP_FILE = WORKSPACE_SRC / "mapping" / "maps" / "bomi_test_map.yaml"
NAV2_PARAMS_FILE = PACKAGE_ROOT / "config" / "nav2_safe_params.yaml"
RVIZ_FILE = PACKAGE_ROOT / "rviz" / "bomi_navigation.rviz"


def _nav2_params():
    return yaml.safe_load(NAV2_PARAMS_FILE.read_text(encoding="utf-8"))


def test_bomi_navigation_launch_has_valid_python_syntax():
    """BOMI 내비게이션 launch 파일이 Python 문법에 맞는지 확인한다."""
    ast.parse(LAUNCH_FILE.read_text(encoding="utf-8"))


def test_bomi_navigation_launch_connects_saved_map_amcl_and_nav2():
    """저장 지도와 BOMI 시뮬레이터가 Nav2에 연결되는지 확인한다."""
    launch_source = LAUNCH_FILE.read_text(encoding="utf-8")

    assert 'get_package_share_directory("mapping")' in launch_source
    assert 'get_package_share_directory("simulation")' in launch_source
    assert 'get_package_share_directory("nav2_bringup")' in launch_source
    assert '"bomi_sim.launch.py"' in launch_source
    assert '"bomi_test_map.yaml"' in launch_source
    assert '"localization_launch.py"' in launch_source
    assert '"navigation_launch.py"' in launch_source
    assert '"base_frame_id": "base_link"' in launch_source
    assert '"robot_radius": "0.31"' in launch_source
    assert '"gpu_adapter": gpu_adapter' not in launch_source
    assert '"headless",\n                default_value="True"' in launch_source
    assert '"LIBGL_ALWAYS_SOFTWARE": "1"' in launch_source
    assert '"GALLIUM_DRIVER": "llvmpipe"' in launch_source
    assert "start_navigation_after_initial_pose" in launch_source
    assert "nav2_waypoint_patrol" not in launch_source


def test_default_bomi_map_references_installed_image():
    """기본 지도 YAML이 함께 설치되는 지도 이미지를 가리키는지 확인한다."""
    map_config = yaml.safe_load(MAP_FILE.read_text(encoding="utf-8"))
    image_file = MAP_FILE.parent / map_config["image"]

    assert map_config["resolution"] > 0.0
    assert image_file.is_file()
    assert image_file.stat().st_size > 10_000


def test_bomi_navigation_uses_lightweight_rviz_configuration():
    """내비게이션 검증에 필요한 표시만 낮은 프레임률로 구성하는지 확인한다."""
    launch_source = LAUNCH_FILE.read_text(encoding="utf-8")
    rviz_config = yaml.safe_load(RVIZ_FILE.read_text(encoding="utf-8"))
    manager = rviz_config["Visualization Manager"]
    display_names = {display["Name"] for display in manager["Displays"]}

    assert 'core_share / "rviz" / "bomi_navigation.rviz"' in launch_source
    assert manager["Global Options"]["Frame Rate"] == 5
    assert {"Map", "AMCL Particles", "Global Path", "Robot Footprint"} <= (
        display_names
    )
    assert "Global Costmap" not in display_names
    assert "Local Costmap" not in display_names


def test_bomi_simulation_provides_nav2_topics_and_frames():
    """BOMI 모델이 Nav2에 필요한 명령·오도메트리 프레임을 제공하는지 확인한다."""
    model_file = (
        WORKSPACE_SRC
        / "description"
        / "models"
        / "bomi_robot"
        / "model.sdf"
    )
    model_source = model_file.read_text(encoding="utf-8")

    assert "<topic>/cmd_vel</topic>" in model_source
    assert "<odom_topic>/odom</odom_topic>" in model_source
    assert "<frame_id>odom</frame_id>" in model_source
    assert "<child_frame_id>base_link</child_frame_id>" in model_source


def test_dwb_goal_tolerance_matches_the_goal_checker():
    """
    DWB의 목표 반경이 목표 판정 반경보다 크지 않은지 확인한다.

    DWB의 RotateToGoal critic은 FollowPath의 xy_goal_tolerance 안에서
    전진을 막는다. 이 값이 general_goal_checker보다 크면 그 사이 구간에
    갇혀 목표 판정이 나지 않고 "Failed to make progress"로 중단된다.
    """
    controller = _nav2_params()["controller_server"]["ros__parameters"]
    goal_checker_tolerance = controller["general_goal_checker"]["xy_goal_tolerance"]
    dwb_tolerance = controller["FollowPath"]["xy_goal_tolerance"]

    assert dwb_tolerance <= goal_checker_tolerance


def test_local_costmap_keeps_the_saved_map_walls():
    """로컬 코스트맵이 저장 지도의 벽을 함께 보도록 static_layer를 쓰는지 확인한다."""
    local_costmap = _nav2_params()["local_costmap"]["local_costmap"]["ros__parameters"]

    assert "static_layer" in local_costmap["plugins"]
    assert (
        local_costmap["static_layer"]["plugin"]
        == "nav2_costmap_2d::StaticLayer"
    )
