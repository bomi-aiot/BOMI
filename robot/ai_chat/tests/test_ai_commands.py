# robot/ai_chat/tests/test_ai_commands.py
"""START_CONVERSATION 수신·응답 계약 회귀 — S15P11E102 통합 스프린트.

이 파일이 검증하는 것
    1. contracts/ai_commands.py 의 파싱·만료 판정·응답 봉투가 백엔드 계약
       (scenario-contract-v1.md §6, MqttInboundMessageParser)과 일치한다.
    2. AiCommandSubscriber 가 브로커 없이도 전 경로(파싱 -> dedup -> 만료 ->
       ACK 발행 -> 큐 적재)를 돈다.
    3. 계약 위반·중복·만료 각각에서 무엇을 하고 무엇을 안 하는지
       (CONVERSATION_STARTED 를 보내는가/안 보내는가는 시나리오마다 다르다).

참고
    CLAUDE.md §2(계약 요약), docs/mqtt/scenario-contract-v1.md §6
"""

import json
import queue

import pytest

from bomi_ai_chat.ai_commands import (
    AiCommandSubscriber,
    build_ai_command_subscriber,
)
from bomi_ai_chat.contracts import ai_commands as contract

SENIOR = "senior-1"
NOW = 1_700_000_000.0  # 2023-11-14T22:13:20+00:00


def start_conversation_json(**overrides) -> str:
    body = {
        "commandId": "cmd-conv-1",
        "scenarioId": "scenario-uuid-1",
        "conversationId": "conversation-uuid-1",
        "robotId": "bomi-AA001",
        "type": "START_CONVERSATION",
        "occurredAt": "2026-08-04T18:10:08+09:00",
        "expiresAt": "2026-08-04T18:20:08+09:00",
        "payload": {
            "seniorId": "senior-uuid-1",
            "intent": "HOMECOMING_GREETING",
            "text": "다녀오셨어요? 오늘 외출은 어떠셨어요?",
            "triggerContext": {"sourceId": "door-sensor-001", "location": "ENTRANCE"},
        },
    }
    body.update(overrides)
    return json.dumps(body)


# ── contracts/ai_commands.py: 파싱 ───────────────────────────────────────────


def test_parse_valid_start_conversation():
    command = contract.parse_start_conversation(start_conversation_json())

    assert command.command_id == "cmd-conv-1"
    assert command.scenario_id == "scenario-uuid-1"
    assert command.conversation_id == "conversation-uuid-1"
    assert command.robot_id == "bomi-AA001"
    assert command.intent == "HOMECOMING_GREETING"
    assert command.text == "다녀오셨어요? 오늘 외출은 어떠셨어요?"
    assert command.trigger_context == {
        "sourceId": "door-sensor-001", "location": "ENTRANCE",
    }


def test_parse_accepts_bytes():
    command = contract.parse_start_conversation(
        start_conversation_json().encode("utf-8")
    )
    assert command.command_id == "cmd-conv-1"


@pytest.mark.parametrize("field", [
    "commandId", "scenarioId", "conversationId", "robotId",
    "occurredAt", "expiresAt",
])
def test_parse_rejects_missing_envelope_field(field):
    body = json.loads(start_conversation_json())
    del body[field]
    with pytest.raises(contract.AiCommandError):
        contract.parse_start_conversation(json.dumps(body))


@pytest.mark.parametrize("field", ["seniorId", "intent", "text"])
def test_parse_rejects_missing_payload_field(field):
    body = json.loads(start_conversation_json())
    del body["payload"][field]
    with pytest.raises(contract.AiCommandError):
        contract.parse_start_conversation(json.dumps(body))


def test_parse_rejects_wrong_type():
    with pytest.raises(contract.AiCommandError):
        contract.parse_start_conversation(
            start_conversation_json(type="NAVIGATE")
        )


def test_parse_rejects_blank_text():
    with pytest.raises(contract.AiCommandError):
        contract.parse_start_conversation(
            start_conversation_json(
                payload={"seniorId": "s", "intent": "HOMECOMING_GREETING", "text": "   "}
            )
        )


def test_parse_accepts_unknown_intent_but_warns(caplog):
    """★ 모르는 intent 라도 text 는 살아 있으면 말은 하게 둔다 — 침묵보다 낫다."""
    with caplog.at_level("WARNING"):
        command = contract.parse_start_conversation(
            start_conversation_json(
                payload={
                    "seniorId": "s", "intent": "NEW_SCENARIO_TYPE",
                    "text": "안녕하세요", "triggerContext": {},
                }
            )
        )

    assert command.intent == "NEW_SCENARIO_TYPE"
    assert "unknown intent" in caplog.text


def test_parse_missing_trigger_context_defaults_to_empty_dict():
    body = json.loads(start_conversation_json())
    del body["payload"]["triggerContext"]

    command = contract.parse_start_conversation(json.dumps(body))

    assert command.trigger_context == {}


# ── contracts/ai_commands.py: 만료 ───────────────────────────────────────────


def test_command_expired_true_after_deadline():
    command = contract.parse_start_conversation(start_conversation_json())
    # expiresAt = 2026-08-04T18:20:08+09:00 = epoch 1785835208. 그 60초 뒤.
    after_deadline = 1_785_835_268.0
    assert contract.command_expired(command, now=after_deadline) is True


def test_command_expired_false_before_deadline():
    command = contract.parse_start_conversation(start_conversation_json())
    # expiresAt(epoch 1785835208) 보다 20분 이전.
    before_deadline = 1_785_834_000.0
    assert contract.command_expired(command, now=before_deadline) is False


def test_command_expired_accepts_backend_utc_z_timestamp():
    """Jetson Python 3.10에서도 백엔드의 RFC 3339 `Z` 시각을 파싱한다."""
    command = contract.parse_start_conversation(
        start_conversation_json(
            occurredAt="2026-08-07T19:31:14.100115958Z",
            expiresAt="2026-08-07T19:31:24.100115958Z",
        )
    )
    before_deadline = 1_786_131_074.0  # 2026-08-07T19:31:14Z

    assert contract.command_expired(command, now=before_deadline) is False


# ── contracts/ai_commands.py: 응답 봉투 ──────────────────────────────────────


def test_build_conversation_started_matches_contract():
    command = contract.parse_start_conversation(start_conversation_json())

    envelope = contract.build_conversation_started(
        "bomi-AA001", command, now=NOW, event_id="evt-1"
    )

    assert envelope["type"] == "CONVERSATION_STARTED"
    assert envelope["robotId"] == "bomi-AA001"
    # 최상위 echo-back 셋 다.
    assert envelope["scenarioId"] == "scenario-uuid-1"
    assert envelope["conversationId"] == "conversation-uuid-1"
    assert envelope["commandId"] == "cmd-conv-1"
    assert envelope["payload"] == {"intent": "HOMECOMING_GREETING"}


def test_build_conversation_ended_omits_command_id():
    """★ 계약 §4: CONVERSATION_ENDED 최소 형식엔 commandId 를 넣지 않는다."""
    command = contract.parse_start_conversation(start_conversation_json())

    envelope = contract.build_conversation_ended(
        "bomi-AA001", command, contract.OUTCOME_COMPLETED, None, now=NOW,
    )

    assert "commandId" not in envelope
    assert envelope["scenarioId"] == "scenario-uuid-1"
    assert envelope["conversationId"] == "conversation-uuid-1"
    assert envelope["payload"] == {"outcome": "COMPLETED", "reasonCode": None}


def test_build_conversation_ended_rejects_unknown_outcome():
    command = contract.parse_start_conversation(start_conversation_json())
    with pytest.raises(contract.AiCommandError):
        contract.build_conversation_ended(
            "bomi-AA001", command, "SOMETHING_ELSE", None,
        )


def test_build_conversation_ended_requires_reason_on_failed():
    command = contract.parse_start_conversation(start_conversation_json())
    with pytest.raises(contract.AiCommandError):
        contract.build_conversation_ended(
            "bomi-AA001", command, contract.OUTCOME_FAILED, None,
        )


def test_build_conversation_ended_allows_failed_with_reason():
    command = contract.parse_start_conversation(start_conversation_json())
    envelope = contract.build_conversation_ended(
        "bomi-AA001", command, contract.OUTCOME_FAILED, "STT_UNAVAILABLE",
    )
    assert envelope["payload"]["reasonCode"] == "STT_UNAVAILABLE"


# ── AiCommandSubscriber ──────────────────────────────────────────────────────


class _Collector:
    def __init__(self):
        self.published: list[tuple[str, str, int]] = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))


def _make_subscriber(settings_factory, *, client=None, maxsize=4):
    settings = settings_factory(
        MQTT_ENABLED="true",
        MQTT_BROKER_URL="mqtt://broker.example:1883",
        ROBOT_DEVICE_ID="bomi-AA001",
    )
    pending: queue.Queue = queue.Queue(maxsize=maxsize)
    subscriber = AiCommandSubscriber(
        settings=settings, pending_queue=pending, client=client
    )
    return subscriber, pending


def test_valid_command_publishes_started_and_queues(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client)

    accepted = subscriber.handle_payload(start_conversation_json())

    assert accepted is True
    assert pending.qsize() == 1
    queued = pending.get_nowait()
    assert queued.command_id == "cmd-conv-1"

    assert len(client.published) == 1
    topic, raw, qos = client.published[0]
    assert topic == "bomi/v1/robot/bomi-AA001/events"
    assert qos == 1
    envelope = json.loads(raw)
    assert envelope["type"] == "CONVERSATION_STARTED"
    assert envelope["commandId"] == "cmd-conv-1"


def test_malformed_payload_is_dropped_without_publishing(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client)

    accepted = subscriber.handle_payload("not json")

    assert accepted is False
    assert pending.qsize() == 0
    assert client.published == []


def test_wrong_robot_id_is_dropped(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client)

    accepted = subscriber.handle_payload(
        start_conversation_json(robotId="some-other-robot")
    )

    assert accepted is False
    assert pending.qsize() == 0
    assert client.published == []


def test_duplicate_command_id_is_ignored(settings_factory, frozen_clock):
    """★ QoS 1 재전송으로 같은 commandId 가 두 번 오면 두 번째는 무시한다.

    첫 번째 CONVERSATION_STARTED 는 이미 나갔으므로 재전송에 또 보내지
    않는다 — 두 번 보내면 백엔드가 같은 대화를 두 번 시작한 것처럼 볼 수 있다.
    """
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client)
    raw = start_conversation_json()

    first = subscriber.handle_payload(raw)
    second = subscriber.handle_payload(raw)

    assert first is True
    assert second is False
    assert pending.qsize() == 1
    assert len(client.published) == 1


def test_expired_command_is_dropped_without_reply(settings_factory, frozen_clock):
    """★ 만료된 명령엔 아무것도 응답하지 않는다 — 백엔드의 10초 워치독이 정리한다."""
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client)

    accepted = subscriber.handle_payload(
        start_conversation_json(
            occurredAt="2020-01-01T00:00:00+09:00",
            expiresAt="2020-01-01T00:00:10+09:00",  # NOW(2023) 보다 훨씬 과거
        )
    )

    assert accepted is False
    assert pending.qsize() == 0
    assert client.published == []


def test_full_queue_drops_new_command_without_crashing(settings_factory, frozen_clock):
    """메인 루프가 밀려 있어도 paho 콜백 스레드가 죽거나 블로킹하지 않는다."""
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, pending = _make_subscriber(settings_factory, client=client, maxsize=1)
    subscriber.handle_payload(start_conversation_json(commandId="cmd-a"))

    accepted = subscriber.handle_payload(
        start_conversation_json(commandId="cmd-b", conversationId="conv-b")
    )

    assert accepted is False
    assert pending.qsize() == 1  # cmd-a 만 남아 있다


def test_publish_conversation_ended(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    client = _Collector()
    subscriber, _pending = _make_subscriber(settings_factory, client=client)
    command = contract.parse_start_conversation(start_conversation_json())

    subscriber.publish_conversation_ended(command, contract.OUTCOME_COMPLETED)

    assert len(client.published) == 1
    topic, raw, qos = client.published[0]
    assert topic == "bomi/v1/robot/bomi-AA001/events"
    assert qos == 1
    envelope = json.loads(raw)
    assert envelope["type"] == "CONVERSATION_ENDED"
    assert envelope["payload"]["outcome"] == "COMPLETED"


def test_publish_conversation_ended_without_client_does_not_raise(settings_factory, frozen_clock):
    """발행자 연결이 없어도(오프라인) 예외를 올리지 않는다 — 대화는 이미 끝났다."""
    frozen_clock(start=NOW)
    subscriber, _pending = _make_subscriber(settings_factory, client=None)
    command = contract.parse_start_conversation(start_conversation_json())

    subscriber.publish_conversation_ended(command, contract.OUTCOME_NO_RESPONSE)


# ── build_ai_command_subscriber 게이트 ───────────────────────────────────────


def test_disabled_mqtt_builds_no_subscriber(settings_factory, caplog):
    settings = settings_factory()
    with caplog.at_level("WARNING"):
        subscriber = build_ai_command_subscriber(
            settings=settings, pending_queue=queue.Queue()
        )

    assert subscriber is None
    assert "MQTT is disabled" in caplog.text


def test_missing_robot_device_id_builds_no_subscriber(settings_factory, caplog):
    settings = settings_factory(
        MQTT_ENABLED="true", MQTT_BROKER_URL="mqtt://broker.example:1883",
    )
    with caplog.at_level("WARNING"):
        subscriber = build_ai_command_subscriber(
            settings=settings, pending_queue=queue.Queue()
        )

    assert subscriber is None
    assert "ROBOT_DEVICE_ID" in caplog.text


def test_enabled_settings_build_a_subscriber(settings_factory):
    settings = settings_factory(
        MQTT_ENABLED="true", MQTT_BROKER_URL="mqtt://broker.example:1883",
        ROBOT_DEVICE_ID="bomi-AA001",
    )

    subscriber = build_ai_command_subscriber(
        settings=settings, pending_queue=queue.Queue()
    )

    assert subscriber is not None
