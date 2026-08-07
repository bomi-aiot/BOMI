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
# contract.TARGET_DEFAULT("DEFAULT")는 충전소 도킹 위치를 가리킨다. 그 좌표는
# 실측값이 아니라 지도 원점(0, 0, 0)으로 절차적으로 정의한다 — 재매핑 시
# 로봇을 충전소에 도킹한 채로 SLAM을 시작하면 원점이 곧 충전소가 된다.
# contract.TARGET_LIVING_ROOM("LIVING_ROOM")은 sofa를 가리킨다. 별도의
# living_room 웨이포인트를 두지 않는 이유는, 그 좌표가 sofa와 같은 지점이기
# 때문이다 — 시연 대본에서 어르신이 소파에 앉으므로 보미야 호출·복약·온습도
# 시나리오의 목적지가 곧 소파다. 같은 지점을 두 이름으로 두면 재매핑 때 한쪽만
# 갱신되어 조용히 어긋난다.
_SUPPORTED_TARGET_TO_WAYPOINT_NAME = {
    contract.TARGET_ENTRANCE: "entrance",
    contract.TARGET_LIVING_ROOM: "sofa",
    contract.TARGET_DEFAULT: "charging",
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
