# robot/ai_chat/src/bomi_ai_chat/contracts/ai_commands.py
"""백엔드 → AI 대화 명령 계약 — `START_CONVERSATION`과 그 응답 두 이벤트.

봉투는 `docs/mqtt/scenario-contract-v1.md` §6 을 따른다. 토픽은
``bomi/v1/ai/{robotId}/commands`` (수신), ``bomi/v1/robot/{robotId}/events``
(발행 — `CONVERSATION_STARTED`/`CONVERSATION_ENDED` 도 로봇 이벤트 토픽으로
나간다. AI 전용 이벤트 토픽은 없다).

    {"commandId": "...", "scenarioId": "...-uuid", "conversationId": "...-uuid",
     "robotId": "bomi-AA001", "type": "START_CONVERSATION",
     "occurredAt": "...+09:00", "expiresAt": "...+09:00",
     "payload": {"seniorId": "...-uuid", "intent": "HOMECOMING_GREETING",
                 "text": "다녀오셨어요?", "triggerContext": {...}}}

이 모듈이 하는 일과 하지 않는 일  ★ 먼저 읽을 것
    한다     봉투 검증, CONVERSATION_STARTED/ENDED 응답 봉투 생성
    안 한다  발화 자체(그래프가 한다), MQTT 연결(ai_commands.py 가 한다)

    door 의 `contracts/door.py` 와 같은 이유로 분리한다 — 브로커 없이도 계약
    형식을 단위 테스트할 수 있어야 한다.

왜 `contracts/door.py` 보다 엄격하게 검증하는가
    현관 이벤트는 "타입을 모르면 버린다"로 충분했다. 이 명령은 다르다 —
    `text` 를 못 읽으면 로봇이 **아무 말도 하지 못하고 침묵하는 시나리오**가
    된다. 그 자체는 §14 상 안전하지만, 백엔드는 `CONVERSATION_STARTED` 조차
    못 받아 10초 뒤 `AI_START_TIMEOUT` 으로 실패 처리한다 — 침묵의 원인을
    로그로 남겨야 나중에 "왜 인사를 안 했나"에 답할 수 있다.

참고
    CLAUDE.md §3 (MQTT 계약 요약), docs/mqtt/scenario-contract-v1.md §6
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TYPE_START_CONVERSATION = "START_CONVERSATION"
TYPE_CONVERSATION_STARTED = "CONVERSATION_STARTED"
TYPE_CONVERSATION_ENDED = "CONVERSATION_ENDED"

# 백엔드가 실제로 보내는 세 가지뿐이다 (scenario-contract-v1.md §6 253줄:
# "산책용 AI 대화 intent는 구현 범위에 포함하지 않는다"). 모르는 값은 거부하지
# 않는다 — 그래도 text 는 말할 수 있고, 침묵보다 낫다. 대신 경고를 남긴다.
KNOWN_INTENTS = frozenset(
    {"WELLNESS_CHECK", "MEDICATION_REMINDER", "HOMECOMING_GREETING"}
)

# CONVERSATION_ENDED.payload.outcome — 계약 §6 305행의 네 값 그대로.
OUTCOME_COMPLETED = "COMPLETED"
OUTCOME_NO_RESPONSE = "NO_RESPONSE"
OUTCOME_CANCELLED = "CANCELLED"
OUTCOME_FAILED = "FAILED"
OUTCOMES = frozenset(
    {OUTCOME_COMPLETED, OUTCOME_NO_RESPONSE, OUTCOME_CANCELLED, OUTCOME_FAILED}
)


class AiCommandError(ValueError):
    """명령 봉투가 계약을 만족하지 않는다.

    누가 잡는가
        ai_commands.py 의 구독 콜백. 경고로 남기고 그 메시지만 버린다 —
        형식이 깨진 명령 하나로 이후 명령 수신이 멈추면 안 된다.
    """


@dataclass(frozen=True)
class StartConversationCommand:
    """정규화된 `START_CONVERSATION` 명령.

    필드
        command_id, scenario_id, conversation_id, robot_id: 최상위 상관관계 ID.
            결과 이벤트에 그대로 echo-back 해야 한다.
        expires_at: 원문 그대로(파싱하지 않음) — 만료 판정은 command_expired() 가 한다.
        senior_id, intent, text, trigger_context: payload 의 네 필수 필드.
            intent 는 KNOWN_INTENTS 밖일 수 있다(경고만 남기고 통과) — 그래도
            text 는 말할 수 있어야 하기 때문이다.
    """

    command_id: str
    scenario_id: str
    conversation_id: str
    robot_id: str
    occurred_at: str
    expires_at: str
    senior_id: str
    intent: str
    text: str
    trigger_context: Mapping[str, Any] = field(default_factory=dict)


def parse_start_conversation(message: Mapping[str, Any] | str | bytes) -> StartConversationCommand:
    """MQTT 페이로드를 `StartConversationCommand` 로 정규화한다.

    무엇을 하는가
        JSON 파싱, 필수 필드 존재 확인. `type` 이 START_CONVERSATION 이 아니면
        거부한다(이 토픽엔 v1 상 이 타입 하나뿐이지만, 미래의 새 타입이 조용히
        엉뚱하게 처리되는 것을 막는다).

    예외
        AiCommandError — 필수 필드 부재, JSON 아님, payload 객체 아님.

    주의사항
        - `text` 가 공백뿐이면 예외를 던진다 — 말할 내용이 없는 대화 명령은
          계약 위반으로 다룬다(빈 문장을 파이프라인에 올리지 않는다, CLAUDE.md
          구 §14 원칙 유지).
        - `intent` 가 KNOWN_INTENTS 밖이면 예외 대신 경고만 남긴다. 백엔드가
          새 시나리오를 추가했을 때 로봇이 침묵하는 것보다, 일단 말하고 로그로
          알리는 편이 낫다(§14: 모르면 물어보되, 여기선 '말은 한다').
    """
    body = _as_mapping(message)

    message_type = str(body.get("type") or "").strip()
    if message_type != TYPE_START_CONVERSATION:
        raise AiCommandError(
            f"unsupported ai command type {message_type!r}; "
            f"expected {TYPE_START_CONVERSATION!r}"
        )

    command_id = _require_text(body, "commandId")
    scenario_id = _require_text(body, "scenarioId")
    conversation_id = _require_text(body, "conversationId")
    robot_id = _require_text(body, "robotId")
    occurred_at = _require_text(body, "occurredAt")
    expires_at = _require_text(body, "expiresAt")

    payload = body.get("payload")
    if not isinstance(payload, Mapping):
        raise AiCommandError("START_CONVERSATION payload must be a JSON object")

    senior_id = _require_text(payload, "seniorId")
    intent = _require_text(payload, "intent")
    if intent not in KNOWN_INTENTS:
        logger.warning(
            "START_CONVERSATION carries an unknown intent %r; speaking anyway",
            intent,
        )
    text = _require_text(payload, "text")
    trigger_context = payload.get("triggerContext")
    if not isinstance(trigger_context, Mapping):
        trigger_context = {}

    return StartConversationCommand(
        command_id=command_id,
        scenario_id=scenario_id,
        conversation_id=conversation_id,
        robot_id=robot_id,
        occurred_at=occurred_at,
        expires_at=expires_at,
        senior_id=senior_id,
        intent=intent,
        text=text,
        trigger_context=dict(trigger_context),
    )


def command_expired(command: StartConversationCommand, *, now: float | None = None) -> bool:
    """명령의 expiresAt 이 지났는지 판정한다.

    무엇을 하는가
        expiresAt(ISO-8601)을 파싱해 현재 시각과 비교한다. bridge.contract 의
        동명 함수와 같은 이유다 — 큐잉·재전송으로 늦게 도착한 인사 명령이
        엉뚱한 타이밍에 발화되는 것을 막는다.

    반환값
        만료됐으면 True. expiresAt 파싱 불가면 True(안전 쪽으로 넘어진다).
    """
    parsed = _parse_iso_datetime(command.expires_at)
    if parsed is None:
        return True
    current = now if now is not None else clock_now()
    current_dt = datetime.fromtimestamp(current, tz=timezone.utc)
    return current_dt >= parsed


def clock_now() -> float:
    """`bomi_ai_chat.clock` 을 지연 import 해 epoch 초를 반환한다.

    이 모듈 전체가 순수 함수를 지향하지만(브로커 없이 테스트), 만료 판정만은
    §15 의 clock 주입 규칙을 따라야 SimClock 시연에서도 일관되게 동작한다.
    """
    from bomi_ai_chat.clock import clock

    return clock.now()


def build_conversation_started(
    robot_id: str,
    command: StartConversationCommand,
    *,
    now: float | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """`CONVERSATION_STARTED` 응답 봉투를 만든다.

    무엇을 하는가
        scenarioId·conversationId·commandId 를 **최상위**로 echo-back 하고
        payload 에 intent 하나만 싣는다(계약 §6 269-281행과 동일 형태).
        commandId 는 이 대화를 시작시킨 START_CONVERSATION 명령의 ID다.

    주의사항
        - 10초 안에 발행해야 한다(계약상 expiresAt 이 occurredAt+10초). 호출부가
          이 함수를 만들어 바로 발행할 것 — 지연시키지 말 것.
    """
    timestamp = now if now is not None else clock_now()
    return {
        "eventId": event_id or uuid.uuid4().hex,
        "type": TYPE_CONVERSATION_STARTED,
        "occurredAt": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        "robotId": robot_id,
        "scenarioId": command.scenario_id,
        "conversationId": command.conversation_id,
        "commandId": command.command_id,
        "payload": {"intent": command.intent},
    }


def build_conversation_ended(
    robot_id: str,
    command: StartConversationCommand,
    outcome: str,
    reason_code: str | None,
    *,
    now: float | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """`CONVERSATION_ENDED` 응답 봉투를 만든다.

    무엇을 하는가
        scenarioId·conversationId 를 최상위로 echo-back한다. **commandId 는
        넣지 않는다** — 계약 §4 93행: "CONVERSATION_ENDED 에는 scenarioId,
        conversationId 만. 최소 형식에서는 commandId 를 넣지 않는다."

    주의사항
        - outcome 은 OUTCOMES 중 하나여야 한다(그 밖은 ContractError 유사하게
          예외를 던진다 — 서버가 조용히 버리는 대신 로봇 쪽에서 시끄럽게 죽는
          편이 낫다. bridge.contract.build_result_envelope 와 동일 원칙).
        - FAILED 면 reason_code 가 필수다. 그 외에는 선택이다(§6 314행:
          "없으면 null").
    """
    if outcome not in OUTCOMES:
        raise AiCommandError(f"disallowed CONVERSATION_ENDED outcome: {outcome}")
    if outcome == OUTCOME_FAILED and not reason_code:
        raise AiCommandError("FAILED CONVERSATION_ENDED requires a reasonCode")

    timestamp = now if now is not None else clock_now()
    return {
        "eventId": event_id or uuid.uuid4().hex,
        "type": TYPE_CONVERSATION_ENDED,
        "occurredAt": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        "robotId": robot_id,
        "scenarioId": command.scenario_id,
        "conversationId": command.conversation_id,
        "payload": {"outcome": outcome, "reasonCode": reason_code},
    }


def _as_mapping(message: Mapping[str, Any] | str | bytes) -> Mapping[str, Any]:
    """dict / JSON 문자열 / bytes 를 모두 받는다. (contracts/door.py 와 동일 패턴)"""
    if isinstance(message, Mapping):
        return message

    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AiCommandError(f"ai command is not UTF-8: {error}") from error

    try:
        decoded = json.loads(message)
    except (TypeError, ValueError) as error:
        raise AiCommandError(f"ai command is not JSON: {error}") from error

    if not isinstance(decoded, Mapping):
        raise AiCommandError(
            f"ai command must be a JSON object, got {type(decoded).__name__}"
        )
    return decoded


def _require_text(body: Mapping[str, Any], field_name: str) -> str:
    value = body.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AiCommandError(f"field {field_name!r} must be a non-empty string")
    return value


def _parse_iso_datetime(value: str) -> datetime | None:
    """ISO-8601 문자열을 tz-aware datetime 으로. 실패하면 None."""
    # 백엔드는 UTC를 RFC 3339의 `Z` 접미사로 보낸다. Python 3.11에서는
    # fromisoformat이 Z를 받지만 Jetson의 Python 3.10은 받지 않아 None으로
    # 떨어졌고, 유효한 START_CONVERSATION을 전부 만료로 오판했다.
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    # Java Instant는 나노초 9자리를 출력할 수 있지만 Python 3.10 datetime은
    # 마이크로초 6자리까지만 안전하게 받는다. 정밀도 차이는 TTL 판정에 의미가
    # 없으므로 뒤 3자리를 버린다.
    normalized = re.sub(
        r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)", r"\1", normalized
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed
