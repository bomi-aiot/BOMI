"""실제 MQTT 브로커를 거치는 브릿지 E2E 테스트다.

백엔드 역할을 하는 클라이언트가 명령을 발행하고, 브릿지 러너가 이를 받아
처리한 뒤 결과를 발행하면, 그 결과를 브로커에서 다시 수신해 검증한다.
명령 해석·주행(Mock)·결과 발행 전 구간이 진짜 브로커를 통해 왕복한다.

브로커가 없으면 테스트를 건너뛴다. 로컬 실행 시 mosquitto(또는 임의 MQTT
브로커)를 ``localhost:1883`` 에 띄운다. 호스트/포트는 ``TEST_BROKER_HOST`` /
``TEST_BROKER_PORT`` 환경변수로 바꿀 수 있다.
"""

import json
import os
import socket
import time

from bridge import contract
from bridge.mqtt_client import MqttBridgeRunner
import paho.mqtt.client as mqtt
import pytest

BROKER_HOST = os.environ.get("TEST_BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("TEST_BROKER_PORT", "1883"))
ROBOT_ID = "robot-01"


def _broker_available() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _broker_available(),
    reason=f"MQTT 브로커가 {BROKER_HOST}:{BROKER_PORT}에 없어 건너뜁니다",
)


def _command(command_type: str, **payload) -> str:
    return json.dumps(
        {
            "commandId": "cmd-e2e-1",
            "scenarioId": "scenario-e2e-7",
            "robotId": ROBOT_ID,
            "type": command_type,
            "occurredAt": "2026-07-28T10:00:00+09:00",
            "expiresAt": "2026-07-28T10:02:00+09:00",
            "payload": payload,
        }
    )


def _make_backend_client(received: list) -> mqtt.Client:
    client = mqtt.Client(
        client_id="test-backend",
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.on_message = lambda c, u, m: received.append(m.payload)
    client.connect(BROKER_HOST, BROKER_PORT)
    client.subscribe(contract.robot_results_topic(ROBOT_ID), qos=1)
    client.loop_start()
    return client


def _wait_for(received: list, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if received:
            return received[0]
        time.sleep(0.05)
    return None


def test_navigate_command_round_trips_over_real_broker() -> None:
    received: list = []
    runner = MqttBridgeRunner(ROBOT_ID, BROKER_HOST, BROKER_PORT)
    backend = _make_backend_client(received)

    try:
        runner.connect_and_loop_start()
        time.sleep(0.3)  # 구독이 자리잡을 시간

        backend.publish(
            contract.robot_commands_topic(ROBOT_ID),
            _command(contract.CMD_NAVIGATE, target=contract.TARGET_ENTRANCE),
            qos=1,
        )

        payload = _wait_for(received)
    finally:
        runner.stop()
        backend.loop_stop()
        backend.disconnect()

    assert payload is not None, "브릿지가 결과를 발행하지 않았습니다"
    envelope = json.loads(payload)
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["robotId"] == ROBOT_ID
    assert envelope["payload"]["scenarioId"] == "scenario-e2e-7"  # echo-back
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED
