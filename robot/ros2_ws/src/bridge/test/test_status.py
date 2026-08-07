"""브릿지의 status 토픽 발행(REST_STATE_CHANGED/NAVIGATION_STATUS)을 검증한다."""

import json

from bridge import contract
from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver


class _Collector:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __call__(self, topic: str, payload: str) -> None:
        self.messages.append((topic, payload))


def _make_bridge(robot_id: str = "robot-01"):
    collector = _Collector()
    return MqttBridge(robot_id, MockRobotDriver(), collector), collector


def test_publish_rest_state_matches_backend_contract() -> None:
    bridge, collector = _make_bridge()

    bridge.publish_rest_state(contract.REST_STATE_RESTING)

    assert len(collector.messages) == 1
    topic, payload = collector.messages[0]
    assert topic == "bomi/v1/robot/robot-01/status"

    envelope = json.loads(payload)
    assert envelope["type"] == contract.STATUS_TYPE_REST_STATE_CHANGED
    assert envelope["robotId"] == "robot-01"
    assert envelope["eventId"]
    assert envelope["occurredAt"]
    # 백엔드 ObservationContract가 읽는 키
    assert envelope["payload"][contract.REST_STATE_KEY] == contract.REST_STATE_RESTING


def test_publish_navigation_status_carries_detail() -> None:
    bridge, collector = _make_bridge()

    bridge.publish_navigation_status({"phase": "MOVING", "progress": 42})

    topic, payload = collector.messages[0]
    assert topic == "bomi/v1/robot/robot-01/status"
    envelope = json.loads(payload)
    assert envelope["type"] == contract.STATUS_TYPE_NAVIGATION
    assert envelope["payload"]["phase"] == "MOVING"
    assert envelope["payload"]["progress"] == 42


def test_awake_rest_state_round_trips() -> None:
    bridge, collector = _make_bridge()

    bridge.publish_rest_state(contract.REST_STATE_AWAKE)

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"][contract.REST_STATE_KEY] == contract.REST_STATE_AWAKE
