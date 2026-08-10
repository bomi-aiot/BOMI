# robot/ai_chat/src/bomi_ai_chat/ai_commands.py
"""백엔드 대화 명령 MQTT 어댑터 — `START_CONVERSATION` 을 받아 그래프로 넘긴다.

어디에 위치하는가
    현관 인사·복약 알림·온습도 안부, 세 시나리오가 이 경로를 쓴다(보미야 호출은
    로봇이 자체적으로 대화를 시작하므로 이 경로를 타지 않는다 — 계약 §2.2).
    백엔드가 `NAVIGATE` 로 로봇을 옮긴 뒤 도착하면 이 토픽으로 명령을 보낸다.

왜 door/mqtt.py 처럼 얇지 않은가
    현관 이벤트는 사실 하나를 반영하고 끝이지만, 이 명령은 **대화**다 — 첫
    문장을 말하고, 마이크를 열어 답을 듣고, 자연스러운 종료까지 이어가야
    한다. 그 실행(청취·재생)은 물리 마이크를 쥐고 있는 bootstrap 의 메인
    루프만 할 수 있다. 그래서 이 모듈은 **수신·검증·즉시 응답(ACK)** 까지만
    하고, 실제 대화 진행은 큐에 넘겨 메인 루프에 위임한다.

    이 분리가 없으면 paho 콜백 스레드가 마이크를 열게 되고, 메인 루프의
    웨이크워드 감지도 같은 마이크를 쓰므로 두 스레드가 오디오 장치를 두고
    충돌한다(sounddevice 는 동시 입력 스트림을 지원하지 않는다).

큐를 쓰는 이유 (스레드 경계)
    paho 콜백 스레드 -> [PendingConversation 큐] -> 메인 루프 스레드.
    큐가 가득 차면(운영에서는 사실상 불가능 — 동시에 여러 대화가 걸릴 일이
    없다) 새 명령을 버린다. 버리는 것이 블로킹보다 안전하다 — 콜백 스레드가
    막히면 이후 모든 MQTT 메시지 처리가 멈춘다.

CONVERSATION_STARTED 를 왜 여기서(수신 스레드) 바로 발행하는가
    계약상 10초 안에 보내야 한다. 메인 루프가 마침 다른 반응형 턴을 처리
    중이면 그 안에서 대기가 생길 수 있어, ACK 만은 수신 즉시 이 스레드에서
    끝낸다. CONVERSATION_ENDED 는 실제 대화가 끝난 뒤 메인 루프가
    publish_conversation_ended() 를 불러 보낸다.

참고
    CLAUDE.md §2(계약 요약), §3(안전), docs/mqtt/scenario-contract-v1.md §6
    door/mqtt.py (같은 paho 배선 패턴), bridge/mqtt_bridge.py (같은 dedup 패턴)
"""

from __future__ import annotations

import json
import logging
import os
import queue
import time
from collections import OrderedDict
from json import dumps as _json_dumps

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.contracts import ai_commands as contract
from bomi_ai_chat.door.mqtt import _parse_broker_url

logger = logging.getLogger(__name__)

# commandId 중복 제거 상한. bridge.mqtt_bridge 의 SEEN_COMMANDS_MAX 와 같은
# 이유 — QoS 1 재전송이 정상 동작이고, 이 창을 벗어난 아주 늦은 재전송까지
# 잡을 필요는 없다.
SEEN_COMMANDS_MAX = 64

# 메인 루프가 아직 이전 대화를 처리 중일 때 새로 도착하는 명령을 얼마나 쌓아
# 둘지. 운영에서는 동시에 여러 대화가 겹칠 일이 거의 없으므로 작게 잡는다 —
# 크게 잡으면 오래된(이미 의미 없어진) 명령이 뒤늦게 처리되는 쪽이 더 위험하다.
QUEUE_MAX_SIZE = 4

AMBIENT_EVENT_TYPE = "AMBIENT_ENVIRONMENT_OBSERVED"
AMBIENT_TOPIC = "bomi/v1/iot/+/events"


class HomecomingAmbientContext:
    """귀가 인사에 사용할 최근 온습도 관측값을 보관한다."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("HOMECOMING_AMBIENT_ENABLED", "false").lower() in (
            "1", "true", "yes",
        )
        self.hot_threshold_c = float(os.environ.get("HOMECOMING_HOT_THRESHOLD_C", "30"))
        self.max_age_sec = float(os.environ.get("HOMECOMING_AMBIENT_MAX_AGE_SEC", "90"))
        self.temperature_c: float | None = None
        self.humidity_percent: float | None = None
        self.received_at: float | None = None

        # 실물 센서 없이 대화만 확인할 때 사용하는 명시적 테스트 값이다.
        test_temperature = os.environ.get("HOMECOMING_AMBIENT_TEST_TEMPERATURE_C")
        if self.enabled and test_temperature:
            self.temperature_c = float(test_temperature)
            self.received_at = time.monotonic()

    def handle_payload(self, raw: bytes | str) -> bool:
        if not self.enabled:
            return False
        try:
            body = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if body.get("type") != AMBIENT_EVENT_TYPE:
                return False
            payload = body.get("payload") or {}
            temperature = payload.get("temperatureC")
            humidity = payload.get("humidityPercent")
            if temperature is None:
                return False
            self.temperature_c = float(temperature)
            self.humidity_percent = float(humidity) if humidity is not None else None
            self.received_at = time.monotonic()
            logger.info(
                "latest ambient context updated: temperature=%.1fC humidity=%s%%",
                self.temperature_c, self.humidity_percent,
            )
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("dropping malformed ambient event for homecoming context")
            return False

    def conversation_text(self) -> str | None:
        if (
            not self.enabled
            or self.temperature_c is None
            or self.received_at is None
            or time.monotonic() - self.received_at > self.max_age_sec
        ):
            return None

        temperature = f"{self.temperature_c:g}"
        humidity = (
            f" 습도는 {self.humidity_percent:g}%예요."
            if self.humidity_percent is not None else ""
        )
        if self.temperature_c >= self.hot_threshold_c:
            return (
                f"할머니, 지금 실내 온도가 {temperature}도로 조금 높아요."
                f"{humidity} 더우시진 않으세요?"
            )
        return (
            f"할머니, 지금 실내 온도는 {temperature}도예요."
            f"{humidity} 지금은 괜찮은 편이에요."
        )


class AiCommandSubscriber:
    """`bomi/v1/ai/{robotId}/commands` 를 구독해 대화 명령을 큐에 넘긴다."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        pending_queue: queue.Queue[contract.StartConversationCommand],
        client=None,
    ):
        self.settings = settings or get_settings()
        self.pending_queue = pending_queue
        self._client = client
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._ambient = HomecomingAmbientContext()

    # ── 메시지 처리: 브로커 없이도 테스트할 수 있는 부분 ──────────────────────

    def handle_payload(self, raw: bytes | str) -> bool:
        """명령 하나를 처리한다. 예외를 던지지 않는다.

        반환값
            True  큐에 넘겼다(= 메인 루프가 이어서 대화를 진행한다).
            False 버렸다. 이유는 로그에 남는다.

        처리 순서
            파싱 -> robotId 일치 확인 -> commandId 중복 제거 -> 만료 확인 ->
            CONVERSATION_STARTED 즉시 발행 -> 큐에 적재.

        주의사항
            만료된 명령에는 아무것도 응답하지 않는다. CONVERSATION_STARTED 를
            보내지 않으면 백엔드의 10초 워치독(AiConversationTimeoutWatchdog)이
            스스로 AI_START_TIMEOUT 으로 정리한다 — 여기서 새 실패 의미를
            더 만들 필요가 없다.
        """
        try:
            command = contract.parse_start_conversation(raw)
        except contract.AiCommandError as error:
            logger.warning("dropping a malformed START_CONVERSATION: %s", error)
            return False

        expected_robot_id = self.settings.robot_device_id
        if expected_robot_id and command.robot_id != expected_robot_id:
            logger.warning(
                "START_CONVERSATION robotId %r does not match ours %r; dropping",
                command.robot_id, expected_robot_id,
            )
            return False

        if command.command_id in self._seen:
            logger.info("duplicate START_CONVERSATION commandId=%s; ignoring",
                        command.command_id)
            return False
        self._remember(command.command_id)

        if contract.command_expired(command):
            logger.warning(
                "START_CONVERSATION already expired (commandId=%s, expiresAt=%s); "
                "not starting — the backend's own ack watchdog will time it out",
                command.command_id, command.expires_at,
            )
            return False

        self._publish_started(command)

        try:
            self.pending_queue.put_nowait(command)
        except queue.Full:
            # 메인 루프가 이미 대화를 여럿 밀린 채 처리 중이라는 뜻이다. 여기서
            # 블로킹하면 이후 모든 MQTT 메시지가 멈춘다 — 이번 요청만 포기한다.
            logger.error(
                "backend conversation queue is full; dropping commandId=%s "
                "(CONVERSATION_STARTED already sent — the conversation will "
                "silently never happen; this needs investigation)",
                command.command_id,
            )
            return False

        return True

    def publish_conversation_ended(
        self,
        command: contract.StartConversationCommand,
        outcome: str,
        reason_code: str | None = None,
    ) -> None:
        """대화가 끝났음을 백엔드에 알린다. 메인 루프가 대화 종료 후 호출한다.

        실패해도 예외를 올리지 않는다 — 이 시점엔 대화 자체는 이미 끝났고,
        발행 실패로 다시 대화를 되돌릴 방법이 없다. 로그가 유일한 흔적이다
        (백엔드는 5분 대화 워치독으로 결국 정리한다).
        """
        if self._client is None:
            logger.warning(
                "no MQTT client to publish CONVERSATION_ENDED (commandId=%s); "
                "the backend will time this out after 5 minutes",
                command.command_id,
            )
            return
        envelope = contract.build_conversation_ended(
            self.settings.robot_device_id or "", command, outcome, reason_code
        )
        topic = f"bomi/v1/robot/{self.settings.robot_device_id}/events"
        try:
            self._client.publish(topic, _json_dumps(envelope, ensure_ascii=False), qos=1)
            logger.info(
                "CONVERSATION_ENDED published: conversationId=%s outcome=%s reason=%s",
                command.conversation_id, outcome, reason_code,
            )
        except Exception:  # noqa: BLE001 - 발행 실패가 루프를 막으면 안 된다
            logger.warning("failed to publish CONVERSATION_ENDED", exc_info=True)

    def _publish_started(self, command: contract.StartConversationCommand) -> None:
        if self._client is None:
            logger.warning(
                "no MQTT client to publish CONVERSATION_STARTED (commandId=%s); "
                "the backend will AI_START_TIMEOUT this in 10s",
                command.command_id,
            )
            return
        envelope = contract.build_conversation_started(
            self.settings.robot_device_id or "", command
        )
        topic = f"bomi/v1/robot/{self.settings.robot_device_id}/events"
        try:
            # QoS 1: 백엔드 인바운드는 QoS 1만 받는다. 10초 예산 안에 반드시
            # 나가야 하므로 여기서 실패하면 곧바로 알아야 한다 — 로그로 남긴다.
            self._client.publish(topic, _json_dumps(envelope, ensure_ascii=False), qos=1)
            logger.info(
                "CONVERSATION_STARTED published: conversationId=%s intent=%s",
                command.conversation_id, command.intent,
            )
        except Exception:  # noqa: BLE001 - 발행 실패가 큐 적재를 막으면 안 된다
            logger.warning("failed to publish CONVERSATION_STARTED", exc_info=True)

    def _remember(self, command_id: str) -> None:
        self._seen[command_id] = None
        while len(self._seen) > SEEN_COMMANDS_MAX:
            self._seen.popitem(last=False)

    # ── 연결: 실기에서만 쓰는 부분 ────────────────────────────────────────────

    def start(self) -> None:
        """브로커에 붙고 구독을 시작한다. door/mqtt.py 의 DoorSubscriber 와 동일 패턴."""
        from paho.mqtt import client as mqtt_client

        self.settings.validate_mqtt()
        host, port, use_tls = _parse_broker_url(self.settings.mqtt_broker_url)

        client = mqtt_client.Client(client_id=f"{self.settings.mqtt_client_id}-ai-commands")
        if self.settings.mqtt_username:
            client.username_pw_set(self.settings.mqtt_username, self.settings.mqtt_password)
        if use_tls:
            client.tls_set()

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        logger.info(
            "ai command subscriber connecting to %s:%d (tls=%s) topic=%s",
            host, port, use_tls, self._commands_topic(),
        )
        client.connect(host, port)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None

    def _commands_topic(self) -> str:
        return f"bomi/v1/ai/{self.settings.robot_device_id}/commands"

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc != 0:
            logger.error("ai command subscriber failed to connect (rc=%s)", rc)
            return
        topic = self._commands_topic()
        client.subscribe(topic, qos=1)
        logger.info("ai command subscriber subscribed to %s", topic)
        if self._ambient.enabled:
            client.subscribe(AMBIENT_TOPIC, qos=1)
            logger.info("homecoming ambient context subscribed to %s", AMBIENT_TOPIC)

    def _on_message(self, client, userdata, message) -> None:
        if message.topic.startswith("bomi/v1/iot/"):
            self._ambient.handle_payload(message.payload)
            return
        self.handle_payload(message.payload)


def build_ai_command_subscriber(
    *,
    settings: Settings | None = None,
    pending_queue: queue.Queue[contract.StartConversationCommand],
) -> AiCommandSubscriber | None:
    """설정이 갖춰져 있으면 구독기를 만든다. 시작하지는 않는다.

    반환값
        AiCommandSubscriber, 또는 None(비활성).

    주의사항
        None 이면 현관 인사·복약 알림·온습도 안부, 세 시나리오의 대화가 전혀
        시작되지 않는다 — 그 사실이 로그에 보여야 한다(robot_events.py 의
        build_robot_event_publisher 와 같은 원칙).
    """
    settings = settings or get_settings()
    if not settings.mqtt_enabled:
        logger.warning(
            "MQTT is disabled (MQTT_ENABLED); the robot will never receive "
            "START_CONVERSATION — homecoming/medication/wellness conversations "
            "will never start."
        )
        return None
    if not settings.robot_device_id:
        logger.warning(
            "ROBOT_DEVICE_ID is missing; ai command subscriber disabled — "
            "the backend cannot address this robot without it"
        )
        return None

    return AiCommandSubscriber(settings=settings, pending_queue=pending_queue)
