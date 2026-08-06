"""Zigbee2MQTT 센서 값을 계약 이벤트로 바꾸는 순수 매핑 로직이다.

MQTT 나 파일 I/O 에 의존하지 않는다. "이 센서의 이번 메시지가 어떤 계약
이벤트를 내야 하는가"만 판단하므로 브로커 없이 단위 테스트할 수 있다.

핵심 규칙(엣지 트리거):

* **retained 메시지는 이벤트를 내지 않는다.** 브로커에 남아 있던 현재 상태가
  번역기 재시작 때 재수신되며 시나리오를 잘못 시작시키는 것을 막는다.
  상태(prev)만 갱신한다.
* 문(``contact``): 상태가 바뀌는 순간 열림은 ``DOOR_OPENED``, 닫힘은
  ``DOOR_CLOSED`` 를 낸다. 같은 상태 반복 메시지는 무시한다.
* PIR(``occupancy``): ``false`` → ``true`` 로 바뀌는 순간에만
  ``MOTION_DETECTED`` 를 낸다.
* 배터리·링크품질만 담긴 메시지처럼 해당 키가 없으면 상태를 바꾸지 않고 무시한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import contract

KIND_DOOR = "door"
KIND_PIR = "pir"

# Zigbee2MQTT payload 키
CONTACT_KEY = "contact"      # true=닫힘, false=열림
OCCUPANCY_KEY = "occupancy"  # true=움직임 감지


def map_message(
    sensor: dict[str, Any],
    data: dict[str, Any],
    prev: dict[str, Any] | None,
    *,
    retained: bool = False,
    now: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """센서 설정 + 이번 Zigbee 메시지 → (계약 이벤트 또는 None, 갱신된 상태).

    Args:
        sensor: config 의 센서 항목(``kind``/``source_id``/``location``).
        data: Zigbee2MQTT 메시지를 파싱한 dict (예: ``{"contact": False}``).
        prev: 이 센서의 직전 상태. 최초에는 ``None``.
        retained: 브로커 retained 메시지 여부. True 면 상태만 갱신하고 발행 안 함.
        now: 시각 주입(테스트용).

    Returns:
        (event, new_prev). event 가 None 이면 발행할 것이 없다.
    """
    prev = dict(prev) if prev else {}
    kind = sensor.get("kind")

    if kind == KIND_DOOR:
        return _map_door(sensor, data, prev, retained=retained, now=now)
    if kind == KIND_PIR:
        return _map_edge(
            sensor, data, prev,
            key=OCCUPANCY_KEY, active_value=True,  # occupancy=true 가 "감지"
            event_type=contract.TYPE_MOTION_DETECTED,
            payload_fn=lambda: contract.location_payload(sensor["location"]),
            retained=retained, now=now,
        )

    # 알 수 없는 종류는 무시(상태 변경 없음).
    return None, prev


def _map_door(
    sensor: dict[str, Any],
    data: dict[str, Any],
    prev: dict[str, Any],
    *,
    retained: bool,
    now: Callable[[], datetime] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """문 상태가 바뀔 때 열림/닫힘 이벤트를 각각 만든다."""
    if CONTACT_KEY not in data:
        return None, prev

    current = data[CONTACT_KEY]
    previous = prev.get(CONTACT_KEY)
    prev[CONTACT_KEY] = current

    if type(current) is not bool or retained or current == previous:
        return None, prev

    # 최초 fresh 닫힘은 기준 상태만 확립한다. 열림은 기존 동작대로 즉시 알린다.
    if previous is None and current is True:
        return None, prev

    event_type = (
        contract.TYPE_DOOR_CLOSED if current is True else contract.TYPE_DOOR_OPENED
    )
    event = contract.build_event(
        sensor["source_id"],
        event_type,
        contract.location_payload(sensor["location"]),
        now=now,
    )
    return event, prev


def _map_edge(
    sensor: dict[str, Any],
    data: dict[str, Any],
    prev: dict[str, Any],
    *,
    key: str,
    active_value: Any,
    event_type: str,
    payload_fn: Callable[[], dict[str, Any]],
    retained: bool,
    now: Callable[[], datetime] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """지정한 키가 비활성→활성으로 전이할 때만 이벤트를 내는 공통 엣지 판정."""
    if key not in data:
        # 이번 메시지에 관심 키가 없다(배터리 등) → 상태 유지, 무시.
        return None, prev

    current = data[key]
    previous = prev.get(key)
    prev[key] = current  # 상태는 항상 갱신

    if retained:
        # 재시작 시 재수신되는 현재 상태 → 발행하지 않는다.
        return None, prev

    became_active = current == active_value and previous != active_value
    if not became_active:
        return None, prev

    event = contract.build_event(
        sensor["source_id"], event_type, payload_fn(), now=now
    )
    return event, prev
