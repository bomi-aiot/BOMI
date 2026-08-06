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


def test_navigation_targets_match_confirmed_contract() -> None:
    assert contract.NAVIGATION_TARGETS == {
        contract.TARGET_ENTRANCE,
        contract.TARGET_DEFAULT,
        contract.TARGET_LIVING_ROOM,
    }


@pytest.mark.parametrize(
    "value",
    [
        "not-a-time",
        "2026-07-28T10:02:00",  # 시간대 없음 — 시계 비교가 불가능하다
    ],
)
def test_parse_rejects_invalid_or_timezone_less_expires_at(value: str) -> None:
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(expiresAt=value))


def test_parse_accepts_utc_z_suffix_expires_at() -> None:
    """★ ``Z`` 표기도 받아야 한다 — 젯슨의 Python 3.10 은 이걸 못 읽는다.

    contract 가 직접 ``+00:00`` 으로 바꿔 주지 않으면 UTC 로 표기된 명령이
    전부 형식 오류로 거절된다.
    """
    command = contract.parse_command(
        _valid_command_json(expiresAt="2026-07-28T01:02:00Z")
    )
    before = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)
    assert contract.command_expired(command, now=lambda: before) is False


def test_parse_rejects_malformed_expires_at() -> None:
    """★ expiresAt 이 ISO-8601 이 아니면 파싱 단계에서 거절한다.

    "판정 불가능 = 실행"으로 흘러가지 않도록, 형식이 깨진 시각은 만료
    검사까지 가지 않고 여기서 명령 자체를 거절한다.
    """
    with pytest.raises(contract.ContractError):
        contract.parse_command(_valid_command_json(expiresAt="not-a-datetime"))


def test_parse_accepts_all_v1_navigate_targets() -> None:
    """LIVING_ROOM·ENTRANCE·DEFAULT 셋 다 계약이 허용하는 target 이다."""
    for target in (
        contract.TARGET_LIVING_ROOM,
        contract.TARGET_ENTRANCE,
        contract.TARGET_DEFAULT,
    ):
        command = contract.parse_command(
            _valid_command_json(payload={contract.NAV_TARGET_KEY: target})
        )
        assert command.target == target


def test_parse_accepts_follow_commands() -> None:
    """FOLLOW_START/STOP 은 시연 범위 밖이지만 계약 타입으로는 존재한다.

    모르는 타입으로 거절하면 백엔드의 10초 ACK 타임아웃이 무응답으로
    터지고 로봇이 SAFE_STOP 에 잠긴다 — 파싱은 받아 줘야 스텁 회신이 된다.
    """
    for follow_type in (contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP):
        command = contract.parse_command(
            _valid_command_json(type=follow_type, payload={})
        )
        assert command.type == follow_type


# ── command_expired ────────────────────────────────────────────────────────


def test_command_expired_true_after_deadline() -> None:
    command = contract.parse_command(_valid_command_json())  # expiresAt +09:00 10:02
    past_deadline = datetime(2026, 7, 28, 1, 3, 0, tzinfo=timezone.utc)  # 10:03 KST
    assert contract.command_expired(command, now=lambda: past_deadline) is True


def test_command_expired_false_before_deadline() -> None:
    command = contract.parse_command(_valid_command_json())
    before_deadline = datetime(2026, 7, 28, 0, 30, 0, tzinfo=timezone.utc)  # 09:30 KST
    assert contract.command_expired(command, now=lambda: before_deadline) is False


# ── build_result_envelope (v1) ──────────────────────────────────────────────


def test_build_result_envelope_matches_backend_v1_contract() -> None:
    """★ 상관관계 ID 는 최상위, payload 는 outcome/resultCode/reasonCode 뿐.

    백엔드 파서는 이 형태 밖의 필드를 화이트리스트 위반으로 통째로
    폐기한다 — 이 테스트가 그 계약의 로봇 쪽 고정이다.
    """
    fixed = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)
    envelope = contract.build_result_envelope(
        "robot-01",
        contract.RESULT_NAVIGATION,
        "scenario-9",
        "cmd-9",
        contract.OUTCOME_SUCCEEDED,
        contract.CODE_ARRIVED,
        None,
        now=lambda: fixed,
        event_id="evt-1",
    )

    assert envelope["eventId"] == "evt-1"
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["occurredAt"] == "2026-07-28T01:00:00+00:00"
    assert envelope["robotId"] == "robot-01"
    # v1: scenarioId/commandId 는 최상위 echo-back. payload 안에 넣으면 안 된다.
    assert envelope["scenarioId"] == "scenario-9"
    assert envelope["commandId"] == "cmd-9"
    assert envelope["payload"] == {
        "outcome": contract.OUTCOME_SUCCEEDED,
        "resultCode": contract.CODE_ARRIVED,
        "reasonCode": None,
    }
    assert set(envelope.keys()) == {
        "eventId", "type", "occurredAt", "robotId",
        "scenarioId", "commandId", "payload",
    }


def test_build_result_envelope_generates_ids_when_not_injected() -> None:
    envelope = contract.build_result_envelope(
        "robot-01", contract.RESULT_SPEAK, "scenario-1", "cmd-1",
        contract.OUTCOME_SUCCEEDED, contract.CODE_SPOKEN, None,
    )
    assert envelope["eventId"]
    assert envelope["occurredAt"].endswith("+00:00")


def test_build_result_envelope_rejects_reason_on_success() -> None:
    """SUCCEEDED 인데 reasonCode 가 있으면 계약 위반이다."""
    with pytest.raises(contract.ContractError):
        contract.build_result_envelope(
            "robot-01", contract.RESULT_NAVIGATION, "s", "c",
            contract.OUTCOME_SUCCEEDED, contract.CODE_ARRIVED,
            contract.REASON_INTERNAL_ERROR,
        )


def test_build_result_envelope_requires_reason_on_failure() -> None:
    """비성공인데 reasonCode 가 없으면 계약 위반이다."""
    with pytest.raises(contract.ContractError):
        contract.build_result_envelope(
            "robot-01", contract.RESULT_NAVIGATION, "s", "c",
            contract.OUTCOME_FAILED, contract.CODE_NOT_ARRIVED, None,
        )
