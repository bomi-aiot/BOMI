"""FOLLOW_START / FOLLOW_STOP 처리 검증 — 브로커도 ROS 2 도 없이 실행한다.

이 파일이 지키는 것 (구현계획 §3)
    1. 접수 확인(ACK)을 즉시 회신한다. 백엔드 FOLLOW ACK 타임아웃이 10초인데
       회전 탐색은 20초를 넘길 수 있다 — 탐색 완료를 기다렸다 회신하면
       시나리오가 TIMED_OUT 으로 죽고 로봇이 SAFE_STOP 에 잠긴다.
    2. 회신 필드가 백엔드 파서(MqttInboundMessageParser.validateFollowResult)의
       허용값과 정확히 맞는다. 하나라도 어긋나면 메시지가 통째로 폐기된다.
    3. 탐색 훅이 없으면 성공을 흉내 내지 않고 FAILED 를 돌려준다.
"""

import json

from bridge import contract
from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver
import pytest


ROBOT_ID = "bomi-AA001"
SCENARIO_ID = "11111111-2222-4333-8444-555555555555"

# 백엔드 파서가 FOLLOW_RESULT 에서 허용하는 값 (Java 코드가 권위다).
ALLOWED_OUTCOMES = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}
ALLOWED_RESULT_CODES = {"STARTED", "STOPPED", "UNCHANGED"}
ALLOWED_ENVELOPE_FIELDS = {
    "eventId", "commandId", "scenarioId", "robotId", "type", "occurredAt",
    "payload",
}
ALLOWED_PAYLOAD_FIELDS = {"outcome", "resultCode", "reasonCode", "message"}


class _Recorder:
    """훅이 몇 번 불렸는지 세는 대역."""

    def __init__(self, *, explode: bool = False) -> None:
        self.calls = 0
        self._explode = explode

    def __call__(self) -> None:
        self.calls += 1
        if self._explode:
            raise RuntimeError("훅이 죽었다")


def _command_json(command_type: str, command_id: str = "cmd-1") -> str:
    """백엔드가 보내는 명령 봉투 한 통을 만든다."""
    return json.dumps({
        "commandId": command_id,
        "scenarioId": SCENARIO_ID,
        "robotId": ROBOT_ID,
        "type": command_type,
        "occurredAt": "2026-08-06T00:00:00Z",
        "expiresAt": "2099-01-01T00:00:00Z",
        "payload": {},
    })


def _build(**kwargs):
    """동기 실행(async_execution=False) 브릿지와 발행 수집기를 만든다."""
    published: list[tuple[str, str]] = []
    bridge = MqttBridge(
        ROBOT_ID,
        MockRobotDriver(),
        lambda topic, payload: published.append((topic, payload)),
        **kwargs,
    )
    return bridge, published


def _results(published):
    """발행된 것 중 FOLLOW_RESULT 만 골라 payload 로 돌려준다."""
    found = []
    for topic, raw in published:
        envelope = json.loads(raw)
        if envelope.get("type") == contract.RESULT_FOLLOW:
            assert topic == contract.robot_results_topic(ROBOT_ID)
            found.append(envelope)
    return found


# ── 시작 ────────────────────────────────────────────────────────────────────


def test_follow_start_acknowledges_immediately_and_starts_the_search() -> None:
    start = _Recorder()
    bridge, published = _build(on_follow_start=start)

    bridge.on_command(_command_json(contract.CMD_FOLLOW_START))

    envelopes = _results(published)
    assert len(envelopes) == 1
    payload = envelopes[0]["payload"]
    assert payload["outcome"] == contract.OUTCOME_SUCCEEDED
    assert payload["resultCode"] == contract.CODE_STARTED
    assert payload["reasonCode"] is None
    assert start.calls == 1


def test_follow_stop_acknowledges_and_stops_the_search() -> None:
    stop = _Recorder()
    bridge, published = _build(on_follow_stop=stop)

    bridge.on_command(_command_json(contract.CMD_FOLLOW_STOP))

    payload = _results(published)[0]["payload"]
    assert payload["outcome"] == contract.OUTCOME_SUCCEEDED
    assert payload["resultCode"] == contract.CODE_STOPPED
    assert payload["reasonCode"] is None
    assert stop.calls == 1


def test_start_and_stop_hooks_do_not_cross() -> None:
    start, stop = _Recorder(), _Recorder()
    bridge, _published = _build(on_follow_start=start, on_follow_stop=stop)

    bridge.on_command(_command_json(contract.CMD_FOLLOW_START, "cmd-a"))
    assert (start.calls, stop.calls) == (1, 0)

    bridge.on_command(_command_json(contract.CMD_FOLLOW_STOP, "cmd-b"))
    assert (start.calls, stop.calls) == (1, 1)


# ── 훅이 없거나 죽을 때 ─────────────────────────────────────────────────────


def test_follow_without_a_hook_reports_failure_instead_of_pretending() -> None:
    # 순수 paho 경로처럼 ROS 2 발행자를 만들 수 없는 실행 경로다. 성공을
    # 흉내 내면 백엔드는 로봇이 도는 줄 알고 대화를 이어간다.
    bridge, published = _build()

    bridge.on_command(_command_json(contract.CMD_FOLLOW_START))

    payload = _results(published)[0]["payload"]
    assert payload["outcome"] == contract.OUTCOME_FAILED
    assert payload["resultCode"] == contract.CODE_UNCHANGED
    assert payload["reasonCode"] == contract.REASON_INTERNAL_ERROR


def test_hook_failure_does_not_break_the_acknowledgement() -> None:
    # 회신은 훅보다 먼저 나간다. 훅이 죽어도 백엔드가 보는 시나리오는
    # 이미 정상 접수돼 있다.
    exploding = _Recorder(explode=True)
    bridge, published = _build(on_follow_start=exploding)

    bridge.on_command(_command_json(contract.CMD_FOLLOW_START))

    payload = _results(published)[0]["payload"]
    assert payload["outcome"] == contract.OUTCOME_SUCCEEDED
    assert exploding.calls == 1


# ── 백엔드 계약 준수 ────────────────────────────────────────────────────────


def test_result_envelope_matches_the_backend_whitelist() -> None:
    # 허용 목록 밖의 필드가 하나라도 있으면 백엔드가 메시지를 통째로 버린다.
    bridge, published = _build(on_follow_start=_Recorder())
    bridge.on_command(_command_json(contract.CMD_FOLLOW_START))

    envelope = _results(published)[0]
    assert set(envelope).issubset(ALLOWED_ENVELOPE_FIELDS)
    assert set(envelope["payload"]).issubset(ALLOWED_PAYLOAD_FIELDS)
    assert envelope["payload"]["outcome"] in ALLOWED_OUTCOMES
    assert envelope["payload"]["resultCode"] in ALLOWED_RESULT_CODES


def test_result_echoes_the_correlation_ids() -> None:
    bridge, published = _build(on_follow_start=_Recorder())
    bridge.on_command(_command_json(contract.CMD_FOLLOW_START, "cmd-xyz"))

    envelope = _results(published)[0]
    assert envelope["commandId"] == "cmd-xyz"
    assert envelope["scenarioId"] == SCENARIO_ID
    assert envelope["robotId"] == ROBOT_ID


@pytest.mark.parametrize(
    "command_type", [contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP])
def test_expired_follow_command_is_not_executed(command_type) -> None:
    # 만료된 명령으로 로봇이 돌기 시작하면 안 된다.
    start, stop = _Recorder(), _Recorder()
    bridge, published = _build(on_follow_start=start, on_follow_stop=stop)

    expired = json.loads(_command_json(command_type))
    expired["expiresAt"] = "2000-01-01T00:00:00Z"
    bridge.on_command(json.dumps(expired))

    assert (start.calls, stop.calls) == (0, 0)
    payload = _results(published)[0]["payload"]
    assert payload["outcome"] == contract.OUTCOME_FAILED
    assert payload["reasonCode"] == contract.REASON_COMMAND_EXPIRED
