"""백엔드와 로봇이 주고받는 MQTT 메시지 계약을 정의하는 순수 Python 모듈이다.

이 모듈은 ROS 2나 MQTT 라이브러리에 의존하지 않는다. 토픽 규칙, 명령 파싱과
검증, 결과 메시지(envelope) 생성만 담당하므로 브로커 없이 단위 테스트할 수 있다.

계약 근거:

* 토픽 규칙: ``docs/mqtt/topic-convention.md``
* 메시지 계약: S15P11E102-146 (백엔드 ``HomecomingContract`` / ``RobotCommand``)

백엔드가 명령을 발행하는 형식(로봇이 수신):

``bomi/v1/robot/{robotId}/commands``

.. code-block:: json

    {
      "commandId": "…", "scenarioId": "…-uuid", "robotId": "robot-01",
      "type": "NAVIGATE", "occurredAt": "…+09:00", "expiresAt": "…",
      "payload": {"target": "ENTRANCE"}
    }

로봇이 결과를 발행하는 형식(백엔드가 수신):

``bomi/v1/robot/{robotId}/results``

.. code-block:: json

    {
      "eventId": "…", "type": "NAVIGATION_RESULT", "occurredAt": "…+09:00",
      "robotId": "robot-01", "payload": {"scenarioId": "…-uuid", "status": "ARRIVED"}
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable
import uuid

# --- 토픽 규칙: bomi/v1/{domain}/{deviceId}/{channel} ---
TOPIC_PREFIX = "bomi/v1"


def robot_commands_topic(robot_id: str) -> str:
    """백엔드 → 로봇 명령 토픽을 반환한다."""
    return f"{TOPIC_PREFIX}/robot/{robot_id}/commands"


def robot_results_topic(robot_id: str) -> str:
    """로봇 → 백엔드 결과 토픽을 반환한다."""
    return f"{TOPIC_PREFIX}/robot/{robot_id}/results"


def robot_status_topic(robot_id: str) -> str:
    """로봇 → 백엔드 상태 토픽을 반환한다."""
    return f"{TOPIC_PREFIX}/robot/{robot_id}/status"


def iot_events_topic(sensor_id: str) -> str:
    """IoT 센서 → 백엔드 이벤트 토픽을 반환한다."""
    return f"{TOPIC_PREFIX}/iot/{sensor_id}/events"


# --- 명령 타입 (백엔드 RobotCommandType) ---
CMD_NAVIGATE = "NAVIGATE"
CMD_SPEAK = "SPEAK"
CMD_CANCEL = "CANCEL"
COMMAND_TYPES = frozenset({CMD_NAVIGATE, CMD_SPEAK, CMD_CANCEL})

# --- 결과 타입 (백엔드가 허용하는 ROBOT_RESULT 타입) ---
RESULT_NAVIGATION = "NAVIGATION_RESULT"
RESULT_SPEAK = "SPEAK_RESULT"
RESULT_CANCEL = "CANCEL_RESULT"

# --- payload 필드/값 (백엔드 HomecomingContract) ---
NAV_TARGET_KEY = "target"
TARGET_ENTRANCE = "ENTRANCE"
TARGET_DEFAULT = "DEFAULT"
SPEAK_TEXT_KEY = "text"
PAYLOAD_KEY = "payload"
RESULT_SCENARIO_ID_KEY = "scenarioId"
RESULT_STATUS_KEY = "status"

# --- 결과 상태 값 ---
STATUS_ARRIVED = "ARRIVED"
STATUS_FAILED = "FAILED"
STATUS_DONE = "DONE"
STATUS_CANCELLED = "CANCELLED"

# --- 상태 타입 (백엔드가 허용하는 ROBOT_STATUS 타입) ---
STATUS_TYPE_REST_STATE_CHANGED = "REST_STATE_CHANGED"
STATUS_TYPE_NAVIGATION = "NAVIGATION_STATUS"

# --- REST_STATE_CHANGED payload 필드/값 (백엔드 ObservationContract) ---
REST_STATE_KEY = "restState"
REST_STATE_RESTING = "RESTING"
REST_STATE_AWAKE = "AWAKE"

MAX_OPAQUE_ID_LENGTH = 64


class ContractError(ValueError):
    """메시지가 계약을 위반했을 때 발생하는 예외다."""


@dataclass(frozen=True)
class RobotCommand:
    """백엔드가 발행한 로봇 명령을 표현하는 불변 값 객체다."""

    command_id: str
    scenario_id: str
    robot_id: str
    type: str
    occurred_at: str
    expires_at: str
    payload: dict[str, Any]

    @property
    def target(self) -> str | None:
        """NAVIGATE 명령의 목적지(payload.target)를 반환한다."""
        return self.payload.get(NAV_TARGET_KEY)

    @property
    def text(self) -> str | None:
        """SPEAK 명령의 발화 문장(payload.text)을 반환한다."""
        return self.payload.get(SPEAK_TEXT_KEY)


def parse_command(raw: str | bytes) -> RobotCommand:
    """명령 JSON 문자열을 검증하고 ``RobotCommand`` 로 변환한다.

    백엔드 ``RobotCommand`` 계약의 필수 필드와 규칙을 그대로 검사한다.
    위반 시 ``ContractError`` 를 발생시킨다.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not raw or not raw.strip():
        raise ContractError("명령 payload가 비어 있습니다")

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ContractError("명령 payload가 유효한 JSON이 아닙니다") from error

    if not isinstance(body, dict):
        raise ContractError("명령 payload는 JSON 객체여야 합니다")

    command_id = _require_opaque_id(body, "commandId")
    scenario_id = _require_text(body, "scenarioId")
    robot_id = _require_text(body, "robotId")
    command_type = _require_text(body, "type")
    if command_type not in COMMAND_TYPES:
        raise ContractError(f"지원하지 않는 명령 타입입니다: {command_type}")
    occurred_at = _require_text(body, "occurredAt")
    expires_at = _require_text(body, "expiresAt")

    payload = body.get(PAYLOAD_KEY)
    if not isinstance(payload, dict):
        raise ContractError("명령 payload.payload는 JSON 객체여야 합니다")

    return RobotCommand(
        command_id=command_id,
        scenario_id=scenario_id,
        robot_id=robot_id,
        type=command_type,
        occurred_at=occurred_at,
        expires_at=expires_at,
        payload=payload,
    )


def build_result_envelope(
    robot_id: str,
    result_type: str,
    scenario_id: str,
    status: str,
    *,
    now: Callable[[], datetime] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """로봇 → 백엔드 결과 메시지(envelope)를 생성한다.

    백엔드 인바운드 파서가 요구하는 필드(eventId, type, occurredAt, robotId,
    payload)를 갖추고, payload에는 백엔드가 시나리오를 잇는 데 쓰는
    ``scenarioId`` 를 그대로 echo-back 한다.

    테스트에서 결과를 고정하려면 ``now`` 와 ``event_id`` 를 주입한다.
    """
    clock = now or (lambda: datetime.now(timezone.utc))
    return {
        "eventId": event_id or uuid.uuid4().hex,
        "type": result_type,
        "occurredAt": clock().isoformat(),
        "robotId": robot_id,
        PAYLOAD_KEY: {
            RESULT_SCENARIO_ID_KEY: scenario_id,
            RESULT_STATUS_KEY: status,
        },
    }


def build_status_envelope(
    robot_id: str,
    status_type: str,
    payload: dict[str, Any],
    *,
    now: Callable[[], datetime] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """로봇 → 백엔드 상태 메시지(envelope)를 생성한다 (REST/NAV 상태 등)."""
    clock = now or (lambda: datetime.now(timezone.utc))
    return {
        "eventId": event_id or uuid.uuid4().hex,
        "type": status_type,
        "occurredAt": clock().isoformat(),
        "robotId": robot_id,
        PAYLOAD_KEY: dict(payload),
    }


def _require_text(body: dict[str, Any], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"필드 '{field}'는 비어 있지 않은 문자열이어야 합니다")
    return value


def _require_opaque_id(body: dict[str, Any], field: str) -> str:
    value = _require_text(body, field)
    if len(value) > MAX_OPAQUE_ID_LENGTH:
        raise ContractError(f"필드 '{field}'는 {MAX_OPAQUE_ID_LENGTH}자를 넘을 수 없습니다")
    return value
