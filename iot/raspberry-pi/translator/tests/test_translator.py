"""번역기 코어(translator.py)를 브로커 없이 검증하는 단위 테스트다.

발행은 리스트 수집기로 주입해, 어떤 Zigbee 메시지가 어떤 계약 이벤트를 어느
토픽으로 내는지 확인한다."""

import json

from translator import Translator


CONFIG = {
    "topics": {"zigbee2mqtt_base": "zigbee2mqtt", "contract_prefix": "bomi/v1"},
    "sensors": [
        {"friendly_name": "door-sensor-01", "source_id": "door-sensor-01",
         "kind": "door", "location": "ENTRANCE"},
        {"friendly_name": "entrance-pir-01", "source_id": "entrance-sensor-hub-01",
         "kind": "pir", "location": "ENTRANCE"},
    ],
}


def _make():
    published = []
    t = Translator(CONFIG, lambda topic, payload: published.append((topic, payload)))
    return t, published


def test_subscribe_topic() -> None:
    t, _ = _make()
    assert t.subscribe_topic == "zigbee2mqtt/#"


def test_door_open_publishes_contract_event_on_correct_topic() -> None:
    t, published = _make()
    # 먼저 닫힘 상태 확립(발행 없음), 그다음 열림
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", json.dumps({"contact": True}))
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", json.dumps({"contact": False}))

    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "bomi/v1/iot/door-sensor-01/events"
    event = json.loads(payload)
    assert event["type"] == "DOOR_OPENED"
    assert event["sourceId"] == "door-sensor-01"


def test_door_close_publishes_door_closed() -> None:
    t, published = _make()
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", json.dumps({"contact": False}))
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", json.dumps({"contact": True}))

    assert [json.loads(payload)["type"] for _, payload in published] == [
        "DOOR_OPENED", "DOOR_CLOSED"
    ]


def test_retained_message_does_not_publish() -> None:
    t, published = _make()
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", json.dumps({"contact": False}), retained=True)
    assert published == []


def test_pir_maps_to_motion_on_hub_source_id() -> None:
    t, published = _make()
    t.on_zigbee_message("zigbee2mqtt/entrance-pir-01", json.dumps({"occupancy": True}))
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "bomi/v1/iot/entrance-sensor-hub-01/events"
    assert json.loads(payload)["type"] == "MOTION_DETECTED"


def test_unknown_sensor_ignored() -> None:
    t, published = _make()
    t.on_zigbee_message("zigbee2mqtt/some-other-device", json.dumps({"contact": False}))
    assert published == []


def test_non_json_payload_ignored() -> None:
    t, published = _make()
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01", b"not-json")
    assert published == []


def test_availability_subtopic_ignored() -> None:
    t, published = _make()
    # zigbee2mqtt/door-sensor-01/availability 같은 하위 토픽은 friendly_name 불일치로 무시
    t.on_zigbee_message("zigbee2mqtt/door-sensor-01/availability", "online")
    assert published == []
