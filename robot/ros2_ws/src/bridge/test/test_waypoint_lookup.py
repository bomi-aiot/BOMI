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


def test_living_room_target_maps_to_sofa_waypoint_name() -> None:
    # LIVING_ROOM은 sofa와 같은 지점이다(보미야 호출·복약·온습도의 목적지).
    assert resolve_waypoint_name(contract.TARGET_LIVING_ROOM) == "sofa"


def test_every_contract_navigation_target_resolves() -> None:
    """계약이 정의한 목적지 전부가 매핑표에 있는지 전수 검사한다.

    목적지를 하나씩만 검사하면 표에서 빠진 목적지를 알아챌 수 없다. 실제로
    LIVING_ROOM이 표에서 빠진 채 머지되어 보미야 호출·복약·온습도 시나리오가
    전부 FAILED로 떨어진 적이 있다. 계약을 단일 출처로 삼는다.
    """
    unresolved = [
        target
        for target in sorted(contract.NAVIGATION_TARGETS)
        if resolve_waypoint_name(target) is None
    ]

    assert unresolved == []


def test_every_resolved_waypoint_name_exists_in_shipped_config() -> None:
    """매핑표가 가리키는 이름이 실제 room_waypoints.yaml에 있는지 확인한다.

    표에 목적지가 있어도 가리키는 웨이포인트 이름이 좌표 파일에 없으면 주행
    시점에 KeyError로 실패한다. 좌표 파일과 매핑표는 서로 다른 패키지에서
    따로 수정되므로, 둘이 어긋난 상태로 커밋되는 것을 여기서 막는다.
    """
    config = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "config"
        / "room_waypoints.yaml"
    )
    resolved = [
        (target, resolve_waypoint_name(target))
        for target in sorted(contract.NAVIGATION_TARGETS)
    ]
    missing = [
        f"{target} -> {name}"
        for target, name in resolved
        if name is not None and not _has_waypoint(config, name)
    ]

    assert missing == []


def _has_waypoint(config: Path, waypoint_name: str) -> bool:
    try:
        load_waypoint(config, waypoint_name)
    except KeyError:
        return False
    return True


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
