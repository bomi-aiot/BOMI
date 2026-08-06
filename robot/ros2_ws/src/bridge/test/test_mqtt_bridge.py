"""브릿지 코어(mqtt_bridge.py)의 명령 처리와 결과 발행을 검증하는 단위 테스트다.

발행은 리스트 수집기로 주입하고 주행은 MockRobotDriver로 대체하므로,
브로커나 ROS 2 없이 명령→결과 왕복 전체를 검증한다.
"""

from datetime import datetime, timezone
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


TEST_NOW = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)


def _make_bridge(
    robot_id: str = "robot-01",
    *,
    driver=None,
    submit_navigation=None,
):
    collector = _Collector()
    bridge = MqttBridge(
        robot_id,
        driver or MockRobotDriver(),
        collector,
        submit_navigation=submit_navigation,
        now=lambda: TEST_NOW,
    )
    return bridge, collector


def _command_json(
    command_type: str,
    robot_id: str = "robot-01",
    *,
    command_id: str = "cmd-1",
    expires_at: str = "2026-07-28T10:02:00+09:00",
    **payload,
) -> str:
    return json.dumps(
        {
            "commandId": command_id,
            "scenarioId": "scenario-42",
            "robotId": robot_id,
            "type": command_type,
            "occurredAt": "2026-07-28T10:00:00+09:00",
            "expiresAt": expires_at,
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


@pytest.mark.parametrize(
    "command_type", [contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP]
)
def test_follow_commands_do_not_start_navigation(command_type: str) -> None:
    driver = _RecordingDriver()
    bridge, collector = _make_bridge(driver=driver)

    bridge.on_command(_command_json(command_type))

    assert driver.navigate_targets == []
    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_FOLLOW
    assert envelope["payload"]["status"] == contract.STATUS_FAILED


def test_navigate_without_target_reports_failed() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE))  # target 없음

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_FAILED


@pytest.mark.parametrize("target", ["BEDROOM", "KITCHEN", "", None])
def test_unknown_target_does_not_move_and_reports_failed(target) -> None:
    driver = _RecordingDriver()
    bridge, collector = _make_bridge(driver=driver)

    bridge.on_command(_command_json(contract.CMD_NAVIGATE, target=target))

    assert driver.navigate_targets == []
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
    "target",
    [
        contract.TARGET_ENTRANCE,
        contract.TARGET_DEFAULT,
        contract.TARGET_LIVING_ROOM,
    ],
)
def test_homecoming_targets_round_trip(target: str) -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE, target=target))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED


def test_expired_navigate_does_not_move_and_reports_failed() -> None:
    driver = _RecordingDriver()
    bridge, collector = _make_bridge(driver=driver)

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE,
            expires_at="2026-07-28T09:59:59+09:00",
            target=contract.TARGET_ENTRANCE,
        )
    )

    assert driver.navigate_targets == []
    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_FAILED


def test_duplicate_command_id_moves_only_once() -> None:
    driver = _RecordingDriver()
    bridge, collector = _make_bridge(driver=driver)
    command = _command_json(
        contract.CMD_NAVIGATE,
        target=contract.TARGET_ENTRANCE,
    )

    bridge.on_command(command)
    bridge.on_command(command)

    assert driver.navigate_targets == [contract.TARGET_ENTRANCE]
    assert len(collector.messages) == 1


def test_navigation_result_waits_for_submitted_task() -> None:
    pending: list = []

    def submit(task) -> bool:
        pending.append(task)
        return True

    bridge, collector = _make_bridge(submit_navigation=submit)
    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE,
            target=contract.TARGET_LIVING_ROOM,
        )
    )

    assert collector.messages == []
    pending[0]()

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["scenarioId"] == "scenario-42"
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED


def test_busy_navigation_is_rejected_without_driver_call() -> None:
    driver = _RecordingDriver()
    bridge, collector = _make_bridge(
        driver=driver,
        submit_navigation=lambda task: False,
    )

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE,
            target=contract.TARGET_ENTRANCE,
        )
    )

    assert driver.navigate_targets == []
    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["status"] == contract.STATUS_FAILED


class _RecordingDriver(MockRobotDriver):
    """실제 이동 대신 호출된 목적지와 취소 횟수를 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.navigate_targets: list[str] = []

    def navigate(self, target: str) -> str:
        self.navigate_targets.append(target)
        return contract.STATUS_ARRIVED
