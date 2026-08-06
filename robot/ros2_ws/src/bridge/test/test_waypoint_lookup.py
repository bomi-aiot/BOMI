"""목적지 이름 변환과 웨이포인트 로딩(순수 로직)을 검증하는 단위 테스트다.

ROS 2나 Nav2 없이 실행한다. core의 waypoint_route 로더와 임시 YAML 파일만
사용하므로 실제 주행 환경이 필요 없다.
"""

from pathlib import Path

from bridge import contract
from bridge.waypoint_lookup import load_waypoint, resolve_waypoint_name
from core.waypoint_route import WaypointConfigError
import pytest


def _write_waypoints(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "room_waypoints.yaml"
    path.write_text(content, encoding="utf-8")
    return path


_VALID_WAYPOINTS = """
waypoints:
  - name: entrance
    x: -0.226
    y: -1.520
    yaw: 1.57
  - name: sofa
    x: 0.178
    y: 1.722
    yaw: 0.0
  - name: charging
    x: 0.0
    y: 0.0
    yaw: 0.0
"""


def test_entrance_target_maps_to_entrance_waypoint_name() -> None:
    assert resolve_waypoint_name(contract.TARGET_ENTRANCE) == "entrance"


def test_default_target_maps_to_charging_waypoint_name() -> None:
    # DEFAULT는 충전소 도킹 위치(지도 원점)를 가리킨다.
    assert resolve_waypoint_name(contract.TARGET_DEFAULT) == "charging"


def test_unknown_target_is_not_supported() -> None:
    assert resolve_waypoint_name("KITCHEN") is None


def test_none_target_is_not_supported() -> None:
    assert resolve_waypoint_name(None) is None


def test_load_waypoint_reads_entrance_coordinates(tmp_path) -> None:
    path = _write_waypoints(tmp_path, _VALID_WAYPOINTS)

    waypoint = load_waypoint(path, "entrance")

    assert waypoint.name == "entrance"
    assert waypoint.x == pytest.approx(-0.226)
    assert waypoint.y == pytest.approx(-1.520)
    assert waypoint.yaw == pytest.approx(1.57)


def test_load_waypoint_reads_charging_coordinates(tmp_path) -> None:
    path = _write_waypoints(tmp_path, _VALID_WAYPOINTS)

    waypoint = load_waypoint(path, "charging")

    assert waypoint.name == "charging"
    assert waypoint.x == pytest.approx(0.0)
    assert waypoint.y == pytest.approx(0.0)
    assert waypoint.yaw == pytest.approx(0.0)


def test_load_waypoint_missing_name_raises_key_error(tmp_path) -> None:
    path = _write_waypoints(tmp_path, _VALID_WAYPOINTS)

    with pytest.raises(KeyError):
        load_waypoint(path, "garage")


def test_load_waypoint_missing_file_raises(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.yaml"

    with pytest.raises(OSError):
        load_waypoint(missing, "entrance")


def test_load_waypoint_invalid_data_raises(tmp_path) -> None:
    # x가 없는 잘못된 웨이포인트는 성공으로 처리되지 않고 예외로 이어진다.
    invalid = """
waypoints:
  - name: entrance
    y: -1.520
    yaw: 1.57
"""
    path = _write_waypoints(tmp_path, invalid)

    with pytest.raises(WaypointConfigError):
        load_waypoint(path, "entrance")
