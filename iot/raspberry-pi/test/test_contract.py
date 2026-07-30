"""계약 모듈(contract.py)의 토픽·봉투 생성을 검증하는 단위 테스트다."""

from datetime import datetime

import contract
import pytest


def _fixed_now():
    # 오프셋 포함 고정 시각(KST)
    return datetime(2026, 7, 30, 21, 15, 0, tzinfo=contract.KST)


def test_iot_events_topic_follows_convention() -> None:
    assert contract.iot_events_topic("door-sensor-01") == "bomi/v1/iot/door-sensor-01/events"


def test_iot_events_topic_rejects_unsafe_id() -> None:
    with pytest.raises(ValueError):
        contract.iot_events_topic("bad id/with space")


def test_build_event_has_required_envelope_fields() -> None:
    event = contract.build_event(
        "door-sensor-01",
        contract.TYPE_DOOR_OPENED,
        contract.door_opened_payload("ENTRANCE"),
        now=_fixed_now,
        event_id="fixed-event-id",
    )
    assert event == {
        "eventId": "fixed-event-id",
        "type": "DOOR_OPENED",
        "occurredAt": "2026-07-30T21:15:00+09:00",
        "sourceId": "door-sensor-01",
        "payload": {"location": "ENTRANCE"},
    }


def test_build_event_occurred_at_includes_offset() -> None:
    event = contract.build_event(
        "door-sensor-01", contract.TYPE_DOOR_OPENED, {}, now=_fixed_now
    )
    assert event["occurredAt"].endswith("+09:00")


def test_build_event_generates_opaque_event_id_when_absent() -> None:
    event = contract.build_event("door-sensor-01", contract.TYPE_DOOR_OPENED, {})
    assert event["eventId"]
    assert len(event["eventId"]) <= contract.MAX_OPAQUE_ID_LENGTH


def test_presence_payload_defaults_to_unknown_direction() -> None:
    payload = contract.presence_detected_payload("ENTRANCE")
    assert payload["direction"] == contract.DIRECTION_UNKNOWN
    assert payload["detectionMethod"] == contract.DETECTION_SENSOR_SEQUENCE
