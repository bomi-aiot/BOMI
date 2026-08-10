"""MQTT 구독 어댑터 — 브로커에서 현관 이벤트를 받아 intake 로 넘긴다.

이 파일에 판정 로직이 없다  ★
    하는 일은 세 가지뿐이다. 연결, 구독, 메시지 하나를 intake 로 넘기기.
    재실 규칙이나 방향 판정을 여기에 넣으면 브로커 없이 테스트할 수 없게 된다.
    그래서 테스트는 `on_message` 에 넣을 payload 를 직접 만들어 전 경로를 돈다.

브로커는 두 곳에 있을 수 있다
    EC2(`bomi-mosquitto`, 8883 노출)와 Jetson 로컬. 어느 쪽에 붙든 코드가 같아야 하므로
    주소는 설정으로 받는다(config.mqtt_broker_url). scheme 이 TLS 여부를 정한다.

paho-mqtt 는 선택 의존이다
    함수 안에서 import 한다. 이 모듈을 import 하는 것만으로 실패하면, MQTT 가 필요 없는
    테스트까지 끌려 들어간다. APScheduler 를 jobs/scheduler.py 에서 다루는 방식과 같다.

    설치: pip install "bomi-ai-chat[mqtt]"

참고
    docs/mqtt/topic-convention.md, CLAUDE.md §11 (현관), §24 (payload 미결)
"""

from __future__ import annotations

import logging
import threading
from urllib.parse import urlparse

from bomi_ai_chat.backend_client.door_client import BackendDoorClient
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.contracts.door import DoorEventError, parse_door_event
from bomi_ai_chat.door import intake

logger = logging.getLogger(__name__)

_DEFAULT_PORTS = {"mqtt": 1883, "mqtts": 8883}


class DoorSubscriber:
    """브로커에 붙어 현관 이벤트를 받는다. 시작은 호출부가 한다."""

    def __init__(
        self,
        senior_id: str,
        *,
        settings: Settings | None = None,
        door_client=None,
        app=None,
        homecoming_gate=None,
    ):
        self.senior_id = senior_id
        self.settings = settings or get_settings()
        self.door_client = door_client
        # 귀가 대본이 시작됐음을 알릴 곳(homecoming_gate.HomecomingGate).
        # None 이면 아무에게도 알리지 않는다 — 문 감시는 그대로 동작한다.
        self.homecoming_gate = homecoming_gate
        # 그래프. 있으면 문 이벤트로 능동 턴을 돌려 checkpoint 에도 반영한다.
        # 없으면 내구 저장소만 갱신되고, 그것만으로도 안전 감시는 살아 있다.
        self.app = app
        self._client = None
        # DOOR_OPENED 를 한 번이라도 봤는지. 웨이크워드 게이트가 이 값을 읽는다
        # (bootstrap._wake_word_allowed). paho 콜백 스레드가 세우고 메인 루프가
        # 읽으므로 Event 를 쓴다.
        self._door_opened = threading.Event()

    # ── 메시지 처리: 브로커 없이도 테스트할 수 있는 부분 ──────────────────────

    def handle_payload(self, raw: bytes | str) -> bool:
        """메시지 하나를 처리한다. 예외를 던지지 않는다.

        왜 예외를 밖으로 내지 않는가
            paho 의 콜백에서 예외가 올라가면 그 메시지 하나가 아니라 구독 루프의
            동작이 불확실해진다. 현관 감시가 조용히 멈추는 것이 이 설계가 가장
            피하려는 실패다.

        반환값
            True  처리됨.
            False 버렸다. 이유는 로그에 남는다.
        """
        try:
            event = parse_door_event(raw)
        except DoorEventError as error:
            # 계약 위반은 경고로 남기고 그 메시지만 버린다. 펌웨어가 새 타입을
            # 추가한 것만으로 현관 감시가 멈춰서는 안 된다.
            logger.warning("dropping a door message: %s", error)
            return False

        try:
            intake.ingest(self.senior_id, event, door_client=self.door_client)
        except Exception:  # noqa: BLE001 - 구독 루프가 죽으면 현관 감시가 멈춘다
            logger.exception("door intake failed for %s", event.type)
            return False

        # HEARTBEAT 나 MOTION 으로는 열지 않는다. 그것들은 어르신이 돌아왔다는
        # 증거가 아니라 센서가 살아 있다는 증거일 뿐이다.
        if event.type == "DOOR_OPENED":
            self._door_opened.set()
            # 여기서부터 온습도 마무리까지가 귀가 대본이다. 그 사이의 "보미야"는
            # 대본을 벗어나게 하므로 막는다(bootstrap._wake_word_allowed).
            self._notify_homecoming_started()

        self._invoke_graph(event)
        return True

    def has_seen_door_opened(self) -> bool:
        """이 프로세스가 뜬 뒤 DOOR_OPENED 를 한 번이라도 받았는가."""
        return self._door_opened.is_set()

    def _notify_homecoming_started(self) -> None:
        """귀가 게이트를 닫는다. 실패해도 문 이벤트 처리를 막지 않는다."""
        gate = self.homecoming_gate
        if gate is None:
            return
        try:
            gate.start()
        except Exception:  # noqa: BLE001 - 게이트는 부가, 문 감시가 본체다
            logger.warning("could not start the homecoming gate", exc_info=True)

    def _invoke_graph(self, event) -> None:
        """그래프에도 알린다. 대화 턴이 읽는 checkpoint 를 갱신하기 위한 것이다.

        실패해도 넘어간다. 내구 저장소 반영은 이미 끝났고, 사다리는 그 값을 읽는다.
        """
        if self.app is None:
            return
        try:
            self.app.invoke(
                {
                    "trigger_type": "door_event",
                    "senior_id": self.senior_id,
                    "last_door_event": {
                        "type": event.type,
                        "ts": event.received_at,
                        "direction": event.direction,
                    },
                },
                {"configurable": {"thread_id": self.senior_id}},
            )
        except Exception:  # noqa: BLE001 - 구독 루프가 죽으면 현관 감시가 멈춘다
            logger.exception("door_event graph invoke failed for %s", self.senior_id)

    # ── 연결: 실기에서만 쓰는 부분 ────────────────────────────────────────────

    def start(self) -> None:
        """브로커에 붙고 구독을 시작한다. 백그라운드 스레드에서 돈다.

        주의사항
            paho 의 loop_start() 는 자체 재연결을 처리한다. 직접 재연결 루프를 쓰지
            않는다 — 두 개의 재연결 로직이 동시에 돌면 연결이 계속 끊긴다.
        """
        from paho.mqtt import client as mqtt_client

        self.settings.validate_mqtt()
        host, port, use_tls = _parse_broker_url(self.settings.mqtt_broker_url)

        client = mqtt_client.Client(client_id=self.settings.mqtt_client_id)
        if self.settings.mqtt_username:
            client.username_pw_set(self.settings.mqtt_username, self.settings.mqtt_password)
        if use_tls:
            client.tls_set()

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        logger.info(
            "door subscriber connecting to %s:%d (tls=%s) topic=%s",
            host, port, use_tls, self.settings.mqtt_door_topic,
        )
        client.connect(host, port)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        """구독을 멈춘다. 붙지 않았으면 아무것도 하지 않는다."""
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """연결 성공 시 구독한다.

        왜 connect() 옆이 아니라 콜백에서 구독하는가
            재연결될 때마다 구독이 다시 필요하다. connect() 뒤에 한 번만 구독하면,
            브로커가 한 번 재시작된 뒤로 문 이벤트가 조용히 안 온다.
        """
        if rc != 0:
            logger.error("door subscriber failed to connect (rc=%s)", rc)
            return
        client.subscribe(self.settings.mqtt_door_topic)
        logger.info("door subscriber subscribed to %s", self.settings.mqtt_door_topic)

    def _on_message(self, client, userdata, message) -> None:
        self.handle_payload(message.payload)


def build_door_subscriber(
    senior_id: str,
    *,
    settings: Settings | None = None,
    app=None,
    homecoming_gate=None,
) -> DoorSubscriber | None:
    """설정이 활성화되어 있으면 구독기를 만든다. 시작하지는 않는다.

    반환값
        DoorSubscriber, 또는 None(비활성).

    주의사항
        None 을 돌려줄 때 경고를 남긴다. 현관 신호가 없는 상태로 로봇이 도는 것은
        정상 동작이 아니라 '기능 하나가 빠진 상태'이고, 그것이 로그에 보여야 한다.
    """
    settings = settings or get_settings()
    if not settings.mqtt_enabled:
        logger.warning(
            "MQTT is disabled (MQTT_ENABLED); the robot will receive no door events. "
            "occupancy stays UNKNOWN and the door watch cannot detect a missing return.")
        return None

    return DoorSubscriber(
        senior_id,
        settings=settings,
        door_client=BackendDoorClient(settings=settings),
        app=app,
        homecoming_gate=homecoming_gate,
    )


def _parse_broker_url(url: str) -> tuple[str, int, bool]:
    """mqtt(s)://host[:port] 를 (host, port, tls) 로 나눈다.

    왜 URL 로 받는가
        host / port / tls 를 따로 받으면 세 값이 어긋난 조합(8883 인데 tls=false)이
        생기고, 그러면 연결이 조용히 실패한다. scheme 하나가 세 값을 묶어준다.
    """
    parsed = urlparse(url if "://" in url else f"mqtt://{url}")
    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError(
            f"unsupported MQTT scheme {scheme!r}; use mqtt:// or mqtts://"
        )
    if not parsed.hostname:
        raise ValueError(f"MQTT broker url has no host: {url!r}")
    return parsed.hostname, parsed.port or _DEFAULT_PORTS[scheme], scheme == "mqtts"
