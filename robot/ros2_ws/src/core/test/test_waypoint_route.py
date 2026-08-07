"""순찰 waypoint 로딩과 경로 순서 로직을 검증한다."""

from pathlib import Path

import pytest

from core.waypoint_route import (
    PatrolRoute,
    Waypoint,
    WaypointConfigError,
    load_patrol_route,
    yaw_to_quaternion,
)


def write_config(tmp_path: Path, content: str) -> Path:
    """테스트용 waypoint YAML 파일을 생성한다."""
    path = tmp_path / "waypoints.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_patrol_route_reads_waypoints(tmp_path):
    """YAML waypoint를 순찰 경로로 읽는지 확인한다."""
    path = write_config(
        tmp_path,
        """
waypoints:
  - name: sofa
    x: 1.0
    y: 2.0
    yaw: 0.5
loop: false
max_goal_retries: 2
goal_retry_delay_sec: 4.0
""",
    )

    route = load_patrol_route(path)

    assert route.loop is False
    assert route.max_goal_retries == 2
    assert route.goal_retry_delay_sec == 4.0
    assert route.current() == Waypoint(
        name="sofa",
        x=1.0,
        y=2.0,
        yaw=0.5,
    )


def test_route_advances_and_stops_when_loop_is_false():
    """반복이 꺼진 경로의 종료를 확인한다."""
    route = PatrolRoute(
        waypoints=[
            Waypoint("a", 0.0, 0.0, 0.0),
            Waypoint("b", 1.0, 0.0, 0.0),
        ],
        loop=False,
    )

    assert route.current().name == "a"
    assert route.move_to_next().name == "b"
    assert route.move_to_next() is None
    assert route.current() is None


def test_route_wraps_when_loop_is_true():
    """반복 경로가 첫 지점으로 돌아오는지 확인한다."""
    route = PatrolRoute(
        waypoints=[
            Waypoint("a", 0.0, 0.0, 0.0),
            Waypoint("b", 1.0, 0.0, 0.0),
        ],
        loop=True,
    )

    assert route.move_to_next().name == "b"
    assert route.move_to_next().name == "a"


def test_route_retries_current_goal_with_a_limit():
    """목표 실패를 제한 횟수만큼 같은 지점에서 재시도한다."""
    route = PatrolRoute(
        waypoints=[
            Waypoint("a", 0.0, 0.0, 0.0),
            Waypoint("b", 1.0, 0.0, 0.0),
        ],
        loop=True,
        max_goal_retries=2,
        goal_retry_delay_sec=1.0,
    )

    assert route.record_goal_failure() == 1
    assert route.current().name == "a"
    assert route.record_goal_failure() == 2
    assert route.current().name == "a"
    assert route.record_goal_failure() is None

    assert route.move_to_next().name == "b"
    assert route.record_goal_failure() == 1


def test_route_rejects_immediate_retry_loop():
    """재시도 활성화 시 0초 대기 설정을 거부한다."""
    with pytest.raises(WaypointConfigError):
        PatrolRoute(
            waypoints=[Waypoint("a", 0.0, 0.0, 0.0)],
            loop=True,
            max_goal_retries=1,
            goal_retry_delay_sec=0.0,
        )


def test_load_patrol_route_rejects_invalid_number(tmp_path):
    """잘못된 waypoint 좌표를 거부하는지 확인한다."""
    path = write_config(
        tmp_path,
        """
waypoints:
  - name: bad
    x: .nan
    y: 0.0
    yaw: 0.0
""",
    )

    with pytest.raises(WaypointConfigError):
        load_patrol_route(path)


def test_yaw_to_quaternion_converts_planar_rotation():
    """평면 yaw 각도가 quaternion으로 변환되는지 확인한다."""
    _, _, qz, qw = yaw_to_quaternion(3.141592653589793)

    assert qz == pytest.approx(1.0)
    assert qw == pytest.approx(0.0)
