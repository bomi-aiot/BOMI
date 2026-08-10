"""사용자 탐색 실행 파일과 기본 설정의 패키지 연결을 검증한다."""

import ast
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_person_search_launch_has_valid_python_syntax() -> None:
    """사용자 탐색 launch 파일이 유효한 Python인지 확인한다."""
    launch_path = PACKAGE_ROOT / "launch" / "person_search_patrol.launch.py"
    ast.parse(launch_path.read_text(encoding="utf-8"))


def test_person_search_console_script_is_registered() -> None:
    """ros2 run에서 사용자 탐색 노드를 찾을 수 있는지 확인한다."""
    setup_text = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert "person_search_patrol = core.person_search_patrol:main" in setup_text


def test_person_search_defaults_use_separate_control_topics() -> None:
    """탐색 명령, 상태와 추종 스위치 토픽이 명확히 분리됐는지 확인한다."""
    config_path = PACKAGE_ROOT / "config" / "person_search_patrol.yaml"
    parameters = yaml.safe_load(config_path.read_text(encoding="utf-8"))[
        "person_search_patrol"
    ]["ros__parameters"]

    assert parameters["enable_topic"] == "/person_search/enable"
    assert parameters["status_topic"] == "/person_search/status"
    assert parameters["follow_enable_topic"] == "/person_following/enable"
    assert parameters["target_confirm_sec"] == 0.5
