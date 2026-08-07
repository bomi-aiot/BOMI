"""현관 이벤트 계약 — 라즈베리파이가 보내고 Jetson 이 정규화하는 메시지.

봉투는 docs/mqtt/topic-convention.md 규약을 따른다.

    {"eventId": "...", "type": "DOOR_OPENED",
     "occurredAt": "2026-08-01T21:30:00+09:00", "sourceId": "door-sensor-01",
     "payload": {...}}

이 모듈이 하는 일과 하지 않는 일  ★ 먼저 읽을 것
    한다     봉투 검증, 시각 정규화, 알 수 없는 타입 거부
    안 한다  **방향(IN/OUT) 판정**

    방향은 백엔드 몫이다 (CLAUDE.md §11). 센서 두 개는 각자 방향을 모르고, 두 신호의
    '순서'로만 방향이 나온다. 그 상관 판정에 필요한 시간 창은 실측값이라 튜닝 대상이고,
    로봇에 두면 조정할 때마다 로봇을 배포해야 한다. 그래서 로봇은 방향을 만들지 않고,
    백엔드가 채워 보내주면 그때만 읽는다.

    이 규칙이 무너지면 같은 판정이 두 곳에 생기고, 두 곳은 반드시 갈라진다.

시각 권위는 Jetson 이다  ★ 이 파일에서 가장 중요한 결정
    라즈베리파이에는 배터리 백업 RTC 가 없을 수 있다. 전원을 껐다 켜면 시계가 1970년일
    수도 있고, 몇 시간 어긋난 값일 수도 있다.

    틀린 문 이벤트 시각은 두 가지를 함께 오염시킨다.
      - 루틴 베이스라인 학습("이 어르신은 보통 9시에 나간다")
      - TTL 산술(인사 마감, 부재 시간 누적)

    그래서 `occurredAt` 은 **참고용**으로만 남기고, 계산에 쓰는 시각은 도착 시점의
    clock.now() 다. 압축 시계 시연이 일관되게 돌아가는 것도 이 정규화 덕분이다 (§15).

참고
    CLAUDE.md §11 (현관과 재실), §15 (시계 주입), §24 (MQTT payload 미결)
    docs/mqtt/topic-convention.md
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock

logger = logging.getLogger(__name__)

# 우리가 이해하는 이벤트 타입.
#
# ★ 현재 배포된 것은 DOOR_OPENED 하나뿐이다 (CLAUDE.md §24).
#   MOTION_DETECTED 와 HEARTBEAT 는 이 설계가 요구하는 것이고, 펌웨어 쪽 합의가
#   남아 있다. 없는 상태로도 이 모듈은 동작한다 — 다만 백엔드가 방향을 만들 수 없고,
#   하트비트가 없으면 door_watch_tick 이 "라즈베리파이가 죽었다"를 알 수 없다.
DOOR_EVENT_TYPES = frozenset({
    "DOOR_OPENED",     # SNZB-04P 접점 열림
    "DOOR_CLOSED",     # SNZB-04P 접점 닫힘
    "MOTION_DETECTED",  # SNZB-03P PIR
    "HEARTBEAT",       # 라즈베리파이 생존 신호
})

# 백엔드가 방향을 확정해 되돌려줄 때 쓰는 값. 로봇이 스스로 만들지는 않는다.
DOOR_DIRECTIONS = frozenset({"in", "out"})


class DoorEventError(ValueError):
    """봉투가 계약을 만족하지 않는다.

    왜 예외인가
        조용히 무시하면 "센서가 안 왔다"와 "메시지를 못 읽었다"가 구분되지 않는다.
        안전 감시에서 그 둘은 정반대의 조치를 요구한다.

    누가 잡는가
        door.intake 가 잡아서 경고로 남기고 그 메시지 하나만 버린다. 구독 루프를
        죽이지 않는다 — 펌웨어가 새 타입을 추가한 것만으로 현관 감시가 멈추면 안 된다.
    """


@dataclass(frozen=True)
class DoorEvent:
    """정규화된 현관 이벤트.

    필드
        type:        DOOR_EVENT_TYPES 중 하나.
        received_at: **권위 있는 시각.** 도착 시점의 clock.now().
        reported_at: 라즈베리파이가 주장한 시각. 참고용이며 계산에 쓰지 않는다.
                     읽을 수 없으면 None.
        source_id:   보낸 기기 id. 어느 센서인지 구분한다.
        event_id:    멱등 처리용. 같은 id 를 두 번 받으면 두 번째는 버려도 된다.
        direction:   "in" | "out" | None. **백엔드가 채워준 경우에만 값이 있다.**
                     None 이 정상이고 흔한 값이다.
        payload:     원본 payload. 그대로 백엔드에 전달한다.
    """

    type: str
    received_at: float
    reported_at: float | None
    source_id: str
    event_id: str
    direction: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def clock_skew_sec(self) -> float | None:
        """라즈베리파이 시계가 얼마나 어긋났는가. 모르면 None."""
        if self.reported_at is None:
            return None
        return abs(self.received_at - self.reported_at)


def parse_door_event(message: Mapping[str, Any] | str | bytes) -> DoorEvent:
    """MQTT 페이로드를 DoorEvent 로 정규화한다.

    무엇을 하는가
        JSON 을 읽고, 타입을 검증하고, 시각을 도착 기준으로 바꿔 넣는다.

    누가 호출하는가
        door.mqtt 구독 콜백. 그리고 테스트가 직접(브로커 없이 전 경로를 돌린다).

    반환값
        DoorEvent. received_at 은 항상 clock.now() 다.

    예외
        DoorEventError — JSON 이 아니거나, dict 가 아니거나, 타입을 모른다.

    주의사항
        - `occurredAt` 을 못 읽어도 **실패로 처리하지 않는다.** reported_at=None 으로
          두고 계속 간다. 참고용 값 하나 때문에 문 이벤트를 버리면, 시계가 망가진
          라즈베리파이가 곧 현관 감시를 통째로 끄는 셈이 된다.
        - 시계가 크게 어긋나면 경고를 남긴다. 그게 망가진 RTC 를 발견하는 유일한
          방법이다. 값 자체는 여전히 쓰지 않는다.
    """
    raw = _as_mapping(message)

    event_type = str(raw.get("type") or "").strip().upper()
    if event_type not in DOOR_EVENT_TYPES:
        raise DoorEventError(
            f"unknown door event type {event_type!r}; "
            f"expected one of {sorted(DOOR_EVENT_TYPES)}"
        )

    received_at = clock.now()
    reported_at = _parse_occurred_at(raw.get("occurredAt"))

    event = DoorEvent(
        type=event_type,
        received_at=received_at,
        reported_at=reported_at,
        source_id=str(raw.get("sourceId") or ""),
        event_id=str(raw.get("eventId") or ""),
        direction=_parse_direction(raw),
        payload=raw.get("payload") if isinstance(raw.get("payload"), Mapping) else {},
    )

    skew = event.clock_skew_sec
    if skew is not None and skew > policy.DOOR_TIMESTAMP_SKEW_WARN_SEC:
        # 값을 고치지 않는다. 이미 received_at 을 쓰고 있으므로 동작은 안전하다.
        # 다만 이 로그가 없으면 망가진 RTC 를 아무도 발견하지 못한다.
        logger.warning(
            "door node clock is off by %.0fs (source=%s, type=%s); "
            "using arrival time as authoritative",
            skew, event.source_id, event.type,
        )

    return event


def _as_mapping(message: Mapping[str, Any] | str | bytes) -> Mapping[str, Any]:
    """dict / JSON 문자열 / bytes 를 모두 받는다."""
    if isinstance(message, Mapping):
        return message

    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DoorEventError(f"door event is not UTF-8: {error}") from error

    try:
        decoded = json.loads(message)
    except (TypeError, ValueError) as error:
        raise DoorEventError(f"door event is not JSON: {error}") from error

    if not isinstance(decoded, Mapping):
        raise DoorEventError(f"door event must be a JSON object, got {type(decoded).__name__}")
    return decoded


def _parse_occurred_at(value: object) -> float | None:
    """ISO 8601 문자열을 epoch 초로. 실패하면 None.

    실패를 예외로 올리지 않는 이유는 위 docstring 에 있다. 이 값은 참고용이다.
    """
    if isinstance(value, (int, float)):
        # 숫자로 오는 펌웨어도 있다. epoch 초로 간주한다.
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    # datetime.fromisoformat 은 3.10 에서 'Z' 를 읽지 못한다.
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("door event has an unreadable occurredAt %r; ignoring it", value)
        return None

    if parsed.tzinfo is None:
        # 타임존이 없는 값은 신뢰하지 않는다. 규약이 타임존을 요구하고 있고,
        # 없는 값을 로컬 시각으로 가정하면 9시간 어긋난 값이 조용히 들어온다.
        logger.warning("door event occurredAt %r has no time zone; ignoring it", value)
        return None

    return parsed.timestamp()


def _parse_direction(raw: Mapping[str, Any]) -> str | None:
    """백엔드가 채워 보낸 방향을 읽는다. 없으면 None 이고 그게 정상이다.

    직접 판정하지 않는다. 이 함수가 두 센서의 순서를 보기 시작하면, 그 순간
    방향 판정이 로봇에도 생긴 것이다 (CLAUDE.md §11).
    """
    payload = raw.get("payload")
    candidates = [raw.get("direction")]
    if isinstance(payload, Mapping):
        candidates.append(payload.get("direction"))

    for value in candidates:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized in DOOR_DIRECTIONS:
            return normalized
        if normalized:
            logger.warning("door event carries an unknown direction %r; treating as unknown",
                           value)
    return None
