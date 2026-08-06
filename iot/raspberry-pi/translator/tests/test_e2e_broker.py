"""실제 MQTT 브로커를 거치는 번역기 E2E 테스트다.

가짜 Zigbee 발행 → 번역기 구독·변환·발행 → 가짜 '백엔드' 수신 순으로 진짜
브로커를 왕복한다. 순수 단위 테스트가 못 잡는 paho 연결·구독·발행 전 구간을
검증한다.

브로커가 없으면 건너뛴다. 로컬 실행 시 mosquitto 를 localhost:1883 에 띄운다.
호스트/포트는 TEST_BROKER_HOST / TEST_BROKER_PORT 환경변수로 바꿀 수 있다.
"""

import json
import os
import socket
import time

import paho.mqtt.client as mqtt
import pytest

from translator import Translator

HOST = os.environ.get("TEST_BROKER_HOST", "localhost")
PORT = int(os.environ.get("TEST_BROKER_PORT", "1883"))


def _broker_available() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _broker_available(),
    reason=f"MQTT 브로커가 {HOST}:{PORT}에 없어 건너뜁니다",
)

CONFIG = {
    "topics": {"zigbee2mqtt_base": "zigbee2mqtt", "contract_prefix": "bomi/v1"},
    "sensors": [
        {"friendly_name": "door-sensor-01", "source_id": "door-sensor-01",
         "kind": "door", "location": "ENTRANCE"},
    ],
}


def _client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.connect(HOST, PORT)
    client.loop_start()
    return client


def _wait_for(received: list, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if received:
            return received[0]
        time.sleep(0.05)
    return None


def test_door_open_round_trips_over_real_broker() -> None:
    received: list = []

    # 1) 가짜 백엔드: 계약 이벤트 토픽 구독
    backend = _client("test-backend")
    backend.on_message = lambda c, u, m: received.append((m.topic, m.payload))
    backend.subscribe("bomi/v1/iot/+/events", qos=1)

    # 2) 번역기: zigbee2mqtt 구독 → 변환 → 브로커로 발행
    tclient = _client("test-translator")
    translator = Translator(
        CONFIG, lambda topic, payload: tclient.publish(topic, payload, qos=1, retain=False)
    )
    tclient.on_message = lambda c, u, m: translator.on_zigbee_message(
        m.topic, m.payload, retained=m.retain
    )
    tclient.subscribe("zigbee2mqtt/#", qos=1)

    time.sleep(0.3)  # 구독이 브로커에 반영될 시간

    # 3) 가짜 Zigbee 발행: 닫힘 → 열림 (열림 전이에서만 DOOR_OPENED)
    pub = _client("test-zigbee")
    pub.publish("zigbee2mqtt/door-sensor-01", json.dumps({"contact": True}), qos=1)
    time.sleep(0.2)
    pub.publish("zigbee2mqtt/door-sensor-01", json.dumps({"contact": False}), qos=1)

    # 4) 검증: DOOR_OPENED 가 계약 형식대로 도착
    result = _wait_for(received)
    try:
        assert result is not None, "계약 이벤트를 수신하지 못했습니다"
        topic, payload = result
        assert topic == "bomi/v1/iot/door-sensor-01/events"
        event = json.loads(payload)
        assert event["type"] == "DOOR_OPENED"
        assert event["sourceId"] == "door-sensor-01"
        assert event["payload"] == {"location": "ENTRANCE"}
        assert event["occurredAt"].endswith("+09:00")
        assert event["eventId"]
    finally:
        for c in (backend, tclient, pub):
            c.loop_stop()
            c.disconnect()
