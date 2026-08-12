# robot/ai_chat/tests/test_wake_door_gate.py
"""현관 이벤트 전의 "보미야"를 무시하는 게이트를 확인한다.

왜 필요한가
    2026-08-09 실기에서 문을 열기 49초 전에 웨이크워드가 감지됐다. 방향을
    읽지 못해(azimuth_deg=None) 로봇이 40도씩 전방위 회전 탐색을 돌았고,
    보는 사람에게는 오작동으로 보였다. 어르신이 귀가하기 전의 감지는
    오검출로 보고 무시한다.

이 파일이 검증하는 것
    1. DOOR_OPENED 를 받기 전에는 막고, 받은 뒤에는 통과시킨다.
    2. HEARTBEAT/MOTION 으로는 열리지 않는다 — 센서 생존 신호이지 귀가가 아니다.
    3. 문 구독자가 없으면 막지 않는다 — 웨이크워드가 통째로 죽으면 안 된다.
    4. WAKE_REQUIRE_DOOR_EVENT=false 로 끌 수 있다(현관 센서 없는 개발 환경).
"""

import json

from bomi_ai_chat import bootstrap
from bomi_ai_chat.door.mqtt import DoorSubscriber


class Runtime:
    """_wake_word_allowed 가 읽는 것은 door_subscriber 하나뿐이다."""

    def __init__(self, door_subscriber=None):
        self.door_subscriber = door_subscriber


class FakeDoor:
    def __init__(self, seen):
        self._seen = seen

    def has_seen_door_opened(self):
        return self._seen


def test_wake_is_blocked_before_any_door_event():
    assert bootstrap._wake_word_allowed(Runtime(FakeDoor(seen=False))) is False


def test_wake_is_allowed_after_a_door_event():
    assert bootstrap._wake_word_allowed(Runtime(FakeDoor(seen=True))) is True


def test_wake_is_allowed_when_the_door_watch_is_off():
    # 구독자가 없으면 문 이벤트가 영영 오지 않는다. 그때까지 막으면
    # 웨이크워드가 통째로 죽는다.
    assert bootstrap._wake_word_allowed(Runtime(None)) is True


def test_the_gate_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("WAKE_REQUIRE_DOOR_EVENT", "false")
    assert bootstrap._wake_word_allowed(Runtime(FakeDoor(seen=False))) is True


# ── 게이트를 여는 쪽: DoorSubscriber ─────────────────────────────────────────

def door_payload(event_type):
    return json.dumps(
        {
            "eventId": "e-1",
            "type": event_type,
            "occurredAt": "2026-08-09T09:00:00+09:00",
            "sourceId": "door_sensor",
            "payload": {},
        }
    )


def subscriber_seeing(monkeypatch, event_type):
    subscriber = DoorSubscriber("senior-1")
    # intake 는 저장소·백엔드를 건드린다. 게이트만 보므로 비활성화한다.
    monkeypatch.setattr(
        "bomi_ai_chat.door.mqtt.intake.ingest", lambda *a, **k: None
    )
    monkeypatch.setattr(DoorSubscriber, "_invoke_graph", lambda self, event: None)
    subscriber.handle_payload(door_payload(event_type))
    return subscriber


def test_a_fresh_subscriber_has_not_seen_the_door(monkeypatch):
    assert DoorSubscriber("senior-1").has_seen_door_opened() is False


def test_door_opened_opens_the_gate(monkeypatch):
    assert subscriber_seeing(monkeypatch, "DOOR_OPENED").has_seen_door_opened() is True


def test_heartbeat_does_not_open_the_gate(monkeypatch):
    assert subscriber_seeing(monkeypatch, "HEARTBEAT").has_seen_door_opened() is False


def test_motion_does_not_open_the_gate(monkeypatch):
    assert (
        subscriber_seeing(monkeypatch, "MOTION_DETECTED").has_seen_door_opened()
        is False
    )
