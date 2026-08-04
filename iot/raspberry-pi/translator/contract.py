"""IoT 센서 이벤트의 MQTT 계약을 정의하는 순수 모듈이다.

Zigbee2MQTT 값을 백엔드가 알아듣는 계약 형식으로 바꿀 때, "봉투(envelope)를
어떻게 채우는가"와 "어느 토픽으로 보내는가"만 담당한다. paho-mqtt 나 파일 I/O
에 의존하지 않으므로 브로커 없이 단위 테스트할 수 있다.

계약 근거: ``docs/mqtt/topic-convention.md`` (IoT → Backend 이벤트)

발행 형식 (백엔드가 수신):

``bomi/v1/iot/{sourceId}/events``

.. code-block:: json

    {
      "eventId": "…", "type": "DOOR_OPENED", "occurredAt": "…+09:00",
      "sourceId": "door-sensor-01", "payload": {"location": "ENTRANCE"}
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable
import uuid

# --- 토픽 규칙: bomi/v1/{domain}/{deviceId}/{channel} ---
DEFAULT_PREFIX = "bomi/v1"

# --- 이벤트 타입 (백엔드 MqttInboundMessageParser 의 IOT_EVENT 허용값) ---
TYPE_DOOR_OPENED = "DOOR_OPENED"
TYPE_DOOR_CLOSED = "DOOR_CLOSED"
TYPE_MOTION_DETECTED = "MOTION_DETECTED"
TYPE_AMBIENT_ENVIRONMENT_OBSERVED = "AMBIENT_ENVIRONMENT_OBSERVED"

# --- payload 필드/값 ---
LOCATION_KEY = "location"

# 백엔드 토픽/식별자 안전 규칙: [A-Za-z0-9._-] 1~64자
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_OPAQUE_ID_LENGTH = 64

# 한국 표준시(+09:00). 계약은 오프셋 포함 ISO-8601 을 요구한다.
KST = timezone(timedelta(hours=9))


def iot_events_topic(source_id: str, prefix: str = DEFAULT_PREFIX) -> str:
    """IoT 센서 → 백엔드 이벤트 토픽을 반환한다."""
    _require_safe_id(source_id, "source_id")
    return f"{prefix}/iot/{source_id}/events"


def build_event(
    source_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    now: Callable[[], datetime] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """IoT → 백엔드 이벤트 봉투를 생성한다.

    백엔드 인바운드 파서가 요구하는 필드를 채운다:

    * ``eventId``  멱등 키. 재전송 시 같은 값 유지(생성 주체 책임).
    * ``type``     허용된 이벤트 타입.
    * ``occurredAt`` 오프셋 포함 ISO-8601 (기본 KST).
    * ``sourceId`` 토픽의 deviceId 와 일치해야 함.
    * ``payload``  타입별 데이터(JSON 객체).

    테스트에서 결과를 고정하려면 ``now`` 와 ``event_id`` 를 주입한다.
    """
    _require_safe_id(source_id, "source_id")
    clock = now or (lambda: datetime.now(KST))
    eid = event_id or uuid.uuid4().hex
    if len(eid) > MAX_OPAQUE_ID_LENGTH:
        raise ValueError(f"eventId 는 {MAX_OPAQUE_ID_LENGTH}자를 넘을 수 없습니다")
    return {
        "eventId": eid,
        "type": event_type,
        "occurredAt": clock().isoformat(),
        "sourceId": source_id,
        "payload": dict(payload),
    }


def location_payload(location: str) -> dict[str, Any]:
    """문·PIR 센서 이벤트의 위치 payload 를 만든다."""
    return {LOCATION_KEY: location}


def _require_safe_id(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(
            f"{field} 는 1~64자의 토픽 안전 문자(영문/숫자/./_/-)여야 합니다"
        )
