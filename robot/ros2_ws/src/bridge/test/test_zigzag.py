"""zigzag_path(현관 지그재그 접근)의 순수 기하 검증.

ROS 2 도 Nav2 도 필요 없다 — 좌표 계산만 하는 모듈이므로 값으로 확인한다.
가장 중요한 성질 두 가지를 고정한다: **도착 좌표가 옮겨지지 않는다**는 것과
**모든 다리가 축 기준 정확히 ±angle_deg 로 기운다**는 것.
"""

from __future__ import annotations

import math

import pytest

from bridge.zigzag import (
    DEFAULT_ZIGZAG_ANGLE_DEG,
    ZigzagPose,
    zigzag_path,
)


def _leg_angles(start_x, start_y, poses, bearing):
    """각 다리가 축(bearing)에서 몇 도 기울었는지 돌려준다."""
    angles = []
    previous_x, previous_y = start_x, start_y
    for pose in poses:
        leg = math.atan2(pose.y - previous_y, pose.x - previous_x)
        # -pi..pi 로 정규화한 뒤 도 단위로.
        offset = math.degrees(math.atan2(
            math.sin(leg - bearing), math.cos(leg - bearing)))
        angles.append(offset)
        previous_x, previous_y = pose.x, pose.y
    return angles


def test_last_pose_is_exactly_the_goal() -> None:
    """지그재그를 넣어도 도착 좌표와 yaw 는 조금도 달라지지 않는다."""
    poses = zigzag_path(0.0, 0.0, 3.0, 0.0, 1.5)

    assert poses[-1] == ZigzagPose(x=3.0, y=0.0, yaw=1.5)


def test_every_leg_is_tilted_by_the_requested_angle() -> None:
    """모든 다리가 축 기준 +15도/-15도 를 번갈아 유지한다."""
    poses = zigzag_path(0.0, 0.0, 3.0, 0.0, 0.0)
    angles = _leg_angles(0.0, 0.0, poses, bearing=0.0)

    assert len(angles) >= 4
    for index, angle in enumerate(angles):
        expected = DEFAULT_ZIGZAG_ANGLE_DEG * (1 if index % 2 == 0 else -1)
        assert angle == pytest.approx(expected, abs=1e-9)


def test_works_on_a_diagonal_axis() -> None:
    """축이 기울어도(대각선 이동) 같은 성질이 유지된다."""
    start_x, start_y = 1.0, -2.0
    goal_x, goal_y = 4.0, 1.5
    bearing = math.atan2(goal_y - start_y, goal_x - start_x)

    poses = zigzag_path(start_x, start_y, goal_x, goal_y, 0.3)
    angles = _leg_angles(start_x, start_y, poses, bearing)

    assert poses[-1].x == pytest.approx(goal_x)
    assert poses[-1].y == pytest.approx(goal_y)
    for index, angle in enumerate(angles):
        expected = DEFAULT_ZIGZAG_ANGLE_DEG * (1 if index % 2 == 0 else -1)
        assert angle == pytest.approx(expected, abs=1e-9)


def test_lateral_excursion_stays_small() -> None:
    """측면 이탈이 벽 팽창 반경(0.4m)보다 충분히 작아야 한다.

    이 성질이 깨지면 경유점이 벽 근처 팽창 영역에 들어가 Nav2 가 경로를
    찾지 못한다 — 지그재그가 주행을 실패시키는 경로다.
    """
    poses = zigzag_path(0.0, 0.0, 5.0, 0.0, 0.0)

    lateral = [abs(pose.y) for pose in poses]
    assert max(lateral) < 0.2


def test_short_moves_are_left_straight() -> None:
    """1m 미만 이동은 꺾지 않고 목표 하나만 돌려준다."""
    poses = zigzag_path(0.0, 0.0, 0.4, 0.0, 0.9)

    assert poses == [ZigzagPose(x=0.4, y=0.0, yaw=0.9)]


def test_leg_count_is_capped() -> None:
    """먼 거리에서도 경유점이 상한을 넘지 않는다."""
    poses = zigzag_path(0.0, 0.0, 50.0, 0.0, 0.0, max_legs=6)

    assert len(poses) <= 6


def test_leg_count_is_even_so_the_path_closes_on_the_axis() -> None:
    """다리 수가 짝수라야 좌우 이탈이 상쇄되어 목표에서 끝난다."""
    for distance in (1.2, 2.0, 2.7, 3.3, 4.9):
        poses = zigzag_path(0.0, 0.0, distance, 0.0, 0.0)
        # 다리 수 = 경유점 수. 짝수여야 한다.
        assert len(poses) % 2 == 0, f"distance={distance}"
        assert poses[-1].y == pytest.approx(0.0)


@pytest.mark.parametrize("angle", [0.0, -5.0, 90.0, 120.0])
def test_rejects_invalid_angles(angle: float) -> None:
    with pytest.raises(ValueError):
        zigzag_path(0.0, 0.0, 3.0, 0.0, 0.0, angle_deg=angle)


def test_rejects_invalid_leg_length() -> None:
    with pytest.raises(ValueError):
        zigzag_path(0.0, 0.0, 3.0, 0.0, 0.0, leg_length_m=0.0)
