# robot/ai_chat/src/bomi_ai_chat/robot_events.py
"""로봇 이벤트 MQTT 발행 — 웨이크워드 감지를 백엔드에 알린다. (S15P11E102-349)

어디에 위치하는가
    bootstrap 의 대화 루프가 "보미야"를 감지한 직후 이 모듈로 한 건을 발행한다.
    백엔드(be-develop, S15P11E102-335)의 WakeWordDetectedHandler 가 이 이벤트를
    받아 보미야 호출 시나리오(WakeWordCallOrchestrator)를 구동한다.

왜 존재하는가
    백엔드 절반만 있는 기능은 조용히 죽어 있다. 로봇이 웨이크워드를 로컬에서만
    감지하고 발행하지 않으면, 시연에서 "보미야"를 불러도 백엔드 시나리오는 한 번도
    시작되지 않는데 로봇은 정상적으로 대화를 시작하므로 아무도 눈치채지 못한다 —
    현관 인사(226)가 겪은 "만들어 놓고 아무도 안 부르는" 유형과 같다.

계약 (백엔드 코드가 권위다 — MqttInboundMessageParser, WakeWordDetectedHandler)
    토픽   bomi/v1/robot/{robotId}/events        (MqttTopics.ROBOT_EVENTS)
    봉투   {"type": "WAKE_WORD_DETECTED",
            "eventId": "<uuid>",
            "occurredAt": "<ISO-8601, 오프셋 포함>",
            "robotId": "<토픽의 {robotId} 와 동일한 deviceId>",
            "payload": {"keyword": "보미야", "confidence": <선택>}}
    ★ robotId 는 본문에도 반드시 넣는다. 파서(MqttInboundMessageParser.java:69-77)가
      ROBOT_EVENT 카테고리에 최상위 robotId 를 요구하고 토픽 값과 대조한다 — 없으면
      경고 로그 한 줄 남기고 조용히 폐기하므로, 로봇은 성공한 줄 알고 시나리오만 죽는다.
    ★ QoS 1 로 발행한다. 백엔드 인바운드는 QoS 1 만 받는다(그 외 폐기, 역시 조용히).
    ★ ROBOT_ID 는 deviceId 공간(robot.device_id, 예: bomi-AA001)이다. REST 온보딩이
      쓰는 robot UUID 와 다른 값이다 — 혼용하면 UNKNOWN_ROBOT 으로 조용히 차단된다.

주의사항
    - 발행 실패가 대화를 막으면 안 된다. 시나리오는 부가 기능이고 대화가 본체다.
      모든 실패는 경고 로그로 삼킨다.
    - door/mqtt.py 의 구독자와 연결 설정(브로커 URL·TLS·자격증명)을 공유하지만
      책임은 별개다 — 구독이 죽어도 발행은 살고, 그 반대도 같다.

참고
    CLAUDE.md §24 (웨이크워드 MQTT 발행), docs/mqtt/topic-convention.md
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from bomi_ai_chat.clock import clock
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.door.mqtt import _parse_broker_url

logger = logging.getLogger(__name__)

# 백엔드 허용 목록(MqttInboundMessageParser)의 타입 문자열. 바꾸면 서버가 거절한다.
WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"

# 감지 모델(bomiya.onnx)이 듣는 호출어. 페이로드의 keyword 필드로 나간다.
WAKE_KEYWORD = "보미야"


class RobotEventPublisher:
    """로봇 이벤트를 브로커에 발행한다. 연결 관리는 paho 에 맡긴다."""

    def __init__(self, settings: Settings, *, client=None):
        self.settings = settings
        # 테스트는 가짜 클라이언트를 주입한다. 실기에서는 start() 가 만든다.
        self._client = client

    # ── 연결: 실기에서만 쓰는 부분 ──────────────────────────────────────────

    def start(self) -> None:
        """브로커에 붙는다. door/mqtt.py 의 구독자와 같은 방식(loop_start 재연결).

        실패해도 예외를 올리지 않는다 — 브로커가 없는 개발 환경에서 대화가
        멈추면 안 된다. publish() 쪽이 클라이언트 부재를 조용히 넘긴다.
        """
        if self._client is not None:
            return
        try:
            from paho.mqtt import client as mqtt_client

            host, port, use_tls = _parse_broker_url(self.settings.mqtt_broker_url)
            client = mqtt_client.Client(
                client_id=f"{self.settings.mqtt_client_id}-events")
            if self.settings.mqtt_username:
                client.username_pw_set(
                    self.settings.mqtt_username, self.settings.mqtt_password)
            if use_tls:
                client.tls_set()
            client.connect(host, port)
            client.loop_start()
            self._client = client
            logger.info("robot event publisher connected to %s:%d (tls=%s)",
                        host, port, use_tls)
        except Exception:  # noqa: BLE001 - 발행 채널 실패가 대화를 막으면 안 된다
            logger.warning("robot event publisher could not connect; "
                           "wake events will not reach the backend", exc_info=True)

    def stop(self) -> None:
        if self._client is None:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001 - 종료 정리 실패는 무시한다
            logger.debug("robot event publisher stop failed", exc_info=True)
        self._client = None

    # ── 발행 ────────────────────────────────────────────────────────────────

    def publish_wake_word(self, *, confidence: float | None = None) -> None:
        """웨이크워드 감지 한 건을 발행한다. 실패는 삼킨다."""
        if self._client is None:
            # start() 가 실패했거나 아예 안 불렸다. 시나리오만 조용히 빠진다 —
            # 그 사실은 start() 가 이미 경고로 남겼다.
            return
        # ★ deviceId 다. robot_id(UUID)를 넣으면 백엔드가 UNKNOWN_ROBOT 으로
        #   조용히 차단한다 — config.py 의 robot_device_id 주석 참고.
        robot_id = self.settings.robot_device_id or ""
        topic = f"bomi/v1/robot/{robot_id}/events"

        # occurredAt 은 오프셋이 붙은 ISO-8601 이어야 한다(서버 파서가 요구).
        # clock 을 경유한다 — §15. UTC 로 보내면 서버(OffsetDateTime)가 알아서 읽는다.
        occurred_at = datetime.fromtimestamp(
            clock.now(), tz=timezone.utc).isoformat()

        payload: dict = {"keyword": WAKE_KEYWORD}
        if confidence is not None:
            payload["confidence"] = confidence
        # robotId 는 토픽과 본문 양쪽에 있어야 한다 — 파서가 대조 후 불일치·부재를
        # 조용히 폐기한다. scenarioId/commandId 류는 최초 트리거라 넣지 않는다(넣으면 거부).
        envelope = {
            "type": WAKE_WORD_DETECTED,
            "eventId": str(uuid.uuid4()),
            "occurredAt": occurred_at,
            "robotId": robot_id,
            "payload": payload,
        }
        try:
            # QoS 1: 백엔드가 QoS 0 을 계약 위반으로 폐기한다. 중복 전달은 서버의
            # eventId 멱등 처리(WakeWordTriggerReceipt)가 흡수하므로 안전하다.
            self._client.publish(
                topic, json.dumps(envelope, ensure_ascii=False), qos=1)
            logger.info("WAKE_WORD_DETECTED published (robot=%s)", robot_id)
        except Exception:  # noqa: BLE001 - 발행 실패가 대화를 막으면 안 된다
            logger.warning("failed to publish WAKE_WORD_DETECTED", exc_info=True)


def build_robot_event_publisher(
    settings: Settings | None = None,
) -> RobotEventPublisher | None:
    """설정이 갖춰져 있으면 발행자를 만든다. 시작하지는 않는다.

    반환값
        RobotEventPublisher, 또는 None(비활성).

    주의사항
        None 을 돌려줄 때 이유를 로그로 남긴다. "보미야 호출 시나리오가 왜 한 번도
        안 도는가"를 나중에 조사할 때, 여기서 꺼져 있었다는 사실이 보여야 한다.
    """
    settings = settings or get_settings()
    if not settings.mqtt_enabled:
        logger.info("MQTT is disabled; wake-word events will not be published "
                    "(the 보미야-호출 backend scenario will never fire)")
        return None
    if not settings.mqtt_broker_url:
        logger.warning("MQTT_BROKER_URL is missing; wake-word events disabled")
        return None
    if not settings.robot_device_id:
        logger.warning("ROBOT_DEVICE_ID is missing; wake-word events disabled — "
                       "the backend cannot attribute events without it "
                       "(this is the MQTT deviceId, e.g. bomi-AA001, "
                       "NOT the robot UUID)")
        return None
    return RobotEventPublisher(settings)
