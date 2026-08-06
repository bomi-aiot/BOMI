"""이벤트 하나를 받아 로컬 상태에 반영하고 백엔드로 올린다.

이 모듈이 그래프 밖에 있는 이유
    문 이벤트의 효과는 두 군데에 남아야 한다.
        내구 저장소(runtime_state)  침묵 사다리와 현관 감시 틱이 읽는다. 재부팅을 넘어
                                    살아남고, 그래프를 돌리지 않아도 최신이어야 한다.
        그래프 checkpoint            대화 턴이 읽는 값. graph.ingress.door_event 가 쓴다.

    두 곳에 쓰는 것은 중복이 아니라 서로 다른 수명이다. silence_tick 은 그래프를 거치지
    않고 runtime_store 를 읽기 때문에(jobs/ticks.py), 여기에 쓰지 않으면 문 이벤트가
    안전 감시에 영원히 도달하지 못한다.

    같은 판정이 두 곳에 생기는 것을 막기 위해 규칙 자체는 door.occupancy 한 곳에만 둔다.
    이 모듈과 graph.ingress.door_event 는 둘 다 그 함수를 부른다.

참고
    CLAUDE.md §11 (현관과 재실), §10 (사다리가 읽는 값), §18 (오프라인)
"""

from __future__ import annotations

import logging

from bomi_ai_chat.contracts.door import DoorEvent
from bomi_ai_chat.door import occupancy as occupancy_rules
from bomi_ai_chat.localstore import runtime as runtime_store

logger = logging.getLogger(__name__)


def ingest(
    senior_id: str,
    event: DoorEvent,
    *,
    door_client=None,
) -> dict[str, object]:
    """문 이벤트 하나를 처리한다. 예외를 던지지 않는다.

    무엇을 하는가  (이 순서가 중요하다)
        1. 하트비트를 찍는다. **어떤 메시지든** 라즈베리파이가 살아있다는 증거다.
        2. 문 개폐 상태를 갱신한다. door_open_since.
        3. 보수적 재실 상태를 반영한다. door.occupancy 의 규칙을 그대로 쓴다.
        4. 백엔드로 올린다. 실패해도 1~3 은 이미 끝나 있다.

    왜 하트비트가 HEARTBEAT 타입만이 아닌가  ★
        문 이벤트가 도착했다는 것 자체가 그 기기가 살아있다는 뜻이다. HEARTBEAT 타입만
        인정하면, 문은 부지런히 열리는데 하트비트 발행만 죽은 라즈베리파이에서
        occupancy 가 UNKNOWN 으로 강등된다. 살아있는 증거를 무시하는 셈이다.

    왜 event.direction 을 보고 HOME/AWAY 로 올리지 않는가  ★ 의도된 결정
        방향의 권위는 백엔드다 (CLAUDE.md §11). 센서 토픽으로 들어온 direction 은
        펌웨어가 스스로 판정한 값일 수 있고, 그것을 믿기 시작하면 방향 판정이 로봇에도
        생긴 것이다. 확정 재실 상태가 들어오는 경로는 딱 하나여야 한다 —
        door.occupancy.apply_backend_occupancy.

        그래도 값은 로그로 남기고 백엔드에 그대로 전달한다. 펌웨어가 방향을 붙이기
        시작했다는 사실은 계약 변경이므로 눈에 보여야 한다 (§24 미결 항목).

    인자
        door_client: 백엔드 전달 어댑터. None 이면 전달을 건너뛴다. 테스트와,
            브로커만 붙여 로컬 동작을 확인할 때 쓴다.

    반환값
        실제로 바뀐 필드 + {"forwarded": bool}. 로깅과 테스트용이다.
    """
    changes: dict[str, object] = {}

    # 1. 하트비트. 이벤트가 왔다는 것 자체가 생존 증거다.
    runtime_store.save(senior_id, door_heartbeat_at=event.received_at)
    changes["door_heartbeat_at"] = event.received_at

    # 2. 문 개폐.
    if event.type == "DOOR_OPENED":
        runtime_store.save(senior_id, door_open_since=event.received_at)
        changes["door_open_since"] = event.received_at
    elif event.type == "DOOR_CLOSED":
        runtime_store.save(senior_id, door_open_since=0.0)
        changes["door_open_since"] = 0.0

    # 3. 보수적 재실 상태.
    local = occupancy_rules.local_occupancy_for(event.type)
    if local is not None:
        changes.update(
            occupancy_rules.set_occupancy(
                senior_id, local, observed_at=event.received_at, source="sensor"
            )
        )

    if event.direction is not None:
        # 계약이 바뀌었다는 신호다. 값을 쓰지는 않는다(위 docstring 참고).
        logger.info(
            "door event %s carries direction=%s from the sensor topic; "
            "the robot does not act on it (the backend owns direction, CLAUDE.md §11)",
            event.type, event.direction,
        )

    # 4. 전달. 여기서 실패하는 것은 인사를 잃는 것이고, 안전 감시를 잃는 것이 아니다.
    forwarded = False
    if door_client is not None:
        forwarded = door_client.forward_event(senior_id, event)
    changes["forwarded"] = forwarded

    logger.info(
        "door event %s from %s (skew=%s) -> %s",
        event.type,
        event.source_id or "?",
        "?" if event.clock_skew_sec is None else f"{event.clock_skew_sec:.0f}s",
        changes.get("occupancy", "occupancy unchanged"),
    )
    return changes
