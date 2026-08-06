"""목표를 보내기 전에 실제 costmap 에서 현관까지 경로가 있는지 확인한다.

목표를 그냥 보내면 Nav2 가 복구 행동을 반복하다 20초 뒤 ABORTED 로 끝나고,
로그를 읽지 않으면 "출발 지점이 막혔다"인지 "목표가 막혔다"인지 구분되지
않는다. 2026-08-07 실기에서 로봇을 벽 근처에 세운 탓에 이 상황을 네 번
겪었다. 그래서 보내기 전에 같은 판정을 여기서 먼저 한다.

정적 지도가 아니라 **실제 global costmap** 을 본다. 라이다가 지금 보고 있는
장애물과 inflation 이 반영된 값이라야 planner 와 같은 결론이 나온다.

종료 코드: 0 경로 있음 / 1 경로 없음(사유 출력) / 2 데이터 부족
"""
import math
import sys
import time
from collections import deque

import rclpy
import yaml
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

# costmap 토픽은 0~100 으로 스케일된 값을 싣는다. 99 이상은 로봇 반경 안에
# 장애물이 있다는 뜻(inscribed obstacle)이라 planner 가 통과하지 못한다.
BLOCKED = 99
WAIT_SEC = 30.0


def _load_entrance(waypoint_file: str) -> dict:
    config = yaml.safe_load(open(waypoint_file, encoding="utf-8"))
    for waypoint in config["waypoints"]:
        if waypoint["name"] == "entrance":
            return waypoint
    raise KeyError("room_waypoints.yaml 에 entrance 가 없습니다")


def main() -> int:
    """출발 위치에서 현관까지 costmap 상 경로가 있는지 판정한다."""
    if len(sys.argv) < 2:
        print("사용법: precheck_path.py <room_waypoints.yaml>", file=sys.stderr)
        return 2
    entrance = _load_entrance(sys.argv[1])

    rclpy.init()
    node = Node("precheck_path")
    buffer = Buffer()
    TransformListener(buffer, node)
    received: dict = {}
    qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    node.create_subscription(
        OccupancyGrid,
        "/global_costmap/costmap",
        lambda msg: received.setdefault("map", msg),
        qos,
    )

    pose = None
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline and (pose is None or "map" not in received):
        rclpy.spin_once(node, timeout_sec=0.3)
        if pose is None:
            try:
                pose = buffer.lookup_transform("map", "base_link", Time())
            except Exception:
                pass

    if pose is None or "map" not in received:
        print("  검증 불가: costmap 또는 map->base_link 를 받지 못했습니다")
        node.destroy_node()
        rclpy.shutdown()
        return 2

    grid = received["map"]
    width = grid.info.width
    height = grid.info.height
    res = grid.info.resolution
    ox = grid.info.origin.position.x
    oy = grid.info.origin.position.y
    cells = grid.data
    start = pose.transform.translation

    def passable(row: int, col: int) -> bool:
        if not (0 <= row < height and 0 <= col < width):
            return False
        return 0 <= cells[row * width + col] < BLOCKED

    def to_cell(x: float, y: float) -> tuple:
        return (int((y - oy) / res), int((x - ox) / res))

    start_cell = to_cell(start.x, start.y)
    goal_cell = to_cell(entrance["x"], entrance["y"])
    start_cost = cells[start_cell[0] * width + start_cell[1]]
    goal_cost = cells[goal_cell[0] * width + goal_cell[1]]
    print("  출발 (%.2f, %.2f) cost=%d / 현관 (%.2f, %.2f) cost=%d"
          % (start.x, start.y, start_cost,
             entrance["x"], entrance["y"], goal_cost))

    if not passable(*start_cell):
        print("  ❌ 출발 지점이 막혀 있습니다(로봇이 벽·가구에 너무 가까움).")
        print("     로봇을 벽에서 40cm 이상 떨어진 트인 곳으로 옮기고 다시 실행하세요.")
        node.destroy_node()
        rclpy.shutdown()
        return 1

    if not passable(*goal_cell):
        print("  ❌ 현관 좌표가 막혀 있습니다. 현관 좌표를 다시 실측하세요.")
        node.destroy_node()
        rclpy.shutdown()
        return 1

    seen = {start_cell}
    queue = deque([start_cell])
    reached = False
    while queue:
        row, col = queue.popleft()
        if (row, col) == goal_cell:
            reached = True
            break
        for drow, dcol in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (row + drow, col + dcol)
            if passable(*nxt) and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)

    distance = math.hypot(start.x - entrance["x"], start.y - entrance["y"])
    if reached:
        print("  ✅ 경로 있음 (직선거리 %.2fm)" % distance)
    else:
        print("  ❌ 현관까지 경로가 없습니다(직선거리 %.2fm)." % distance)
        print("     통로가 막혔거나 지도에 안 그려진 구간이 가로막고 있습니다.")
        print("     그 구간을 왕복하며 다시 매핑하거나 장애물을 치우세요.")

    node.destroy_node()
    rclpy.shutdown()
    return 0 if reached else 1


if __name__ == "__main__":
    sys.exit(main())
