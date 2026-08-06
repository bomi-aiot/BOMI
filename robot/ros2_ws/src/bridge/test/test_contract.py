"""계약 모듈(contract.py)의 파싱·검증·envelope 생성을 검증하는 단위 테스트다."""

from datetime import datetime, timezone
import json

from bridge import contract
import pytest


def _valid_command_json(**overrides) -> str:
    body = {
        "commandId": "cmd-1",
        "scenarioId": "11111111-1111-1111-1111-111111111111",
        "robotId": "robot-01",
        "type": contract.CMD_NAVIGATE,
        "occurredAt": "2026-07-28T10:00:00+09:00",
        "expiresAt": "2026-07-28T10:02:00+09:00",
        "payload": {contract.NAV_TARGET_KEY: contract.TARGET_ENTRANCE},
    }
    body.update(overrides)
    return json.dumps(body)


def test_topics_follow_convention() -> None:
    assert contract.robot_commands_topic("robot-01") == "bomi/v1/robot/robot-01/commands"
    assert contract.robot_results_topic("robot-01") == "bomi/v1/robot/robot-01/results"
    assert contract.robot_status_topic("robot-01") == "bomi/v1/robot/robot-01/status"


def test_parse_valid_navigate_command() -> None:
    command = contract.parse_command(_valid_command_json())

    assert command.type == contract.CMD_NAVIGATE
    assert command.robot_id == "robot-01"
    assert command.scenario_id == "11111111-1111-1111-1111-111111111111"
    assert command.target == contract.TARGET_ENTRANCE


def test_parse_accepts_bytes_payload() -> None:
    command = contract.parse_command(_valid_command_json().encode("utf-8"))
    assert command.command_id == "cmd-1"


def test_parse_rejects_blank_payload() -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command("")


def test_parse_rejects_non_json() -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command("not json")


def test_parse_rejects_missing_required_field() -> None:
    body = json.loads(_valid_command_json())
    del body["scenarioId"]
    with pytest.raises(contract.ContractError):
        contract.parse_command(json.dumps(body))


def test_parse_rejects_unknown_command_type() -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(type="DANCE"))


def test_parse_rejects_non_object_payload() -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(payload="oops"))


def test_parse_rejects_overlong_command_id() -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(commandId="x" * 65))


@pytest.mark.parametrize(
    "command_type", [contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP]
)
def test_parse_accepts_follow_commands(command_type: str) -> None:
    command = contract.parse_command(
        _valid_command_json(type=command_type, payload={})
    )
    assert command.type == command_type


def test_navigation_targets_match_confirmed_contract() -> None:
    assert contract.NAV_TARGETS == {
        contract.TARGET_ENTRANCE,
        contract.TARGET_DEFAULT,
        contract.TARGET_LIVING_ROOM,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("occurredAt", "not-a-time"),
        ("expiresAt", "2026-07-28T10:02:00"),
    ],
)
def test_parse_rejects_invalid_or_timezone_less_timestamp(
    field: str,
    value: str,
) -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(**{field: value}))


def test_expiration_uses_timezone_aware_instants() -> None:
    command = contract.parse_command(_valid_command_json())

    assert contract.is_command_expired(
        command,
        now=lambda: datetime(2026, 7, 28, 1, 1, tzinfo=timezone.utc),
    ) is False
    assert contract.is_command_expired(
        command,
        now=lambda: datetime(2026, 7, 28, 1, 3, tzinfo=timezone.utc),
    ) is True


def test_build_result_envelope_matches_backend_contract() -> None:
    fixed = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)
    envelope = contract.build_result_envelope(
        "robot-01",
        contract.RESULT_NAVIGATION,
        "scenario-9",
        contract.STATUS_ARRIVED,
        now=lambda: fixed,
        event_id="evt-1",
    )

    # 백엔드 인바운드 파서가 요구하는 필드
    assert envelope["eventId"] == "evt-1"
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["occurredAt"] == "2026-07-28T01:00:00+00:00"
    assert envelope["robotId"] == "robot-01"
    # scenarioId echo-back (백엔드가 시나리오를 잇는 핵심)
    assert envelope["payload"][contract.RESULT_SCENARIO_ID_KEY] == "scenario-9"
    assert envelope["payload"][contract.RESULT_STATUS_KEY] == contract.STATUS_ARRIVED


def test_build_result_envelope_generates_ids_when_not_injected() -> None:
    envelope = contract.build_result_envelope(
        "robot-01", contract.RESULT_SPEAK, "scenario-1", contract.STATUS_DONE
    )
    assert envelope["eventId"]
    assert envelope["occurredAt"].endswith("+00:00")
