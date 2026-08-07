"""MQTT 전진 테스트 launch와 twist_mux 연결 설정을 검증한다."""

import ast
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_SRC = PACKAGE_ROOT.parent
LAUNCH_FILE = PACKAGE_ROOT / "launch" / "backend_drive_test.launch.py"
MUX_CONFIG = WORKSPACE_SRC / "core" / "config" / "twist_mux.yaml"


def test_backend_drive_launch_has_valid_python_syntax() -> None:
    """통신 테스트 launch 파일이 Python 문법에 맞는지 검증한다."""
    ast.parse(LAUNCH_FILE.read_text(encoding="utf-8"))


def test_backend_drive_launch_uses_forward_driver_and_mux() -> None:
    """forward_test만 선택하고 최종 속도를 /cmd_vel로 연결하는지 확인한다."""
    source = LAUNCH_FILE.read_text(encoding="utf-8")

    assert '"driver_type": "forward_test"' in source
    assert '"test_cmd_vel_topic": "/cmd_vel_backend_test"' in source
    assert 'package="twist_mux"' in source
    assert '("/cmd_vel_out", "/cmd_vel")' in source
    assert 'executable="pico_driver"' not in source


def test_mux_contains_backend_test_input_below_joystick_priority() -> None:
    """전용 토픽이 mux에 있고 조이스틱이 더 높은 우선순위를 갖는지 확인한다."""
    parameters = yaml.safe_load(MUX_CONFIG.read_text(encoding="utf-8"))
    topics = parameters["twist_mux"]["ros__parameters"]["topics"]

    assert topics["backend_test"]["topic"] == "/cmd_vel_backend_test"
    assert topics["backend_test"]["timeout"] == 0.5
    assert topics["keyboard"]["priority"] < topics["backend_test"]["priority"]
    assert topics["backend_test"]["priority"] < topics["joystick"]["priority"]
