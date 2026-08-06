"""브릿지 코어(mqtt_bridge.py)의 명령 처리와 결과 발행을 검증하는 단위 테스트다.

발행은 리스트 수집기로 주입하고 주행은 MockRobotDriver로 대체하므로,
브로커나 ROS 2 없이 명령→결과 왕복 전체를 검증한다.

v1 개편(2026-08)에서 추가된 것: 만료 거절, commandId 중복 제거, CANCEL 즉시
처리(비동기 실행 모드), 계약 위반 시 FAILED 회신. 전부 인수인계 필수 항목이다.
"""

from datetime import datetime, timezone
import json
import threading
import time

from bridge import contract
from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver
import pytest

# 명령의 occurredAt(10:00 KST)과 expiresAt(10:02 KST) 사이의 고정 시각.
# 브리지의 now() 를 여기 맞춰야 "만료 거절"이 테스트를 오염시키지 않는다.
_NOW = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)  # 10:00 KST


class _Collector:
    """발행된 (topic, payload)를 모아두는 테스트용 publish 콜백이다.

    여러 스레드(워커)에서 호출될 수 있으므로 락으로 보호한다.
    """

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def __call__(self, topic: str, payload: str) -> None:
        with self._lock:
            self.messages.append((topic, payload))


def _make_bridge(robot_id: str = "robot-01", *, driver=None, async_execution=False):
    collector = _Collector()
    bridge = MqttBridge(
        robot_id,
        driver or MockRobotDriver(),
        collector,
        async_execution=async_execution,
        now=lambda: _NOW,
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


def _wait_for(collector: _Collector, count: int, *, timeout: float = 2.0) -> None:
    """비동기 실행 모드에서 워커가 결과를 발행할 때까지 짧게 기다린다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(collector.messages) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"{timeout}초 안에 결과 {count}건이 발행되지 않았습니다")


# ── 기본 왕복 (v1 형식) ──────────────────────────────────────────────────────


def test_navigate_command_publishes_v1_navigation_result() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(
        _command_json(contract.CMD_NAVIGATE, target=contract.TARGET_LIVING_ROOM)
    )

    assert len(collector.messages) == 1
    topic, payload = collector.messages[0]
    assert topic == "bomi/v1/robot/robot-01/results"

    envelope = json.loads(payload)
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["robotId"] == "robot-01"
    # v1: 상관관계 ID 는 최상위 echo-back. payload 안에 있으면 안 된다.
    assert envelope["scenarioId"] == "scenario-42"
    assert envelope["commandId"] == "cmd-1"
    assert "scenarioId" not in envelope["payload"]
    assert envelope["payload"] == {
        "outcome": contract.OUTCOME_SUCCEEDED,
        "resultCode": contract.CODE_ARRIVED,
        "reasonCode": None,
    }


def test_speak_command_publishes_v1_speak_result() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_SPEAK, text="어서 오세요"))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_SPEAK
    assert envelope["payload"] == {
        "outcome": contract.OUTCOME_SUCCEEDED,
        "resultCode": contract.CODE_SPOKEN,
        "reasonCode": None,
    }


def test_cancel_command_publishes_v1_cancel_result() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_CANCEL))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_CANCEL
    assert envelope["payload"] == {
        "outcome": contract.OUTCOME_SUCCEEDED,
        "resultCode": contract.CODE_TARGET_CANCELLED,
        "reasonCode": None,
    }


def test_navigate_without_target_reports_failed_with_reason() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE))  # target 없음

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_FAILED
    assert envelope["payload"]["resultCode"] == contract.CODE_NOT_ARRIVED
    assert envelope["payload"]["reasonCode"] == contract.REASON_UNKNOWN_TARGET


def test_command_for_other_robot_is_ignored() -> None:
    bridge, collector = _make_bridge(robot_id="robot-01")

    bridge.on_command(
        _command_json(contract.CMD_NAVIGATE, robot_id="robot-99", target="ENTRANCE")
    )

    assert collector.messages == []


@pytest.mark.parametrize(
    "target",
    [contract.TARGET_ENTRANCE, contract.TARGET_LIVING_ROOM, contract.TARGET_DEFAULT],
)
def test_all_v1_targets_round_trip(target: str) -> None:
    """v1 계약의 세 목적지 전부 mock 드라이버로 왕복한다.

    ★ 이 테스트가 '아무 target 이나 mock 이 ARRIVED 를 준다'는 낡은 가정을
    깨는 지점이다 — 이제 mock 도 지원 목적지만 ARRIVED, 그 밖은 FAILED.
    """
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE, target=target))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_SUCCEEDED
    assert envelope["payload"]["resultCode"] == contract.CODE_ARRIVED


def test_unknown_target_reports_failed_even_on_mock_driver() -> None:
    """거짓 성공 제거: mock 드라이버도 모르는 target 은 FAILED."""
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(contract.CMD_NAVIGATE, target="KITCHEN"))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_FAILED
    assert envelope["payload"]["resultCode"] == contract.CODE_NOT_ARRIVED
    assert envelope["payload"]["reasonCode"] == contract.REASON_UNKNOWN_TARGET


# ── 만료 (expiresAt) ─────────────────────────────────────────────────────────


def test_expired_command_is_not_executed_and_reports_command_expired() -> None:
    """★ expiresAt 이 지난 명령은 driver 를 호출하지 않고 즉시 실패 회신한다."""
    driver = MockRobotDriver()
    bridge, collector = _make_bridge(driver=driver)

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE,
            target=contract.TARGET_LIVING_ROOM,
            expires_at="2026-07-28T09:59:00+09:00",  # now(10:00 KST) 이전
        )
    )

    assert len(collector.messages) == 1
    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_FAILED
    assert envelope["payload"]["reasonCode"] == contract.REASON_COMMAND_EXPIRED


def test_non_expired_command_still_executes() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE,
            target=contract.TARGET_LIVING_ROOM,
            expires_at="2026-07-28T10:02:00+09:00",  # now(10:00) 이전 마감
        )
    )

    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_SUCCEEDED


# ── commandId 중복 제거 ──────────────────────────────────────────────────────


def test_duplicate_command_id_is_not_re_executed() -> None:
    """★ QoS 1 재전송으로 같은 commandId 가 두 번 오면 두 번째는 무시한다."""
    bridge, collector = _make_bridge()
    raw = _command_json(contract.CMD_NAVIGATE, target=contract.TARGET_LIVING_ROOM)

    bridge.on_command(raw)
    bridge.on_command(raw)  # 재전송 흉내

    assert len(collector.messages) == 1


def test_different_command_ids_both_execute() -> None:
    bridge, collector = _make_bridge()

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE, target=contract.TARGET_LIVING_ROOM,
            command_id="cmd-a",
        )
    )
    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE, target=contract.TARGET_ENTRANCE,
            command_id="cmd-b",
        )
    )

    assert len(collector.messages) == 2


# ── 계약 위반 → 무응답 금지 ──────────────────────────────────────────────────


def test_unparseable_json_is_dropped_without_reply() -> None:
    """JSON 자체가 깨지면 상관관계 ID 를 건질 수 없어 회신도 불가능하다."""
    bridge, collector = _make_bridge()

    bridge.on_command("not a valid json")

    assert collector.messages == []


def test_contract_violation_with_recoverable_ids_still_replies_failed() -> None:
    """★ 무응답 금지: 위반이라도 scenarioId/commandId/type 을 읽을 수 있으면
    FAILED 를 회신한다 — 백엔드가 20분간 기다리다 SAFE_STOP 에 잠그는 것보다
    즉시 실패를 알리는 편이 낫다.
    """
    bridge, collector = _make_bridge()
    # occurredAt 이 없어 parse_command 는 실패하지만, scenarioId/commandId/
    # type/robotId 는 살아 있다.
    broken = json.dumps(
        {
            "commandId": "cmd-broken",
            "scenarioId": "scenario-broken",
            "robotId": "robot-01",
            "type": contract.CMD_NAVIGATE,
            "payload": {"target": "LIVING_ROOM"},
        }
    )

    bridge.on_command(broken)

    assert len(collector.messages) == 1
    envelope = json.loads(collector.messages[0][1])
    assert envelope["scenarioId"] == "scenario-broken"
    assert envelope["commandId"] == "cmd-broken"
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["payload"]["outcome"] == contract.OUTCOME_FAILED


def test_contract_violation_for_other_robot_does_not_reply() -> None:
    bridge, collector = _make_bridge(robot_id="robot-01")
    broken = json.dumps(
        {
            "commandId": "cmd-broken",
            "scenarioId": "scenario-broken",
            "robotId": "robot-99",  # 다른 로봇
            "type": contract.CMD_NAVIGATE,
            "payload": {"target": "LIVING_ROOM"},
        }
    )

    bridge.on_command(broken)

    assert collector.messages == []


# ── FOLLOW 스텁 (산책 보류) ──────────────────────────────────────────────────


@pytest.mark.parametrize("follow_type", [contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP])
def test_follow_commands_get_immediate_failed_stub(follow_type: str) -> None:
    """산책은 이번 스프린트 범위 밖이지만 무응답이면 10초 뒤 SAFE_STOP 이다.

    즉시 FAILED 를 회신해 원인이 로그에 남고 백엔드 워치독 타임아웃을
    기다리지 않게 한다.
    """
    bridge, collector = _make_bridge()

    bridge.on_command(_command_json(follow_type))

    envelope = json.loads(collector.messages[0][1])
    assert envelope["type"] == contract.RESULT_FOLLOW
    assert envelope["payload"]["outcome"] == contract.OUTCOME_FAILED


# ── 스레드 분리 (async_execution) ────────────────────────────────────────────


def test_async_execution_runs_navigate_off_the_calling_thread() -> None:
    """★ 비동기 모드에서는 on_command 가 즉시 돌아오고, 실행은 워커가 한다.

    이게 없으면 paho 콜백 스레드가 주행 내내 블로킹되어 CANCEL 이 큐에서
    썩는다 — 인수인계의 "MQTT 수신과 Nav2 실행 스레드 분리" 요구사항이다.
    """
    driver = MockRobotDriver(delay_seconds=0.2)
    bridge, collector = _make_bridge(driver=driver, async_execution=True)

    started = time.monotonic()
    bridge.on_command(
        _command_json(contract.CMD_NAVIGATE, target=contract.TARGET_LIVING_ROOM)
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.1, "on_command 이 driver.navigate() 완료를 기다리면 안 된다"
    _wait_for(collector, 1)
    envelope = json.loads(collector.messages[0][1])
    assert envelope["payload"]["outcome"] == contract.OUTCOME_SUCCEEDED

    bridge.stop()


def test_cancel_is_handled_synchronously_even_while_worker_is_busy() -> None:
    """★ CANCEL 은 워커 큐를 거치지 않고 수신 스레드에서 즉시 실행된다.

    MockRobotDriver.cancel() 은 항상 즉시 CANCELLED 를 반환하므로, 워커가
    긴 NAVIGATE 를 처리하는 도중에도 CANCEL 회신이 먼저 도착해야 한다.
    """
    driver = MockRobotDriver(delay_seconds=1.0)  # 워커를 오래 붙잡아 둔다
    bridge, collector = _make_bridge(driver=driver, async_execution=True)

    bridge.on_command(
        _command_json(
            contract.CMD_NAVIGATE, target=contract.TARGET_LIVING_ROOM,
            command_id="cmd-nav",
        )
    )
    # CANCEL 은 다른 commandId 로, 워커가 아직 NAVIGATE 를 붙잡고 있는 사이에.
    started = time.monotonic()
    bridge.on_command(_command_json(contract.CMD_CANCEL, command_id="cmd-cancel"))
    elapsed = time.monotonic() - started

    assert elapsed < 0.1, "CANCEL 처리가 워커 큐에서 기다리면 안 된다"
    _wait_for(collector, 1)
    cancel_results = [
        json.loads(payload) for _, payload in collector.messages
        if json.loads(payload)["type"] == contract.RESULT_CANCEL
    ]
    assert len(cancel_results) == 1

    bridge.stop()
