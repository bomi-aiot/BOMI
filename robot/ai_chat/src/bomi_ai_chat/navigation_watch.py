# robot/ai_chat/src/bomi_ai_chat/navigation_watch.py
"""bridge 가 발행하는 이동 결과를 엿듣는다 — "이동 중 침묵"의 도착 신호.

어디에 위치하는가
    CLAUDE.md §3a "이동 중 침묵". 보미야 호출은 백엔드가 항상 NAVIGATE
    (LIVING_ROOM) 을 함께 유발한다(scenario-contract-v1.md §8.3). 로봇이
    이동하는 동안 마이크를 열면 모터 소음이 ASR 을 망친다 — 그래서 bootstrap
    의 웨이크 흐름은 짧은 응답만 하고, 이 모듈이 도착(v1 `NAVIGATION_RESULT`
    / `outcome=SUCCEEDED` / `resultCode=ARRIVED`)을 알려줄 때까지 기다린다.

왜 새 토픽이 없는가
    `bomi/v1/robot/{robotId}/results` 는 원래 bridge -> 백엔드 전용 채널이지만,
    MQTT 는 구독자가 여럿이어도 아무 문제가 없다. ai_chat 이 같은 토픽을
    "엿듣기"만 하면 되므로, bridge 도 백엔드도 건드릴 필요가 없다(2026-08
    통합 스프린트가 "백엔드 계약 무접촉"으로 정한 원칙과 같다).

이 모듈이 하는 일과 하지 않는 일
    한다     결과 봉투에서 ARRIVED 여부만 뽑아 threading.Event 로 알린다.
    안 한다  결과 검증(계약 위반 거부 등) — bridge/backend 가 이미 정합을
             책임지므로, 여기서는 "ARRIVED 인가 아닌가"만 관대하게 본다.
             형식이 이상하면 그냥 '아직 도착 아님'으로 취급한다(무시).

참고
    CLAUDE.md §3a, docs/mqtt/scenario-contract-v1.md §7
    door/mqtt.py (같은 paho 배선 패턴)
"""

from __future__ import annotations

import json
import logging
import threading

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.door.mqtt import _parse_broker_url

logger = logging.getLogger(__name__)


class NavigationArrivalWatcher:
    """`bomi/v1/robot/{robotId}/results` 를 엿들어 ARRIVED 를 신호한다."""

    def __init__(self, *, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client
        self._arrived = threading.Event()

    # ── 신호 대기: 브로커 없이도 테스트할 수 있는 부분 ──────────────────────

    def reset(self) -> None:
        """새 이동을 기다리기 전에 지난 신호를 지운다.

        지우지 않으면, 직전 대화의 ARRIVED 신호가 아직 Event 에 남아 있어
        이번 대화가 실제 도착 전에 곧바로 '도착함'으로 오판할 수 있다.
        """
        self._arrived.clear()

    def wait_for_arrival(self, timeout_sec: float) -> bool:
        """ARRIVED 를 받을 때까지 최대 timeout_sec 초 기다린다.

        반환값
            True  ARRIVED 를 받았다(제한 시간 안에).
            False 제한 시간을 넘겼다 — 호출부(bootstrap)가 그 자리에서
                  대화를 시작해야 한다(policy.WAKE_MOVEMENT_WAIT_TIMEOUT_SEC
                  문서화된 이유: 침묵 고착이 늦은 시작보다 훨씬 나쁘다).
        """
        return self._arrived.wait(timeout_sec)

    def handle_payload(self, raw: bytes | str) -> bool:
        """결과 메시지 하나를 본다. 예외를 던지지 않는다.

        반환값
            True  이번 메시지가 ARRIVED 였다(신호를 세웠다).
            False 그 외 전부(우리 것이 아님, ARRIVED 가 아님, 형식이 깨짐).
        """
        try:
            body = _as_mapping(raw)
        except (TypeError, ValueError, UnicodeDecodeError):
            return False

        if body.get("type") != "NAVIGATION_RESULT":
            return False

        expected_robot_id = self.settings.robot_device_id
        if expected_robot_id and body.get("robotId") != expected_robot_id:
            return False

        payload = body.get("payload")
        if not isinstance(payload, dict):
            return False
        if (payload.get("outcome") == "SUCCEEDED"
                and payload.get("resultCode") == "ARRIVED"):
            self._arrived.set()
            logger.info("navigation ARRIVED observed; ending the movement wait")
            return True
        return False

    # ── 연결: 실기에서만 쓰는 부분 ────────────────────────────────────────────

    def start(self) -> None:
        """브로커에 붙고 결과 토픽을 구독한다. door/mqtt.py 와 동일 패턴."""
        from paho.mqtt import client as mqtt_client

        self.settings.validate_mqtt()
        host, port, use_tls = _parse_broker_url(self.settings.mqtt_broker_url)

        client = mqtt_client.Client(
            client_id=f"{self.settings.mqtt_client_id}-nav-watch")
        if self.settings.mqtt_username:
            client.username_pw_set(self.settings.mqtt_username, self.settings.mqtt_password)
        if use_tls:
            client.tls_set()

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        logger.info("navigation arrival watcher connecting to %s:%d (tls=%s) topic=%s",
                    host, port, use_tls, self._results_topic())
        client.connect(host, port)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None

    def _results_topic(self) -> str:
        return f"bomi/v1/robot/{self.settings.robot_device_id}/results"

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc != 0:
            logger.error("navigation arrival watcher failed to connect (rc=%s)", rc)
            return
        topic = self._results_topic()
        client.subscribe(topic, qos=1)
        logger.info("navigation arrival watcher subscribed to %s", topic)

    def _on_message(self, client, userdata, message) -> None:
        self.handle_payload(message.payload)


def _as_mapping(raw: bytes | str) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("navigation result payload must be a JSON object")
    return decoded


def build_navigation_arrival_watcher(
    settings: Settings | None = None,
) -> NavigationArrivalWatcher | None:
    """설정이 갖춰져 있으면 감시자를 만든다. 시작하지는 않는다.

    반환값
        NavigationArrivalWatcher, 또는 None(비활성).

    주의사항
        settings.wake_movement_wait_enabled 가 꺼져 있으면 아예 만들지
        않는다 — 로봇/브릿지 없는 개발 환경에서 매 "보미야"마다 45초를
        날리는 사고를 막는다(config.py 의 wake_movement_wait_enabled 주석
        참고).
    """
    settings = settings or get_settings()
    if not settings.wake_movement_wait_enabled:
        return None
    if not settings.mqtt_enabled:
        logger.warning(
            "WAKE_MOVEMENT_WAIT_ENABLED is on but MQTT is disabled; "
            "the robot will always fall back to the %s-second timeout",
            "policy.WAKE_MOVEMENT_WAIT_TIMEOUT_SEC",
        )
        return None
    if not settings.robot_device_id:
        logger.warning(
            "ROBOT_DEVICE_ID is missing; navigation arrival watcher disabled — "
            "the robot will always fall back to the movement-wait timeout"
        )
        return None

    return NavigationArrivalWatcher(settings=settings)
