# robot/ai_chat/src/bomi_ai_chat/entrance_cheer.py
"""현관으로 출발할 때 "야호" 하고 환호한다 — 반가움을 소리로 먼저 낸다.

왜 있는가
    문이 열리면 로봇은 현관까지 조용히 굴러갈 뿐이고, 어르신은 로봇이 도착해
    입을 열 때까지 이게 나를 맞으러 오는 중인지 알 수 없다. 출발하는 순간
    한 마디 내지르면 그 몇 초가 "마중 나오는 중"으로 읽힌다. 같은 이유로
    주행 경로도 지그재그다(bridge/zigzag.py).

왜 새 계약이 아니라 '엿듣기' 인가
    navigation_watch.py 와 같은 수법이다. ``bomi/v1/robot/{robotId}/commands``
    는 원래 백엔드 -> bridge 채널이지만 MQTT 는 구독자가 여럿이어도 무방하다.
    ai_chat 이 같은 토픽을 엿듣기만 하면 되므로 **백엔드도 bridge 도 건드릴
    필요가 없다**. SPEAK 명령을 새로 만들지 않은 이유이기도 하다 — 백엔드는
    SPEAK 를 발행하지 않고(CLAUDE.md §1), Nav2 드라이버의 speak() 는 애초에
    FAILED 를 돌려준다.

왜 도착이 아니라 출발인가
    navigation_watch 는 results 토픽에서 ARRIVED 를 본다. 그건 이미 다 온
    뒤다. 여기서 필요한 건 "지금 출발한다"라서 commands 토픽의 NAVIGATE 를
    본다 — 로봇이 움직이기 시작하는 바로 그 순간이다.

마이크와 부딪히지 않는가
    부딪히지 않는다. 현관 이동 구간은 "이동 중 침묵"(CLAUDE.md §3a)이라
    마이크를 열지 않는다. 로봇이 자기 소리를 듣고 오작동할 창이 없다.

이 모듈이 하지 않는 것
    * 목적지 판단을 지어내지 않는다. payload.target 이 ENTRANCE 일 때만 운다.
    * 재생을 직접 하지 않는다. speak 콜백을 주입받을 뿐이라 TTS·스피커를
      모른다(테스트가 리스트 수집기를 넣는다).
    * 실패를 위로 던지지 않는다. 환호는 곁가지고 귀가 대본이 본체다 —
      search_signal.py·robot_events.py 와 같은 원칙이다.

왜 한 마디가 아니라 여러 마디인가
    현관까지는 15~30초쯤 걸린다. "야호" 한 마디는 2초면 끝나고 나머지는 다시
    침묵이라, 마중 나오는 중이라는 인상이 그 침묵에 묻힌다. 여러 마디를 차례로
    이어 말하면 이동하는 내내 소리가 난다. 주행은 bridge(ROS 2)가 하고 이
    모듈은 별도 스레드라, 말하는 동안에도 로봇은 계속 굴러간다.

    한 스레드에서 **순서대로** 말한다 — 동시에 두 문장을 재생하면 같은 스피커를
    두 번 여는 셈이다. 그리고 총 시간 상한을 둔다. 도착하면 곧바로 백엔드가
    귀가 인사를 시작하는데, 그때까지 환호가 남아 있으면 두 소리가 겹친다.

[.env 로 조절하는 값들]
    ENTRANCE_CHEER_ENABLED  "1"이면 환호한다(기본 "1"). 끄면 조용히 간다.
    ENTRANCE_CHEER_TEXT     외칠 말. "|" 로 나누면 여러 마디를 차례로 말한다.
    ENTRANCE_CHEER_MAX_SECONDS  환호 전체의 시간 상한(기본 20초).
    ENTRANCE_CHEER_GAP_SEC  마디 사이의 숨(기본 0.4초).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.door.mqtt import _parse_broker_url

logger = logging.getLogger(__name__)

#: 마디 구분자. 쉼표는 문장 안에 흔해서 쓰지 않는다.
PHRASE_SEPARATOR = "|"

#: 기본 환호 문구. 도착 인사("할머니 기다리고 있었어요!")와 겹치지 않게 고른다.
DEFAULT_CHEER_TEXT = (
    "야호!"
    "|할머니 오셨구나!"
    "|지금 마중 나가는 중이에요!"
    "|조금만 기다려 주세요!"
)

#: 환호 전체의 시간 상한(초). 도착 후 귀가 인사와 겹치지 않게 하는 안전장치다.
DEFAULT_MAX_SECONDS = 20.0

#: 마디 사이의 숨(초). 0 이면 붙여 말해 다급하게 들린다.
DEFAULT_GAP_SEC = 0.4


def split_phrases(text: str) -> list[str]:
    """환호 문구를 마디로 나눈다. 빈 마디는 버린다.

    역할: "야호!|할머니 오셨구나!" 를 두 마디로 나눈다.
    입력값: text - 구분자로 이어 붙인 문구.
    반환값: 마디 목록. 구분자가 없으면 원문 한 마디짜리 목록이다.
    """
    return [part.strip() for part in text.split(PHRASE_SEPARATOR) if part.strip()]


def _positive_env(name: str, default: float) -> float:
    """0 보다 큰 실수 설정을 읽는다. 잘못 적혀 있으면 기본값으로 돌아간다."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r 를 숫자로 읽지 못해 %s 를 씁니다", name, raw, default)
        return default
    return value if value > 0 else default

#: 이 목적지로 갈 때만 운다. 거실(보미야 호출)과 복귀(DEFAULT)는 조용히 간다 —
#: 복귀는 아무도 보고 있지 않고, 거실은 부른 사람이 이미 로봇을 보고 있다.
_TARGET_ENTRANCE = "ENTRANCE"


class EntranceCheerWatcher:
    """commands 토픽을 엿들어 NAVIGATE(ENTRANCE) 에 환호한다.

    입력값(생성자)
        speak: 문구 하나를 받아 소리 내는 콜백. 운영에서는 TTS 합성 + 스피커
            재생이고, 테스트에서는 리스트 수집기다.
        settings: 설정(robot_device_id, MQTT 접속 정보).
        text: 외칠 말. None 이면 ENTRANCE_CHEER_TEXT 또는 기본값.
        thread_factory: threading.Thread 호환 팩터리. 테스트가 즉시 실행되는
            가짜 스레드를 넣어 비동기 없이 검증한다.
    """

    def __init__(
        self,
        speak: Callable[[str], None],
        *,
        settings: Settings | None = None,
        client: Any = None,
        text: str | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._speak = speak
        self._client = client
        self._thread_factory = thread_factory
        # 시계와 잠을 주입받는 이유: 테스트가 20초를 실제로 기다릴 수는 없다.
        self._clock = clock
        self._sleep = sleep
        self._text = (
            text
            if text is not None
            else os.getenv("ENTRANCE_CHEER_TEXT", DEFAULT_CHEER_TEXT)
        ) or DEFAULT_CHEER_TEXT
        self._phrases = split_phrases(self._text)
        # 같은 명령을 두 번 보고 두 번 외치지 않기 위한 기억. 백엔드 재전송이나
        # QoS 1 재배달로 같은 commandId 가 또 올 수 있다.
        self._last_command_id: str | None = None
        self._lock = threading.Lock()

    # ── 판정: 브로커 없이 검증되는 부분 ──────────────────────────────────

    def handle_payload(self, raw: bytes | str) -> bool:
        """명령 하나를 본다. 예외를 던지지 않는다.

        반환값
            True  현관 이동이라 환호를 시작했다.
            False 그 외 전부(우리 것이 아님, 현관이 아님, 중복, 형식 깨짐).
        """
        try:
            body = _as_mapping(raw)
        except (TypeError, ValueError, UnicodeDecodeError):
            return False

        if body.get("type") != "NAVIGATE":
            return False

        expected_robot_id = self.settings.robot_device_id
        if expected_robot_id and body.get("robotId") != expected_robot_id:
            return False

        payload = body.get("payload")
        if not isinstance(payload, dict):
            return False
        if payload.get("target") != _TARGET_ENTRANCE:
            return False

        command_id = body.get("commandId")
        with self._lock:
            if command_id is not None and command_id == self._last_command_id:
                return False
            self._last_command_id = command_id

        logger.info("navigating to the entrance; cheering %r", self._text)
        self._cheer_async()
        return True

    def _cheer_async(self) -> None:
        """환호를 별도 스레드로 넘긴다.

        paho 수신 콜백 스레드에서 부르므로 여기서 TTS 합성(네트워크 왕복)과
        재생을 기다리면 그동안 다른 MQTT 메시지를 못 받는다. 특히 곧이어
        도착 결과를 봐야 하는 navigation_watch 가 같은 브로커를 쓴다.
        """
        thread = self._thread_factory(target=self._cheer, daemon=True)
        thread.start()

    def _cheer(self) -> None:
        """마디를 차례로 말한다. 시간 상한을 넘기면 남은 마디는 버린다.

        상한을 넘겨 남은 마디를 말하지 않는 것이 맞다 — 이미 도착해서 귀가
        인사가 시작됐을 시점이고, 거기에 환호를 얹으면 두 소리가 겹친다.
        """
        max_seconds = _positive_env("ENTRANCE_CHEER_MAX_SECONDS", DEFAULT_MAX_SECONDS)
        gap_sec = _positive_env("ENTRANCE_CHEER_GAP_SEC", DEFAULT_GAP_SEC)
        deadline = self._clock() + max_seconds

        for index, phrase in enumerate(self._phrases):
            if index > 0:
                # 숨을 먼저 쉬고 나서 재본다 — 상한을 넘긴 뒤에 새 마디를
                # 시작하지 않는 것이 이 상한의 뜻이다.
                self._sleep(gap_sec)
                if self._clock() >= deadline:
                    logger.info(
                        "환호 시간 상한(%.1f초)에 걸려 남은 %d마디를 건너뜁니다",
                        max_seconds, len(self._phrases) - index)
                    return
            try:
                self._speak(phrase)
            except Exception:  # noqa: BLE001 - 환호 실패가 귀가 대본을 막으면 안 된다
                # 한 마디가 실패하면 스피커나 TTS 가 통째로 죽은 것이다.
                # 남은 마디를 계속 시도해 봐야 같은 예외만 쌓인다.
                logger.exception("failed to cheer on the way to the entrance")
                return

    # ── 연결: 실기에서만 쓰는 부분 ───────────────────────────────────────

    def start(self) -> None:
        """브로커에 붙고 명령 토픽을 구독한다. navigation_watch 와 동일 패턴."""
        from paho.mqtt import client as mqtt_client

        self.settings.validate_mqtt()
        host, port, use_tls = _parse_broker_url(self.settings.mqtt_broker_url)

        client = mqtt_client.Client(
            client_id=f"{self.settings.mqtt_client_id}-entrance-cheer")
        if self.settings.mqtt_username:
            client.username_pw_set(
                self.settings.mqtt_username, self.settings.mqtt_password)
        if use_tls:
            client.tls_set()

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        logger.info(
            "entrance cheer watcher connecting to %s:%d (tls=%s) topic=%s",
            host, port, use_tls, self._commands_topic())
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
        return f"bomi/v1/robot/{self.settings.robot_device_id}/commands"

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc != 0:
            logger.error(
                "entrance cheer watcher failed to connect (rc=%s)", rc)
            return
        topic = self._commands_topic()
        client.subscribe(topic, qos=1)
        logger.info("entrance cheer watcher subscribed to %s", topic)

    def _on_message(self, client, userdata, message) -> None:
        self.handle_payload(message.payload)


def _as_mapping(raw: bytes | str) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("robot command payload must be a JSON object")
    return decoded


def build_entrance_cheer_watcher(
    speak: Callable[[str], None],
    settings: Settings | None = None,
) -> EntranceCheerWatcher | None:
    """설정이 갖춰져 있으면 감시자를 만든다. 시작하지는 않는다.

    반환값
        EntranceCheerWatcher, 또는 None(비활성).

    비활성 조건
        * ENTRANCE_CHEER_ENABLED 가 "1" 이 아니다.
        * MQTT 가 꺼져 있다 — 엿들을 토픽 자체가 없다.
        * robot_device_id 가 없다 — 토픽 이름을 만들 수 없다.
    """
    settings = settings or get_settings()

    if os.getenv("ENTRANCE_CHEER_ENABLED", "1") != "1":
        logger.info(
            "ENTRANCE_CHEER_ENABLED != 1 — 현관 이동에 환호하지 않습니다.")
        return None
    if not settings.mqtt_enabled:
        logger.info("MQTT 가 꺼져 있어 현관 환호를 켜지 않습니다.")
        return None
    if not settings.robot_device_id:
        logger.warning(
            "ROBOT_DEVICE_ID 가 없어 현관 환호 토픽을 만들 수 없습니다.")
        return None

    return EntranceCheerWatcher(speak, settings=settings)
