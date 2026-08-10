# robot/ai_chat/tests/test_homecoming_gate.py
"""귀가 대본이 도는 동안 "보미야"를 막는 게이트를 확인한다.

왜 필요한가
    시연에서 문이 열린 뒤 현관 이동 -> 인사 -> 추종 -> 온습도 마무리까지가 하나의
    대본이다. 현관으로 가는 동안 메인 루프는 웨이크워드 대기 상태라, 그때 잡힌
    "보미야"가 대본을 버리고 거실 호출 시나리오를 새로 시작한다.

이 파일이 검증하는 것
    1. DOOR_OPENED 로 닫히고, 귀가 인사가 끝나면 열린다.
    2. 마감 시각이 지나면 스스로 열린다 — 대본이 실패해도 웨이크워드가 죽지 않는다.
    3. WAKE_BLOCK_DURING_HOMECOMING=false 로 끌 수 있다.
    4. 귀가 인사가 아닌 대화(복약·온습도)는 게이트를 건드리지 않는다.
"""

import json

from bomi_ai_chat import bootstrap
from bomi_ai_chat.door.mqtt import DoorSubscriber
from bomi_ai_chat.homecoming_gate import HomecomingGate


class _Clock:
    """테스트가 300초를 실제로 기다릴 수는 없다."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Runtime:
    """_wake_word_allowed 가 읽는 것은 이 둘뿐이다."""

    def __init__(self, gate=None, door_subscriber=None):
        self.homecoming_gate = gate
        self.door_subscriber = door_subscriber


class _Door:
    def has_seen_door_opened(self):
        return True


class _Command:
    def __init__(self, intent):
        self.intent = intent


# ── 게이트 자체 ──────────────────────────────────────────────────────────────

def test_starts_closed() -> None:
    assert HomecomingGate().is_running() is False


def test_start_closes_and_finish_opens() -> None:
    gate = HomecomingGate(clock=_Clock())

    gate.start()
    assert gate.is_running() is True

    gate.finish()
    assert gate.is_running() is False


def test_opens_itself_after_the_deadline() -> None:
    """대본이 실패해 finish 를 부를 사람이 없어도 웨이크워드가 돌아온다."""
    clock = _Clock()
    gate = HomecomingGate(clock=clock)
    gate.start()

    clock.now = 299.0
    assert gate.is_running() is True

    clock.now = 301.0
    assert gate.is_running() is False


def test_the_deadline_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("HOMECOMING_GATE_TIMEOUT_SEC", "10")
    clock = _Clock()
    gate = HomecomingGate(clock=clock)
    gate.start()

    clock.now = 11.0
    assert gate.is_running() is False


def test_a_broken_deadline_falls_back_to_the_default(monkeypatch) -> None:
    """숫자가 아니면 게이트를 죽이지 않고 기본값으로 돌아간다."""
    monkeypatch.setenv("HOMECOMING_GATE_TIMEOUT_SEC", "곧")
    clock = _Clock()
    gate = HomecomingGate(clock=clock)
    gate.start()

    clock.now = 299.0
    assert gate.is_running() is True


def test_a_second_door_event_restarts_the_deadline() -> None:
    clock = _Clock()
    gate = HomecomingGate(clock=clock)
    gate.start()

    clock.now = 250.0
    gate.start()
    clock.now = 400.0

    assert gate.is_running() is True


def test_blocking_can_be_turned_off(monkeypatch) -> None:
    gate = HomecomingGate(clock=_Clock())
    gate.start()
    assert gate.blocks_wake_word() is True

    monkeypatch.setenv("WAKE_BLOCK_DURING_HOMECOMING", "false")
    assert gate.blocks_wake_word() is False
    # 끄는 것은 차단뿐이다. 진행 여부는 그대로 들고 있어야 finish 가 맞는다.
    assert gate.is_running() is True


# ── 웨이크워드 게이트와의 연결 ───────────────────────────────────────────────

def test_wake_is_blocked_while_the_homecoming_script_runs() -> None:
    gate = HomecomingGate(clock=_Clock())
    gate.start()
    runtime = _Runtime(gate=gate, door_subscriber=_Door())

    assert bootstrap._wake_word_allowed(runtime) is False


def test_wake_returns_after_the_script_finishes() -> None:
    gate = HomecomingGate(clock=_Clock())
    gate.start()
    runtime = _Runtime(gate=gate, door_subscriber=_Door())

    gate.finish()

    assert bootstrap._wake_word_allowed(runtime) is True


def test_no_gate_does_not_block() -> None:
    """게이트가 없는 실행(테스트·구버전 Runtime)에서는 막지 않는다."""
    assert bootstrap._wake_word_allowed(
        _Runtime(gate=None, door_subscriber=_Door())) is True


# ── 문 이벤트가 게이트를 닫는다 ──────────────────────────────────────────────

def _door_payload(event_type):
    return json.dumps({
        "eventId": "11111111-1111-4111-8111-111111111111",
        "type": event_type,
        "occurredAt": "2026-08-10T04:23:42+09:00",
        "sourceId": "door-sensor-01",
        "payload": {},
    })


def test_door_opened_closes_the_gate() -> None:
    gate = HomecomingGate(clock=_Clock())
    subscriber = DoorSubscriber("senior", homecoming_gate=gate)

    subscriber.handle_payload(_door_payload("DOOR_OPENED"))

    assert gate.is_running() is True


def test_other_door_events_do_not_close_the_gate() -> None:
    """HEARTBEAT·MOTION 은 센서 생존 신호이지 귀가가 아니다."""
    gate = HomecomingGate(clock=_Clock())
    subscriber = DoorSubscriber("senior", homecoming_gate=gate)

    subscriber.handle_payload(_door_payload("HEARTBEAT"))
    subscriber.handle_payload(_door_payload("MOTION_DETECTED"))
    subscriber.handle_payload(_door_payload("DOOR_CLOSED"))

    assert gate.is_running() is False


def test_a_broken_gate_does_not_break_the_door_watch() -> None:
    class _Exploding:
        def start(self):
            raise RuntimeError("boom")

    subscriber = DoorSubscriber("senior", homecoming_gate=_Exploding())

    assert subscriber.handle_payload(_door_payload("DOOR_OPENED")) is True
    assert subscriber.has_seen_door_opened() is True


# ── 대화가 끝나면 게이트를 연다 ──────────────────────────────────────────────

def test_the_homecoming_greeting_releases_the_gate() -> None:
    gate = HomecomingGate(clock=_Clock())
    gate.start()

    bootstrap._release_homecoming_gate(
        _Runtime(gate=gate), _Command("HOMECOMING_GREETING"))

    assert gate.is_running() is False


def test_other_intents_leave_the_gate_alone() -> None:
    """복약·온습도 대화는 귀가 대본이 아니다."""
    gate = HomecomingGate(clock=_Clock())
    gate.start()

    bootstrap._release_homecoming_gate(
        _Runtime(gate=gate), _Command("MEDICATION_REMINDER"))

    assert gate.is_running() is True
