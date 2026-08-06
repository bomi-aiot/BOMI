"""백엔드 목적지 이름을 room_waypoints.yaml 웨이포인트로 변환하는 순수 로직.

이 모듈은 ROS 2나 Nav2에 의존하지 않는다. 백엔드가 보내는 목적지 이름을
좌표가 담긴 웨이포인트로 바꾸는 규칙만 담당하므로, 실제 주행 없이 단위
테스트할 수 있다. 좌표 자체는 이 모듈에 하드코딩하지 않고 core 패키지의
room_waypoints.yaml을 단일 출처로 사용한다.
"""

from __future__ import annotations

from pathlib import Path

from bridge import contract
from core.waypoint_route import Waypoint, load_patrol_route

# 백엔드 목적지 이름 -> room_waypoints.yaml 웨이포인트 이름.
# 계약(contract)에 정의된 목적지만 여기에 명시적으로 나열한다. 문자열 대소문자
# 변환으로 임의 목적지를 자동 허용하지 않기 위해, 지원 목적지를 표로 직접
# 관리한다.
# v1 계약의 세 목적지를 전부 지원한다. LIVING_ROOM 은 보미야 호출·복약·온습도
# 시나리오의 목적지이고, DEFAULT 는 대화 종료 후 복귀 지점이다. 좌표 자체는
# room_waypoints.yaml 에 있으며 living_room/default 는 실측 전 임시값이다
# (해당 파일 주석 참고).
_SUPPORTED_TARGET_TO_WAYPOINT_NAME = {
    contract.TARGET_ENTRANCE: "entrance",
    contract.TARGET_LIVING_ROOM: "living_room",
    contract.TARGET_DEFAULT: "default",
}


def resolve_waypoint_name(target: str | None) -> str | None:
    """백엔드 목적지 이름을 웨이포인트 이름으로 변환한다.

    역할: NAVIGATE 명령의 target을 지원 목적지 표에서 찾아 웨이포인트 이름을
        돌려준다.
    입력값: target - 백엔드가 보낸 목적지 이름(예: "ENTRANCE"). None일 수 있다.
    반환값: 지원 목적지면 웨이포인트 이름(예: "entrance"), 아니면 None.
    주의: 지원하지 않는 목적지는 None을 돌려주며, 호출자는 이를 FAILED로
        처리해야 한다. 여기서 임의로 기본 목적지를 만들지 않는다.
    """
    if target is None:
        return None
    return _SUPPORTED_TARGET_TO_WAYPOINT_NAME.get(target)


def load_waypoint(waypoint_file: str | Path, waypoint_name: str) -> Waypoint:
    """room_waypoints.yaml에서 이름에 해당하는 웨이포인트를 읽는다.

    역할: core의 검증된 YAML 로더를 재사용해 좌표를 읽고, 이름이 일치하는
        웨이포인트를 돌려준다.
    입력값: waypoint_file - 웨이포인트 YAML 경로. waypoint_name - 찾을 이름.
    반환값: 좌표(x, y, yaw)를 담은 Waypoint.
    실패: 파일이 없거나 YAML이 잘못되면 core 로더가 예외를 던진다. 이름이
        목록에 없으면 KeyError를 던진다.
    """
    route = load_patrol_route(waypoint_file)
    for waypoint in route.waypoints:
        if waypoint.name == waypoint_name:
            return waypoint
    raise KeyError(waypoint_name)
