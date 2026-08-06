"""LiDAR 스캔 데이터에서 전방의 가장 가까운 거리를 계산한다."""

import math

from sensor_msgs.msg import LaserScan


ANGLE_TOLERANCE_RAD = 1e-6


def calculate_front_distance(
    scan: LaserScan,
    front_angle_min_deg: float,
    front_angle_max_deg: float,
) -> float:
    """
    설정된 전방 각도 범위에서 가장 가까운 유효 거리를 계산한다.

    입력:
        scan: LiDAR의 전체 거리 데이터가 담긴 LaserScan 메시지
        front_angle_min_deg: 사용할 전방 최소 각도
        front_angle_max_deg: 사용할 전방 최대 각도

    출력:
        가장 가까운 유효 거리(m)를 반환한다.
        유효한 거리값이 없으면 NaN을 반환한다.

    주의사항:
        0, NaN, inf 및 센서 측정 범위를 벗어난 값은 제외한다.
        현재는 최소 각도부터 최대 각도까지 이어지는 범위만 지원한다.
    """
    if front_angle_min_deg > front_angle_max_deg:
        raise ValueError(
            "front_angle_min_deg는 "
            "front_angle_max_deg보다 작거나 같아야 합니다."
        )

    front_angle_min_rad = math.radians(front_angle_min_deg)
    front_angle_max_rad = math.radians(front_angle_max_deg)

    valid_distances: list[float] = []

    for index, distance in enumerate(scan.ranges):
        # 배열의 위치를 실제 LiDAR 측정 각도로 변환한다.
        angle_rad = scan.angle_min + index * scan.angle_increment

        # 지정한 전방 각도 범위 밖의 측정값은 사용하지 않는다.
        if angle_rad < front_angle_min_rad - ANGLE_TOLERANCE_RAD:
            continue

        if angle_rad > front_angle_max_rad + ANGLE_TOLERANCE_RAD:
            continue

        # NaN과 inf는 실제 거리로 사용할 수 없다.
        if not math.isfinite(distance):
            continue

        # 측정에 실패했을 때 들어올 수 있는 0.0을 제외한다.
        if distance <= 0.0:
            continue

        # 센서가 알려주는 유효 측정 범위를 벗어난 값은 제외한다.
        if distance < scan.range_min:
            continue

        if distance > scan.range_max:
            continue

        valid_distances.append(float(distance))

    if not valid_distances:
        return math.nan

    return min(valid_distances)
