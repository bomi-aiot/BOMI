"""플래너가 실제로 보는 global costmap을 그림으로 떠서 저장한다.

왜 필요한가: 사람 눈에 보이는 빈 바닥과 플래너가 보는 지도는 다르다.
global costmap은 저장된 정적 지도에 LiDAR 실시간 장애물 레이어를 얹은
것이고, 거기에 로봇 반경(robot_radius)과 팽창 반경(inflation_radius)이
더해진다. 로봇 중심은 모든 물체에서 robot_radius 이상 떨어져야 하므로,
방에 사람이 한 명 서 있기만 해도 그 주위에 지름 0.6 m 이상의 금지 원이
생긴다. 2.7 m x 2.2 m 방에서는 그것만으로 통로가 닫힌다.

2026-08-07 실기에서 "눈으로는 충분히 넓은데 경로를 못 만든다"는 상황이
났고, 저장된 정적 지도만 봐서는 원인을 알 수 없었다. 정적 지도에서는
목표와 출발 모두 여유가 넉넉했기 때문이다.

쓰는 법 (Nav2가 떠 있는 상태에서):

    python3 costmap_snapshot.py [출력경로]

출력은 PNG 한 장이다. 색은 다음과 같다.

    검정   치명(로봇 중심이 들어갈 수 없음)
    빨강   팽창 구역(들어갈 수는 있으나 비용이 큼)
    회색   미탐색
    흰색   자유

로봇의 현재 위치를 파란 십자로, 목표 웨이포인트를 초록 십자로 찍는다.
경로를 못 만들 때 이 그림에서 둘 사이가 검정으로 끊겨 있는지 보면 된다.
"""
import math
import sys
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from PIL import Image
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from tf2_ros import Buffer, TransformListener

# Nav2 코스트맵 값. 100은 치명, 99는 팽창된 치명, -1은 미탐색이다.
LETHAL = 100
INSCRIBED = 99
UNKNOWN = -1


def _color(value: int) -> tuple[int, int, int]:
    """코스트맵 한 칸을 사람이 구분할 수 있는 색으로 바꾼다."""
    if value == UNKNOWN:
        return (170, 170, 170)
    if value >= LETHAL:
        return (0, 0, 0)
    if value >= INSCRIBED:
        return (60, 60, 60)
    if value > 0:
        # 팽창 구역. 비용이 클수록 진한 빨강.
        shade = int(255 - min(value, 98) * 1.6)
        return (255, shade, shade)
    return (255, 255, 255)


def main() -> int:
    """global costmap과 로봇 위치를 받아 PNG로 저장한다."""
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/costmap.png"

    rclpy.init()
    node = Node("costmap_snapshot")
    buffer = Buffer()
    TransformListener(buffer, node)

    grid: list[OccupancyGrid] = []

    # 코스트맵은 transient local로 한 번만 보내므로 QoS를 맞춰야 받는다.
    qos = QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=1,
    )
    node.create_subscription(
        OccupancyGrid, "/global_costmap/costmap", grid.append, qos
    )

    deadline = time.time() + 15.0
    while time.time() < deadline and not grid:
        rclpy.spin_once(node, timeout_sec=0.2)

    if not grid:
        print("global costmap을 받지 못했습니다. Nav2가 떠 있는지 확인하세요.")
        node.destroy_node()
        rclpy.shutdown()
        return 1

    msg = grid[-1]
    w, h = msg.info.width, msg.info.height
    res = msg.info.resolution
    ox = msg.info.origin.position.x
    oy = msg.info.origin.position.y

    image = Image.new("RGB", (w, h), (255, 255, 255))
    px = image.load()
    counts = {"자유": 0, "팽창": 0, "치명": 0, "미탐색": 0}

    for y in range(h):
        for x in range(w):
            value = msg.data[y * w + x]
            # OccupancyGrid는 아래에서 위로 쌓이므로 이미지에서 뒤집는다.
            px[x, h - 1 - y] = _color(value)

            if value == UNKNOWN:
                counts["미탐색"] += 1
            elif value >= INSCRIBED:
                counts["치명"] += 1
            elif value > 0:
                counts["팽창"] += 1
            else:
                counts["자유"] += 1

    def mark(xm: float, ym: float, color: tuple[int, int, int]) -> None:
        """맵 좌표에 십자를 찍는다."""
        cx = int((xm - ox) / res)
        cy = h - 1 - int((ym - oy) / res)
        for d in range(-3, 4):
            for p in ((cx + d, cy), (cx, cy + d)):
                if 0 <= p[0] < w and 0 <= p[1] < h:
                    px[p[0], p[1]] = color

    robot = None
    try:
        transform = buffer.lookup_transform(
            "map", "base_link", rclpy.time.Time()
        )
        robot = (
            transform.transform.translation.x,
            transform.transform.translation.y,
        )
        mark(robot[0], robot[1], (0, 90, 255))
    except Exception:
        print("로봇 위치를 읽지 못했습니다(파란 십자 생략).")

    total = w * h
    print(f"코스트맵 {w}x{h} = {w*res:.2f} x {h*res:.2f} m, 해상도 {res} m")
    for key, value in counts.items():
        print(f"  {key:4s} {value:6d} 칸 ({value / total * 100:5.1f}%)")
    if robot:
        print(f"  로봇 위치 ({robot[0]:+.3f}, {robot[1]:+.3f}) 파란 십자")

    scale = max(1, 600 // max(w, h))
    image.resize((w * scale, h * scale), Image.NEAREST).save(out)
    print(f"\n저장: {out}")

    node.destroy_node()
    rclpy.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
