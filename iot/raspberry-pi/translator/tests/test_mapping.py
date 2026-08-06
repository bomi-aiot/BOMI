"""매핑 로직(mapping.py)의 엣지 트리거·retained 무시를 검증하는 단위 테스트다."""

from datetime import datetime

import contract
import mapping


DOOR = {"kind": "door", "source_id": "door-sensor-01", "location": "ENTRANCE"}
PIR = {"kind": "pir", "source_id": "entrance-sensor-hub-01", "location": "ENTRANCE"}


def _now():
    return datetime(2026, 7, 30, 21, 15, 0, tzinfo=contract.KST)


# --- 문(contact) --------------------------------------------------------------

def test_door_open_edge_emits_door_opened() -> None:
    # 닫힘(True) 상태에서 열림(False) 으로 전이 → DOOR_OPENED
    event, prev = mapping.map_message(DOOR, {"contact": False}, {"contact": True}, now=_now)
    assert event is not None
    assert event["type"] == "DOOR_OPENED"
    assert event["sourceId"] == "door-sensor-01"
    assert event["payload"] == {"location": "ENTRANCE"}
    assert prev["contact"] is False


def test_door_first_fresh_open_emits() -> None:
    # 최초 상태(prev 없음)에서 fresh 열림 메시지 → 발행
    event, _ = mapping.map_message(DOOR, {"contact": False}, None, now=_now)
    assert event is not None
    assert event["type"] == "DOOR_OPENED"


def test_door_first_fresh_closed_establishes_state_without_emit() -> None:
    event, prev = mapping.map_message(DOOR, {"contact": True}, None, now=_now)
    assert event is None
    assert prev["contact"] is True


def test_door_repeated_open_does_not_emit() -> None:
    # 이미 열림 상태에서 같은 열림 메시지 반복 → 발행 안 함
    event, _ = mapping.map_message(DOOR, {"contact": False}, {"contact": False}, now=_now)
    assert event is None


def test_door_close_emits_door_closed() -> None:
    event, prev = mapping.map_message(DOOR, {"contact": True}, {"contact": False}, now=_now)
    assert event is not None
    assert event["type"] == "DOOR_CLOSED"
    assert event["payload"] == {"location": "ENTRANCE"}
    assert prev["contact"] is True


def test_door_retained_message_updates_state_but_no_emit() -> None:
    # retained 로 들어온 현재 상태(열림) → 상태만 갱신, 발행 안 함
    event, prev = mapping.map_message(
        DOOR, {"contact": False}, None, retained=True, now=_now
    )
    assert event is None
    assert prev["contact"] is False


def test_door_retained_then_real_open_emits() -> None:
    # retained 로 '열림'을 받았다가 닫혔다 다시 열리면 그때는 발행
    _, prev = mapping.map_message(DOOR, {"contact": False}, None, retained=True, now=_now)
    _, prev = mapping.map_message(DOOR, {"contact": True}, prev, now=_now)   # 닫힘
    event, _ = mapping.map_message(DOOR, {"contact": False}, prev, now=_now)  # 열림
    assert event is not None
    assert event["type"] == "DOOR_OPENED"


def test_battery_only_message_ignored() -> None:
    # contact 키 없는 메시지(배터리 등) → 무시, 상태 보존
    event, prev = mapping.map_message(
        DOOR, {"battery": 87, "linkquality": 120}, {"contact": False}, now=_now
    )
    assert event is None
    assert prev == {"contact": False}


# --- PIR(occupancy) -----------------------------------------------------------

def test_pir_occupancy_edge_emits_motion_detected() -> None:
    event, prev = mapping.map_message(PIR, {"occupancy": True}, {"occupancy": False}, now=_now)
    assert event is not None
    assert event["type"] == "MOTION_DETECTED"
    assert event["sourceId"] == "entrance-sensor-hub-01"
    assert event["payload"] == {"location": "ENTRANCE"}
    assert prev["occupancy"] is True


def test_pir_clear_does_not_emit() -> None:
    event, _ = mapping.map_message(PIR, {"occupancy": False}, {"occupancy": True}, now=_now)
    assert event is None


def test_unknown_kind_ignored() -> None:
    event, prev = mapping.map_message(
        {"kind": "smoke", "source_id": "x", "location": "Y"},
        {"smoke": True}, None, now=_now,
    )
    assert event is None
