"""백엔드와 로봇이 주고받는 MQTT 메시지 계약을 정의하는 순수 Python 모듈이다.

이 모듈은 ROS 2나 MQTT 라이브러리에 의존하지 않는다. 토픽 규칙, 명령 파싱과
검증, 결과 메시지(envelope) 생성만 담당하므로 브로커 없이 단위 테스트할 수 있다.

계약 근거 — **v1 (scenario-contract-v1.md) 이 정본이고, 백엔드 파서 코드가 최종
권위다** (``MqttInboundMessageParser.java``). 과거의 legacy 결과 형식
(``payload: {scenarioId, status}``)은 파서는 아직 받아주지만 보미야 호출
orchestrator 가 거부하므로 더 이상 사용하지 않는다.

백엔드가 명령을 발행하는 형식(로봇이 수신):

``bomi/v1/robot/{robotId}/commands``

.. code-block:: json

    {
      "commandId": "…", "scenarioId": "…-uuid", "robotId": "robot-01",
      "type": "NAVIGATE", "occurredAt": "…+09:00", "expiresAt": "…+09:00",
      "payload": {"target": "LIVING_ROOM"}
    }

로봇이 결과를 발행하는 형식(백엔드가 수신) — **v1**. 상관관계 ID 는 전부
최상위이고, payload 는 outcome/resultCode/reasonCode 세 필드다:

``bomi/v1/robot/{robotId}/results``

.. code-block:: json

    {
      "eventId": "…", "type": "NAVIGATION_RESULT", "occurredAt": "…+00:00",
      "robotId": "robot-01", "scenarioId": "…-uuid", "commandId": "…",
      "payload": {"outcome": "SUCCEEDED", "resultCode": "ARRIVED", "reasonCode": null}
    }

백엔드 파서가 조용히 폐기하는 것들 (에러 응답 없음 — 어기면 로봇은 성공한 줄 안다):

* payload 에 outcome/resultCode/reasonCode/location/message 외의 필드
* ``reasonCode`` 키 자체가 없는 payload (값 null 은 허용, 키 부재는 거부)
* enum 밖의 reasonCode — 허용값은 문서(11개)가 아니라 코드 기준 7개다 (아래 REASON_*)
* SUCCEEDED 인데 ARRIVED+null 이 아닌 조합 / 비성공인데 NOT_ARRIVED+reason 이 아닌 조합
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


# --- 명령 타입 (백엔드 RobotCommandType — 5개 전부) ---
CMD_NAVIGATE = "NAVIGATE"
CMD_SPEAK = "SPEAK"
CMD_CANCEL = "CANCEL"
# 산책 시나리오의 따라가기 명령. 시연 범위에서는 보류지만, 백엔드가 보낼 수 있는
# 타입이므로 계약에는 있어야 한다 — 모르는 타입으로 버리면 백엔드의 10초 ACK
# 타임아웃이 무응답으로 터지고 로봇이 SAFE_STOP 에 잠긴다(CLAUDE.md §3).
CMD_FOLLOW_START = "FOLLOW_START"
CMD_FOLLOW_STOP = "FOLLOW_STOP"
COMMAND_TYPES = frozenset(
    {CMD_NAVIGATE, CMD_SPEAK, CMD_CANCEL, CMD_FOLLOW_START, CMD_FOLLOW_STOP}
)

# --- 결과 타입 (백엔드가 허용하는 ROBOT_RESULT 타입) ---
RESULT_NAVIGATION = "NAVIGATION_RESULT"
RESULT_SPEAK = "SPEAK_RESULT"
RESULT_CANCEL = "CANCEL_RESULT"
RESULT_FOLLOW = "FOLLOW_RESULT"

# --- payload 필드/값 ---
NAV_TARGET_KEY = "target"
TARGET_ENTRANCE = "ENTRANCE"
TARGET_DEFAULT = "DEFAULT"
TARGET_LIVING_ROOM = "LIVING_ROOM"
# 백엔드 RobotCommand 가 검증하는 NAVIGATE 목적지 전체. 이 밖의 값은 백엔드가
# 아예 발행하지 못하지만, 방어적으로 로봇 쪽에서도 같은 표를 기준으로 삼는다.
NAVIGATION_TARGETS = frozenset({TARGET_ENTRANCE, TARGET_DEFAULT, TARGET_LIVING_ROOM})
SPEAK_TEXT_KEY = "text"
PAYLOAD_KEY = "payload"

# --- 드라이버 내부 상태 값 (RobotDriver 가 반환; MQTT 로 나가지 않는다) ---
# v1 이전에는 이 값이 그대로 payload.status 로 나갔다. 지금은 브릿지가 이 내부
# 상태를 아래 v1 어휘(outcome/resultCode/reasonCode)로 번역해서 발행한다.
STATUS_ARRIVED = "ARRIVED"
STATUS_FAILED = "FAILED"
STATUS_DONE = "DONE"
STATUS_CANCELLED = "CANCELLED"

# --- v1 결과 어휘 (MqttInboundMessageParser 허용값과 1:1) ---
OUTCOME_SUCCEEDED = "SUCCEEDED"
OUTCOME_FAILED = "FAILED"
OUTCOME_CANCELLED = "CANCELLED"
OUTCOME_TIMED_OUT = "TIMED_OUT"
OUTCOMES = frozenset(
    {OUTCOME_SUCCEEDED, OUTCOME_FAILED, OUTCOME_CANCELLED, OUTCOME_TIMED_OUT}
)

# resultCode — 결과 타입별 허용값 (백엔드 §7.1 표와 동일)
CODE_ARRIVED = "ARRIVED"
CODE_NOT_ARRIVED = "NOT_ARRIVED"
CODE_SPOKEN = "SPOKEN"
CODE_NOT_SPOKEN = "NOT_SPOKEN"
CODE_TARGET_CANCELLED = "TARGET_CANCELLED"
CODE_TARGET_UNCHANGED = "TARGET_UNCHANGED"
CODE_STARTED = "STARTED"
CODE_STOPPED = "STOPPED"
CODE_UNCHANGED = "UNCHANGED"

# reasonCode — ★ 문서에는 11개가 적혀 있지만 백엔드 파서 코드는 NAVIGATION 에
# 아래 7개만 허용한다(그 외는 통째로 폐기). FOLLOW 는 이 중 PERSON_LOST 를
# 더한 5개(PERSON_LOST/COMMAND_EXPIRED/EXECUTION_TIMEOUT/SAFETY_STOP/
# INTERNAL_ERROR)다. 새 값을 쓰고 싶으면 백엔드 코드부터 확인하라.
REASON_COMMAND_EXPIRED = "COMMAND_EXPIRED"
REASON_UNKNOWN_TARGET = "UNKNOWN_TARGET"
REASON_PATH_BLOCKED = "PATH_BLOCKED"
REASON_LOCALIZATION_LOST = "LOCALIZATION_LOST"
REASON_EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
REASON_SAFETY_STOP = "SAFETY_STOP"
REASON_INTERNAL_ERROR = "INTERNAL_ERROR"
REASON_PERSON_LOST = "PERSON_LOST"

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
    # 파싱 가능 여부를 여기서 확정한다. 실행 시점에 처음 파싱하다 실패하면
    # "만료 판정 불가 = 실행" 같은 애매한 상태가 생긴다. 형식이 깨진 expiresAt 은
    # 계약 위반으로 명령 자체를 거절하는 편이 안전하다.
    if _parse_iso_datetime(expires_at) is None:
        raise ContractError(
            f"필드 'expiresAt'가 ISO-8601 형식이 아닙니다: {expires_at}"
        )

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


def command_expired(
    command: RobotCommand, *, now: Callable[[], datetime] | None = None
) -> bool:
    """명령의 expiresAt 이 지났는지 판정한다.

    무엇을 하는가
        expiresAt(ISO-8601)을 파싱해 현재 시각과 비교한다. QoS 1 재전송이나
        오프라인 큐잉으로 몇 분 늦게 도착한 "현관으로 가라"가 그대로 주행으로
        이어지는 것을 막는 유일한 방어선이다 — 이 검사가 없던 시절의 브릿지는
        2년 전에 만료된 명령도 실행했다.

    반환값
        만료됐으면 True. 파싱 불가면 True (parse_command 가 형식을 이미
        검증하므로 정상 경로에서는 도달하지 않지만, 판정 불가를 실행으로
        기울이지 않는다 — 안전 쪽으로 넘어진다).
    """
    parsed = _parse_iso_datetime(command.expires_at)
    if parsed is None:
        return True
    clock = now or (lambda: datetime.now(timezone.utc))
    current = clock()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current >= parsed


def build_result_envelope(
    robot_id: str,
    result_type: str,
    scenario_id: str,
    command_id: str,
    outcome: str,
    result_code: str,
    reason_code: str | None,
    *,
    now: Callable[[], datetime] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """로봇 → 백엔드 v1 결과 메시지(envelope)를 생성한다.

    무엇을 하는가
        상관관계 ID(scenarioId, commandId)를 **최상위**에 echo-back 하고
        payload 에 {outcome, resultCode, reasonCode} 세 필드만 싣는다.
        백엔드 파서는 화이트리스트 방식이라 필드 하나만 더 있어도 통째로
        폐기한다 — 여기서 만드는 형태가 허용되는 전부다.

    주의사항
        - reasonCode 는 값이 null 이어도 **키가 반드시 존재**해야 한다.
        - 교차 제약(SUCCEEDED→reason 없음 / 비성공→reason 필수)을 여기서
          검증한다. 서버는 위반을 '조용히' 버리므로, 로봇 쪽 버그는 여기서
          시끄럽게(ContractError) 죽는 편이 낫다.

    테스트에서 결과를 고정하려면 ``now`` 와 ``event_id`` 를 주입한다.
    """
    if outcome not in OUTCOMES:
        raise ContractError(f"허용되지 않는 outcome 입니다: {outcome}")
    if outcome == OUTCOME_SUCCEEDED and reason_code is not None:
        raise ContractError("SUCCEEDED 결과의 reasonCode 는 null 이어야 합니다")
    if outcome != OUTCOME_SUCCEEDED and not reason_code:
        raise ContractError(f"{outcome} 결과에는 reasonCode 가 필요합니다")

    clock = now or (lambda: datetime.now(timezone.utc))
    return {
        "eventId": event_id or uuid.uuid4().hex,
        "type": result_type,
        "occurredAt": clock().isoformat(),
        "robotId": robot_id,
        "scenarioId": scenario_id,
        "commandId": command_id,
        PAYLOAD_KEY: {
            "outcome": outcome,
            "resultCode": result_code,
            "reasonCode": reason_code,
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


def _parse_iso_datetime(value: str) -> datetime | None:
    """ISO-8601 문자열을 tz-aware datetime 으로 파싱한다. 실패 시 None.

    백엔드는 항상 오프셋(+09:00 등)을 붙여 보낸다. 오프셋이 없는 값은
    시계 비교가 무의미하므로 파싱 실패로 취급한다.

    끝의 ``Z``(UTC)는 ``+00:00`` 으로 바꿔서 넘긴다 — 젯슨(Ubuntu 22.04)의
    Python 3.10 ``fromisoformat`` 은 ``Z`` 를 못 읽어서, 이 변환이 없으면
    UTC 표기로 온 명령이 전부 "형식 오류"로 거절된다.
    """
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


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
