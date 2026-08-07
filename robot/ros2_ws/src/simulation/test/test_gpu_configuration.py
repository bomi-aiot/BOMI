"""BOMI Gazebo의 WSLg 렌더링 설정을 검증한다."""

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_LAUNCH = PACKAGE_ROOT / "launch" / "bomi_sim.launch.py"
SIMULATION_WORLD = PACKAGE_ROOT / "worlds" / "bomi_test_world.sdf"


def test_simulation_launch_has_valid_python_syntax():
    """BOMI 시뮬레이션 launch 파일이 Python 문법에 맞는지 확인한다."""
    ast.parse(SIMULATION_LAUNCH.read_text(encoding="utf-8"))


def test_simulation_uses_stable_wslg_software_rendering():
    """Gazebo 프로세스에서만 WSL용 소프트웨어 렌더링을 적용하는지 확인한다."""
    launch_source = SIMULATION_LAUNCH.read_text(encoding="utf-8")

    assert 'LaunchConfiguration("gpu_adapter")' not in launch_source
    assert 'default_value="NVIDIA"' not in launch_source
    assert launch_source.count("additional_env=") == 2
    assert "SetEnvironmentVariable" not in launch_source
    assert launch_source.count('"LIBGL_ALWAYS_SOFTWARE": "1"') == 2
    assert launch_source.count('"GALLIUM_DRIVER": "llvmpipe"') == 2


def test_simulation_supports_headless_gpu_sensor_execution():
    """Gazebo GUI 없이 서버와 GPU 센서를 실행할 수 있는지 확인한다."""
    launch_source = SIMULATION_LAUNCH.read_text(encoding="utf-8")

    assert 'LaunchConfiguration("headless")' in launch_source
    assert 'condition=IfCondition(headless)' in launch_source
    assert 'condition=UnlessCondition(headless)' in launch_source
    assert '"-s"' in launch_source


def test_simulation_uses_ogre2_for_gpu_lidar():
    """GPU LiDAR에 필요한 Ogre2 렌더러를 일관되게 사용하는지 확인한다."""
    launch_source = SIMULATION_LAUNCH.read_text(encoding="utf-8")
    world_source = SIMULATION_WORLD.read_text(encoding="utf-8")

    assert launch_source.count('"--render-engine"') == 2
    assert launch_source.count('"ogre2"') == 2
    assert "<render_engine>ogre2</render_engine>" in world_source
    assert "<render_engine>ogre</render_engine>" not in world_source


def test_navigation_world_has_localization_boundaries():
    """저장 지도 기반 위치 추정에 필요한 네 방향 경계 벽을 확인한다."""
    world_source = SIMULATION_WORLD.read_text(encoding="utf-8")

    for wall_name in ("north_wall", "south_wall", "east_wall", "west_wall"):
        assert f'<model name="{wall_name}">' in world_source
