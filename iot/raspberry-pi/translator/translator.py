"""Zigbee2MQTT ↔ 백엔드 계약을 잇는 번역기 코어다.

paho-mqtt 에 직접 의존하지 않는다. "메시지를 발행하는 방법"을 ``publish``
콜백으로 주입받으므로, 테스트에서는 리스트 수집기로, 운영에서는 paho 발행
함수로 바꿔 끼울 수 있다(로봇 브릿지 MqttBridge 와 같은 패턴).

흐름:

``zigbee2mqtt/<name> 수신 → 센서 조회 → mapping(엣지 판정) → 계약 이벤트 발행``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

import contract
import mapping

logger = logging.getLogger(__name__)

# 발행 콜백 형태: (topic, payload_json) -> None
PublishFn = Callable[[str, str], None]


class Translator:
    """Zigbee2MQTT 메시지를 계약 이벤트로 통역하는 코어다."""

    def __init__(
        self,
        config: dict[str, Any],
        publish: PublishFn,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._publish = publish
        self._now = now
        topics = config.get("topics", {})
        self._zigbee_base = topics.get("zigbee2mqtt_base", "zigbee2mqtt")
        self._prefix = topics.get("contract_prefix", contract.DEFAULT_PREFIX)
        # friendly_name -> 센서 설정
        self._sensors: dict[str, dict[str, Any]] = {
            s["friendly_name"]: s for s in config.get("sensors", [])
        }
        # friendly_name -> 직전 상태(엣지 판정용)
        self._state: dict[str, dict[str, Any]] = {}

    @property
    def subscribe_topic(self) -> str:
        """구독해야 하는 Zigbee2MQTT 와일드카드 토픽."""
        return f"{self._zigbee_base}/#"

    def on_zigbee_message(
        self, topic: str, payload: str | bytes, retained: bool = False
    ) -> None:
        """Zigbee2MQTT 메시지 하나를 처리한다.

        등록되지 않은 센서, 관심 없는 하위 토픽, 파싱 불가 payload 는 조용히
        무시한다(재전송 폭주 방지). 상태 전이가 확정되면 계약 이벤트를 발행한다.
        """
        friendly = self._friendly_name(topic)
        sensor = self._sensors.get(friendly)
        if sensor is None:
            return  # 우리가 담당하지 않는 토픽/센서

        data = self._parse(payload)
        if data is None:
            return

        event, new_state = mapping.map_message(
            sensor,
            data,
            self._state.get(friendly),
            retained=retained,
            now=self._now,
        )
        self._state[friendly] = new_state

        if event is None:
            return

        out_topic = contract.iot_events_topic(sensor["source_id"], self._prefix)
        self._publish(out_topic, json.dumps(event, ensure_ascii=False))
        logger.info("계약 이벤트 발행: type=%s source=%s", event["type"], sensor["source_id"])

    def _friendly_name(self, topic: str) -> str:
        """``zigbee2mqtt/door-sensor-01`` → ``door-sensor-01``.

        Zigbee2MQTT 의 하위 상태 토픽(예: .../availability)은 friendly_name 이
        아니므로 센서 조회에서 자연히 걸러진다.
        """
        base = f"{self._zigbee_base}/"
        if not topic.startswith(base):
            return ""
        return topic[len(base):]

    def _parse(self, payload: str | bytes) -> dict[str, Any] | None:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.debug("JSON 이 아닌 payload 무시")
            return None
        if not isinstance(data, dict):
            return None
        return data
