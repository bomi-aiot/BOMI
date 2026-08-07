# robot/ai_chat/src/bomi_ai_chat/search_signal.py
"""회전 탐색 신호 발신 — "보미야"를 들은 방향을 로봇 내부로 알린다.

왜 MQTT 가 아니라 UDP 인가
    백엔드 MQTT 계약(MqttInboundMessageParser.validateWakeWordDetected)은 봉투와
    payload 의 허용 필드를 정확히 못 박고, 그 밖의 필드가 하나라도 있으면
    메시지를 통째로 버린다. WAKE_WORD_DETECTED payload 에 허용된 것은
    keyword 와 confidence 뿐이라 각도를 실을 수 없다.

    그래서 역할을 나눈다 (구현계획 §0):
        MQTT (백엔드 경유)  "언제" 시작할지. 시나리오 기록·중복 방지·안전 차단.
        UDP  (로봇 내부)    "어디로" 돌지. 계약을 건드리지 않고 각도만 나른다.

무엇을 보내는가
    {"type": "wake", "azimuth_deg": <로봇 정면 기준 각도 or null>}
    {"type": "stop", "reason": "<사유>"}

    각도 부호는 ROS 2 REP-103 을 따른다 — 로봇 기준 왼쪽(반시계)이 양수다.
    마이크가 반대 방향으로 세는 장치라면 SEARCH_AZIMUTH_SIGN=-1 로 뒤집는다.

주의사항
    - 발신 실패가 대화를 막으면 안 된다. 모든 실패는 경고 로그로 삼킨다.
      탐색은 부가 기능이고 대화가 본체다(robot_events.py 와 같은 원칙).
    - UDP 라 도착 보장이 없다. 각도가 못 가면 wake_search 노드는 힌트 없이
      전체 한 바퀴 탐색으로 폴백한다 — 느릴 뿐 시나리오는 성립한다.
    - 이 모듈은 모터를 직접 제어하지 않는다(robot/AGENTS.md §3). 방향을
      알릴 뿐, 돌지 말지는 ROS 2 쪽이 정한다.

[.env 로 조절하는 값들]
    SEARCH_SIGNAL_ENABLED     "1"이면 신호를 보낸다(기본 "1").
    SEARCH_SIGNAL_HOST        받는 쪽 주소(기본 127.0.0.1). 같은 젯슨이면 루프백.
    SEARCH_SIGNAL_PORT        받는 쪽 포트(기본 5006). wake_search 의
                              hint_bind_port 와 같아야 한다.
    SEARCH_USE_BEAM_DIRECTION "1"이면 마이크에서 소리 방향을 읽는다(기본 "1").
                              끄면 각도 없이 보내고 로봇은 전체 탐색을 한다.
    SEARCH_AZIMUTH_SIGN       "1" 또는 "-1". 로봇이 반대로 돌면 뒤집는다.
"""

from __future__ import annotations

import json
import logging
import os
import socket

logger = logging.getLogger(__name__)

# wake_search 노드(core/core/wake_search.py)와 맞춘 메시지 타입.
SIGNAL_WAKE = "wake"
SIGNAL_STOP = "stop"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5006


def normalize_relative_deg(degrees: float) -> float:
    """각도를 -180 ~ +180 범위로 접는다.

    역할: 350도를 -10도로 바꿔 "왼쪽으로 350도"가 아니라 "오른쪽으로 10도"가
        되게 한다. 이걸 빼먹으면 로봇이 반대로 한 바퀴 돈다.
    입력값: degrees - 임의의 각도(도).
    반환값: -180 이상 180 미만으로 접힌 각도.
    """
    wrapped = (float(degrees) + 180.0) % 360.0
    if wrapped < 0.0:
        wrapped += 360.0
    return wrapped - 180.0


class SearchSignalSender:
    """회전 탐색 신호를 UDP 로 보낸다. 연결 상태를 갖지 않는다."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        direction_provider=None,
        azimuth_sign: float = 1.0,
    ) -> None:
        """수신 주소와 방향 읽기 콜백을 받는다.

        입력값:
            host, port - wake_search 노드가 듣고 있는 주소와 포트.
            direction_provider - 로봇 정면 기준 각도(도)를 돌려주는 콜백.
                None 이면 각도 없이 보낸다. 실패하면 예외를 던져도 된다 —
                이 클래스가 잡아서 "각도 없음"으로 처리한다.
            azimuth_sign - 마이크 각도 증가 방향이 반시계면 1.0, 시계면 -1.0.
        """
        if not isinstance(host, str) or not host.strip():
            raise ValueError("host must not be empty")
        if isinstance(port, bool) or not isinstance(port, int):
            raise ValueError("port must be an integer")
        if not 1 <= port <= 65535:
            raise ValueError("port must be from 1 to 65535")
        if azimuth_sign not in (1.0, -1.0, 1, -1):
            raise ValueError("azimuth_sign must be 1 or -1")

        self._destination = (host.strip(), port)
        self._direction_provider = direction_provider
        self._azimuth_sign = float(azimuth_sign)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._closed = False

    # ── 발신 ────────────────────────────────────────────────────────────────

    def send_wake(self) -> float | None:
        """웨이크워드 감지를 알린다. 가능하면 소리 방향을 함께 보낸다.

        반환값: 함께 보낸 각도(도). 방향을 못 읽었으면 None.
        주의: 실패해도 예외를 올리지 않는다.
        """
        azimuth = self._read_direction_deg()
        self._send({"type": SIGNAL_WAKE, "azimuth_deg": azimuth})
        return azimuth

    def send_stop(self, reason: str = "unspecified") -> None:
        """탐색을 즉시 멈추라고 알린다(재호출·정지 요청·대화 종료).

        주의: 몇 번 불려도 안전하다. 탐색 중이 아니면 받는 쪽이 무시한다.
        """
        self._send({"type": SIGNAL_STOP, "reason": str(reason)})

    def close(self) -> None:
        """소켓을 닫는다. 두 번 불려도 안전하다."""
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.close()
        except OSError:
            logger.debug("search signal socket close failed", exc_info=True)

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _read_direction_deg(self) -> float | None:
        """방향 콜백을 불러 -180~180 범위 각도를 얻는다. 실패는 None."""
        if self._direction_provider is None:
            return None
        try:
            raw = self._direction_provider()
        except Exception:  # noqa: BLE001 - 방향을 못 읽어도 탐색은 가능하다
            logger.warning(
                "소리 방향을 읽지 못했습니다. 각도 없이 전체 탐색으로 넘깁니다.",
                exc_info=True)
            return None
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning("소리 방향 값이 숫자가 아닙니다: %r", raw)
            return None
        if value != value or value in (float("inf"), float("-inf")):
            logger.warning("소리 방향 값이 유한하지 않습니다: %r", raw)
            return None
        return normalize_relative_deg(value * self._azimuth_sign)

    def _send(self, payload: dict) -> None:
        """JSON 한 통을 보낸다. 실패는 경고 로그로 삼킨다."""
        if self._closed:
            return
        try:
            packet = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            self._socket.sendto(packet, self._destination)
            logger.info("회전 탐색 신호 발신: %s", payload)
        except Exception:  # noqa: BLE001 - 신호 실패가 대화를 막으면 안 된다
            logger.warning("회전 탐색 신호 발신 실패", exc_info=True)


def build_search_signal_sender(beam=None) -> SearchSignalSender | None:
    """설정이 갖춰져 있으면 발신자를 만든다.

    입력값: beam - BeamController(선택). 있으면 소리 방향을 여기서 읽는다.
    반환값: SearchSignalSender, 또는 None(비활성).

    주의사항
        None 을 돌려줄 때는 반드시 이유를 로그로 남긴다. "왜 로봇이 안 도는가"를
        나중에 조사할 때, 여기서 꺼져 있었다는 사실이 보여야 한다
        (robot_events.build_robot_event_publisher 와 같은 원칙).
    """
    if os.getenv("SEARCH_SIGNAL_ENABLED", "1") != "1":
        logger.info(
            "SEARCH_SIGNAL_ENABLED != 1 — 회전 탐색 신호를 보내지 않습니다 "
            "(보미야를 불러도 로봇이 사람을 찾으러 돌지 않습니다)")
        return None

    host = os.getenv("SEARCH_SIGNAL_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_port = os.getenv("SEARCH_SIGNAL_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        logger.warning(
            "SEARCH_SIGNAL_PORT 가 정수가 아닙니다(%r). 기본값 %d 를 씁니다.",
            raw_port, DEFAULT_PORT)
        port = DEFAULT_PORT

    raw_sign = os.getenv("SEARCH_AZIMUTH_SIGN", "1").strip()
    azimuth_sign = -1.0 if raw_sign in ("-1", "-1.0") else 1.0

    provider = _build_direction_provider(beam)

    try:
        sender = SearchSignalSender(
            host=host,
            port=port,
            direction_provider=provider,
            azimuth_sign=azimuth_sign,
        )
    except ValueError:
        logger.warning("회전 탐색 신호 설정이 잘못되어 비활성화합니다.",
                       exc_info=True)
        return None

    logger.info(
        "회전 탐색 신호 발신자 준비: %s:%d, 방향읽기=%s, 부호=%+d",
        host, port, "켬" if provider is not None else "끔", int(azimuth_sign))
    return sender


def _build_direction_provider(beam):
    """BeamController 에서 "로봇 정면 기준 각도"를 얻는 콜백을 만든다.

    왜 빔 고정이 켜져 있으면 방향을 못 읽는가
        BEAM_FIX_ENABLED=1 이면 마이크 빔이 정면에 고정되고, 그때
        AEC_AZIMUTH_VALUES 는 '지금 말하는 사람 방향'이 아니라 고정된 정면
        각도를 그대로 돌려준다. 그 값으로 회전하면 항상 0도, 즉 제자리다.
        그래서 이 조합은 방향 읽기를 끄고 전체 탐색으로 폴백한다.

    왜 BeamController 를 여기서 만들 수 있는가
        생성자는 .env 만 읽고 하드웨어에 손대지 않는다(마이크 접근은
        read_direction_deg 안에서 일어나고, 그 실패는 위에서 잡는다).
        그래서 호출부가 넘겨주지 않아도 안전하게 하나 만들 수 있다.
    """
    if os.getenv("SEARCH_USE_BEAM_DIRECTION", "1") != "1":
        logger.info("SEARCH_USE_BEAM_DIRECTION != 1 — 방향 없이 전체 탐색합니다.")
        return None

    if beam is None:
        try:
            from bomi_ai_chat.audio_io.beam_control import BeamController

            beam = BeamController()
        except Exception:  # noqa: BLE001 - 마이크 제어가 없어도 탐색은 가능하다
            logger.warning(
                "BeamController 를 만들 수 없어 방향 없이 전체 탐색합니다.",
                exc_info=True)
            return None

    if getattr(beam, "enabled", False):
        logger.warning(
            "BEAM_FIX_ENABLED=1 이라 소리 방향을 읽을 수 없습니다 "
            "(빔이 정면에 고정되면 항상 정면 각도가 나옵니다). "
            "각도 없이 전체 탐색합니다.")
        return None

    front_deg = float(getattr(beam, "front_deg", 0.0) or 0.0)

    def provider() -> float:
        """마이크 절대 각도를 로봇 정면 기준 상대 각도로 바꾼다."""
        absolute_deg = beam.read_direction_deg()
        return normalize_relative_deg(absolute_deg - front_deg)

    return provider
