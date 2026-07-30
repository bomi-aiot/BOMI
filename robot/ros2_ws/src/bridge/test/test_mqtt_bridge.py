"""브릿지 코어(mqtt_bridge.py)의 명령 처리와 결과 발행을 검증하는 단위 테스트다.

발행은 리스트 수집기로 주입하고 주행은 MockRobotDriver로 대체하므로,
브로커나 ROS 2 없이 명령→결과 왕복 전체를 검증한다.
"""

import json

from bridge import contract
from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver
import pytest


class _Collector:
    """발행된 (topic, payload)를 모아두는 테스트용 publish 콜백이다."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __call__(self, topic: str, payload: str) -> None:
        self.messages.append((topic, payload))


def _make_bridge(robot_id: str = "robot-01"):
    collector = _Collector()
    bridge = MqttBridge(robot_id, MockRobotDriver(), collector)
    return bridge, collector


def _command_json(command_type: str, robot_id: str = "robot-01", **payload) -> str:
    return json.dumps(
        {
            "commandId": "cmd-1",
            "scenarioId": "scenario-42",
            "robotId": robot_id,
            "type": command_type,
            "occurredAt": "2026-07-28T10:00:00+09:00",
            "expiresAt": "2026-07-28T10:02:00+09:00",
            "payload": payload,
        }
    )


def test_navigate_command_publishes_navigation_result_with_echoed_scenario_id() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(
        _command_json(contract.CMD_NAVIGATE, target=contract.TARGET_ENTRANCE)
    )

    assert len(collector.messages) == 1
    topic, payload = collector.messages[0]
    assert topic == "bomi/v1/robot/robot-01/results"

    envelope = json.loads(payload)
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["robotId"] == "robot-01"
    assert envelope["payload"]["scenarioId"] == "scenario-42"  # echo-back
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED


def test_speak_command_publishes_speak_result() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_SPEAK, text="어서 오세요"))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_SPEAK
    assert envelope["payload"]["status"] == contract.STATUS_DONE


def test_cancel_command_publishes_cancel_result() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_CANCEL))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_CANCEL
    assert envelope["payload"]["status"] == contract.STATUS_CANCELLED


def test_navigate_without_target_reports_failed() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE))  # target 없음

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_FAILED


def test_command_for_other_robot_is_ignored() -> None:
    bridge, collector = _make_bridge(robot_id="robot-01")

    bridge.on_command(
        _command_json(contract.CMD_NAVIGATE, robot_id="robot-99", target="ENTRANCE")
    )

    assert collector.messages == []


def test_contract_violation_is_dropped_without_publishing() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command("not a valid json")

    assert collector.messages == []


@pytest.mark.parametrize(
    "target", [contract.TARGET_ENTRANCE, contract.TARGET_DEFAULT]
)
def test_homecoming_targets_round_trip(target: str) -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE, target=target))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED
