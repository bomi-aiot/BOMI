"""온습도 측정값을 백엔드 MQTT 계약 이벤트로 발행하는 코어."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Callable

import contract

PublishFn = Callable[[str, str], None]


class AmbientPublisher:
    """검증된 DHT 측정값을 ``AMBIENT_ENVIRONMENT_OBSERVED``로 변환한다."""

    def __init__(
        self,
        source_id: str,
        location: str,
        publish: PublishFn,
        *,
        prefix: str = contract.DEFAULT_PREFIX,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_id = source_id
        self._location = location
        self._publish = publish
        self._prefix = prefix
        self._now = now

    def publish_observation(self, temperature: float, humidity: float) -> bool:
        """정상 범위의 측정값만 발행하고 발행 여부를 반환한다.

        DHT11 데이터시트 범위인 0~50°C, 20~90% RH를 적용한다.
        """
        if not self._valid_number(temperature) or not self._valid_number(humidity):
            return False
        if not 0 <= temperature <= 50 or not 20 <= humidity <= 90:
            return False

        payload = contract.ambient_payload(
            self._location,
            round(float(temperature), 1),
            round(float(humidity), 1),
        )
        event = contract.build_event(
            self._source_id,
            contract.TYPE_AMBIENT_ENVIRONMENT_OBSERVED,
            payload,
            now=self._now,
        )
        topic = contract.iot_events_topic(self._source_id, self._prefix)
        self._publish(topic, json.dumps(event, ensure_ascii=False))
        return True

    @staticmethod
    def _valid_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
