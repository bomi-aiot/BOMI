"""room_waypoints.yaml에서 웨이포인트 하나를 "x y yaw" 한 줄로 출력한다.

ROS 2에 의존하지 않는다. 셸 스크립트가 좌표를 읽어 쓰기 위한 최소 도구다.

왜 필요한가: bomi_goto.sh는 출발 좌표를 ~/.bomi_demo_state에서 읽는데, 그
파일은 젯슨 홈에만 있는 런타임 산출물이라 재부팅·브랜치 전환·초기화로
사라진다. 사라지면 2단계가 첫 줄에서 멈춘다. 2026-08-07에 실제로 그래서
손으로 복원해야 했다.

같은 좌표가 이미 저장소의 room_waypoints.yaml에 있으므로(charging =
DEFAULT = 대기 위치 = 매핑 출발 지점), 상태 파일이 없으면 그쪽에서
읽어오면 된다. 좌표를 두 곳에 적어두고 동기화하는 대신, 저장소를 단일
출처로 두고 상태 파일은 캐시로만 쓴다.

사용법:
    python3 read_waypoint.py <room_waypoints.yaml> <이름>
    → "-0.838 -1.136 3.130"
"""
import sys

import yaml


def main() -> int:
    """웨이포인트 좌표를 표준출력으로 내보낸다."""
    if len(sys.argv) < 3:
        print("사용법: read_waypoint.py <yaml> <이름>", file=sys.stderr)
        return 2

    path, name = sys.argv[1], sys.argv[2]

    try:
        with open(path, encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
    except OSError as error:
        print(f"웨이포인트 파일을 열 수 없습니다: {error}", file=sys.stderr)
        return 1
    except yaml.YAMLError as error:
        print(f"웨이포인트 YAML이 잘못됐습니다: {error}", file=sys.stderr)
        return 1

    waypoints = (document or {}).get("waypoints") or []

    for waypoint in waypoints:
        if waypoint.get("name") != name:
            continue

        try:
            x = float(waypoint["x"])
            y = float(waypoint["y"])
            yaw = float(waypoint["yaw"])
        except (KeyError, TypeError, ValueError):
            print(f"'{name}' 웨이포인트의 좌표가 잘못됐습니다", file=sys.stderr)
            return 1

        print(f"{x:.4f} {y:.4f} {yaw:.4f}")
        return 0

    available = ", ".join(str(w.get("name")) for w in waypoints) or "(없음)"
    print(
        f"'{name}' 웨이포인트가 없습니다. 있는 것: {available}",
        file=sys.stderr,
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())
