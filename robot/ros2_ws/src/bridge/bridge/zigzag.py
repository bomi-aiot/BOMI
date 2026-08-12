r"""현관까지 지그재그로 다가가는 경유 좌표를 만드는 순수 기하 모듈.

왜 존재하는가
    현관 대본에서 로봇은 문 앞 좌표까지 최단 직선에 가깝게 온다. 기능상
    문제는 없지만 어르신을 반기러 나가는 동작으로는 무뚝뚝하다. 직진 방향을
    기준으로 좌우 15도씩 번갈아 틀며 다가가면 같은 좌표에 도착하면서도
    "반가워서 들뜬" 걸음으로 읽힌다.

왜 Nav2 를 그대로 쓰는가 (직접 cmd_vel 을 쏘지 않는다)
    지그재그를 cmd_vel 로 직접 그리면 costmap 도 장애물 회피도 사라진다.
    현관은 이 집에서 벽과 문이 가장 가까운 자리라 그 방식은 위험하다.
    그래서 이 모듈은 **경유 좌표만** 만들고, 주행은 Nav2
    NavigateThroughPoses 가 한다 — 회피·경로계획·복구가 전부 살아 있고,
    바뀌는 것은 "어디를 지나가는가" 뿐이다.

기하
    출발점 S 에서 목표 G 로 향하는 직선을 축으로 삼는다. 축을 같은 길이의
    다리(leg) N 개로 쪼개고, 각 다리를 축 기준 +theta, -theta 로 번갈아
    기울인다. N 이 짝수면 좌우 이탈이 정확히 상쇄되어 마지막 다리가 G 에서
    끝난다 — 지그재그를 넣어도 도착 좌표는 조금도 달라지지 않는다.

        측면 이탈
          ^
      +A  |    /\        /\
          |   /  \      /  \
        0 +--S----\----/----\----G--> 축(S->G)
          |        \  /      \  /
      -A  |         \/        \/

    한 다리의 축 길이를 a = D/N 이라 하면 측면 진폭은 A = a*tan(theta) 다.
    theta 15도, a 0.5m 면 A 는 약 0.13m — 복도 폭에 견주면 작다. 진폭이
    커지면 경유점이 벽 팽창 영역(inflation_radius 0.4m)에 들어가 Nav2 가
    경로를 못 찾으므로, 다리를 짧게 두는 것이 곧 안전 여유다.

경계 조건
    * 거리가 min_distance_m 보다 짧으면 지그재그를 넣지 않고 목표만
      돌려준다. 1m 도 안 되는 이동을 여섯 번 꺾으면 제자리에서 비틀대는
      것처럼 보이고, 경유점 간격이 xy_goal_tolerance(0.10m)에 근접해
      Nav2 가 이미 도착했다고 볼 수도 있다.
    * 다리 수는 max_legs 로 상한을 둔다. 먼 거리에서 경유점이 수십 개가
      되면 경로가 길어져 도착이 늦고, 실패 지점만 늘어난다.
    * 반환 목록의 마지막은 **항상 목표 좌표와 목표 yaw** 다. 중간 경유점의
      yaw 는 그 지점에서 다음 경유점으로 향하는 진행 방향이라, 로봇이 실제로
      좌우로 몸을 틀며 간다.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

#: 직진 축 기준으로 좌우로 트는 각도(도).
#:   올리면 -> 지그재그가 뚜렷해지지만 측면 이탈이 커져 벽에 가까워진다.
#:   내리면 -> 안전하지만 거의 직진으로 보인다.
DEFAULT_ZIGZAG_ANGLE_DEG = 15.0

#: 다리 하나의 축 방향 길이(m). 측면 진폭 A = 이 값 * tan(각도) 다.
DEFAULT_ZIGZAG_LEG_LENGTH_M = 0.5

#: 이 거리보다 짧게 이동할 때는 지그재그를 넣지 않는다(m).
DEFAULT_ZIGZAG_MIN_DISTANCE_M = 1.0

#: 다리 수 상한(짝수). 먼 거리에서도 경유점이 이 이상 늘지 않는다.
DEFAULT_ZIGZAG_MAX_LEGS = 12


@dataclass(frozen=True)
class ZigzagPose:
    """지그재그 경로의 한 지점. Nav2 PoseStamped 로 옮겨질 값만 담는다."""

    x: float
    y: float
    yaw: float


def zigzag_path(
    start_x: float,
    start_y: float,
    goal_x: float,
    goal_y: float,
    goal_yaw: float,
    *,
    angle_deg: float = DEFAULT_ZIGZAG_ANGLE_DEG,
    leg_length_m: float = DEFAULT_ZIGZAG_LEG_LENGTH_M,
    min_distance_m: float = DEFAULT_ZIGZAG_MIN_DISTANCE_M,
    max_legs: int = DEFAULT_ZIGZAG_MAX_LEGS,
) -> list[ZigzagPose]:
    """출발점에서 목표까지 지그재그로 지나갈 경유 좌표를 만든다.

    역할: S->G 직선을 축으로 좌우 angle_deg 씩 번갈아 기운 다리로 쪼개고,
        각 꺾이는 지점을 경유 좌표로 돌려준다.
    입력값: start_x/start_y - 현재 위치(map 좌표계). goal_x/goal_y/goal_yaw -
        목표 웨이포인트. angle_deg/leg_length_m/min_distance_m/max_legs -
        위 상수 참고.
    반환값: 경유 좌표 목록. **마지막 원소는 항상 목표 좌표와 목표 yaw** 다.
        지그재그를 넣지 않는 경우(너무 가까움) 목표 하나만 담긴 목록이다.
    실패: angle_deg 가 0 이하이거나 90도 이상, leg_length_m 이 0 이하,
        max_legs 가 2 미만이면 ValueError.
    """
    if not 0.0 < angle_deg < 90.0:
        raise ValueError("angle_deg must be between 0 and 90 degrees")
    if leg_length_m <= 0.0:
        raise ValueError("leg_length_m must be positive")
    if max_legs < 2:
        raise ValueError("max_legs must be at least 2")

    goal = ZigzagPose(x=goal_x, y=goal_y, yaw=goal_yaw)

    delta_x = goal_x - start_x
    delta_y = goal_y - start_y
    distance = math.hypot(delta_x, delta_y)

    # 너무 가까우면 꺾지 않는다. 여기서 걸러 두면 아래 나눗셈이 0 거리를
    # 만날 일도 없다.
    if distance < min_distance_m:
        return [goal]

    theta = math.radians(angle_deg)
    bearing = math.atan2(delta_y, delta_x)

    # 다리 수는 짝수여야 좌우 이탈이 상쇄되어 마지막 다리가 목표에서 끝난다.
    # 축 길이 기준으로 leg_length_m 에 가장 가까운 짝수를 고른다.
    raw_legs = distance / leg_length_m
    legs = 2 * max(1, round(raw_legs / 2))
    legs = min(legs, max_legs - max_legs % 2)

    axial_step = distance / legs
    amplitude = axial_step * math.tan(theta)

    poses: list[ZigzagPose] = []
    for index in range(1, legs):
        axial = index * axial_step
        # 홀수 번째 꼭짓점만 축에서 벗어난다. 짝수 번째는 축 위로 돌아온다.
        lateral = amplitude if index % 2 == 1 else 0.0
        # 이 지점에서 다음 지점으로 향하는 방향이 곧 이 지점의 yaw 다.
        # 짝수에서 출발하는 다리는 축에서 멀어지고(+theta), 홀수에서
        # 출발하는 다리는 축으로 돌아온다(-theta).
        heading = bearing + (theta if index % 2 == 0 else -theta)
        poses.append(
            ZigzagPose(
                x=start_x + axial * math.cos(bearing)
                - lateral * math.sin(bearing),
                y=start_y + axial * math.sin(bearing)
                + lateral * math.cos(bearing),
                yaw=heading,
            )
        )

    # 마지막은 언제나 목표 그 자체다 — 지그재그가 도착 좌표를 옮기지 않는다.
    poses.append(goal)
    return poses
