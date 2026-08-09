# robot/ai_chat/tests/test_backend_conversation_loop.py
"""backend 대화(START_CONVERSATION)가 메인 루프에서 진행되는 전 경로 회귀.

이 파일이 검증하는 것
    1. 큐에 쌓인 backend 대화가 웨이크워드 대기를 인터럽트하고, 실제
       "보미야" 흐름(호출 응답·WAKE_WORD_DETECTED 발행)을 타지 않는다.
    2. 첫 문장은 backend_command 경로(app.invoke)로 나가고, 이어지는 발화는
       기존 _run_graph_conversation 세션 기계를 그대로 탄다 — 새 종료 조건을
       만들지 않는다.
    3. 종료 사유(farewell/no_speech/interrupted/seed 실패)가 CONVERSATION_ENDED
       의 올바른 outcome 으로 옮겨진다.
    4. 큐가 비어 있으면(backend 대화가 없으면) 기존 웨이크워드 동작이 조금도
       달라지지 않는다 — 이 스프린트 전 회귀 스위트(725건)가 이미 그 계약을
       고정하고 있으므로, 여기서는 "인터럽트 훅이 얹혀도 정상 경로에 영향
       없음"만 짧게 확인한다.

참고
    CLAUDE.md §3(안전·배선), bootstrap.py 모듈 내 "백엔드가 시작하는 대화" 절
"""

import queue

from bomi_ai_chat import bootstrap
from bomi_ai_chat.contracts import ai_commands as contract

SENIOR = "senior-1"
NOW = 1_700_000_000.0


def settings_with(settings_factory, **extra):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        SENIOR_ID=SENIOR,
        **extra,
    )


def start_conversation_command(**overrides) -> contract.StartConversationCommand:
    body = {
        "commandId": "cmd-conv-1",
        "scenarioId": "scenario-1",
        "conversationId": "conversation-1",
        "robotId": "bomi-AA001",
        "type": "START_CONVERSATION",
        "occurredAt": "2026-08-04T18:10:08+09:00",
        "expiresAt": "2026-08-04T18:20:08+09:00",
        "payload": {
            "seniorId": "senior-uuid-1",
            "intent": "HOMECOMING_GREETING",
            "text": "다녀오셨어요? 오늘 외출은 어떠셨어요?",
            "triggerContext": {},
        },
    }
    body.update(overrides)
    import json
    return contract.parse_start_conversation(json.dumps(body))


class RecordingApp:
    """runtime.app 대역 — invoke 호출을 그대로 기록한다."""

    def __init__(self, *, fail_on_call: int | None = None):
        self.invocations: list[tuple[dict, dict]] = []
        self._fail_on_call = fail_on_call

    def invoke(self, state, config):
        self.invocations.append((state, config))
        if self._fail_on_call == len(self.invocations):
            raise RuntimeError("graph exploded")
        return {}


class RecordingSubscriber:
    """runtime.ai_command_subscriber 대역."""

    def __init__(self):
        self.ended: list[tuple] = []

    def publish_conversation_ended(self, command, outcome, reason_code=None):
        self.ended.append((command.conversation_id, outcome, reason_code))


class RecordingEventPublisher:
    """진짜 "보미야" 흐름에서만 불려야 하는 발행자 — 호출 여부가 증거다."""

    def __init__(self):
        self.publishes = 0

    def publish_wake_word(self, **kwargs):
        self.publishes += 1

    def stop(self):
        pass


class RecordingSearchSignal:
    def __init__(self):
        self.events = []

    def send_wake(self):
        self.events.append(("wake", None))

    def send_stop(self, reason):
        self.events.append(("stop", reason))


class FixedAmbient:
    def conversation_text(self):
        return "할머니, 지금 실내 온도가 31도로 조금 높아요. 더우시진 않으세요?"


class InterruptibleWake:
    """실제 WakeWordDetector 의 interrupt_check 계약을 흉내 낸 대역.

    wait_for_wake() 는 (a) interrupt_check 가 참이면 즉시 반환하고,
    (b) 아니면 wakes_left 를 하나 쓰고, 그마저 없으면 KeyboardInterrupt.
    """

    def __init__(self, wakes: int = 0):
        self.wakes_left = wakes
        self.interrupt_check = None
        self.calls = 0

    def wait_for_wake(self):
        self.calls += 1
        if self.interrupt_check is not None and self.interrupt_check():
            return
        if self.wakes_left == 0:
            raise KeyboardInterrupt
        self.wakes_left -= 1


class ScriptedAudio:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    def capture(self, onset_timeout_seconds=None):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class ScriptedStt:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else ""


def _make_runtime(*, app=None, subscriber=None):
    pending: queue.Queue = queue.Queue(maxsize=4)
    return bootstrap.Runtime(
        app=app or RecordingApp(),
        senior_id=SENIOR,
        ai_command_subscriber=subscriber or RecordingSubscriber(),
        backend_conversation_queue=pending,
    ), pending


# ── 1+2. 큐에 있으면 웨이크 흐름을 건너뛰고 backend_command 로 말한다 ─────────


def test_pending_conversation_skips_wake_ack_and_speaks_the_seed_text(
    monkeypatch, settings_factory, frozen_clock,
):
    frozen_clock(start=NOW)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt("고마워요"))
    turns: list[str] = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    app = RecordingApp()
    runtime, pending = _make_runtime(app=app)
    command = start_conversation_command()
    pending.put_nowait(command)

    wake = InterruptibleWake(wakes=0)  # "보미야"는 한 번도 안 온다
    event_publisher = RecordingEventPublisher()

    bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(b"1"), settings_with(settings_factory),
        wake=wake, event_publisher=event_publisher, max_turns=2,
    )

    # 첫 호출이 seed 문장을 backend_command 경로로 보냈다.
    assert len(app.invocations) == 1
    state, config = app.invocations[0]
    assert state["trigger_type"] == "backend_command"
    assert state["command"]["text"] == "다녀오셨어요? 오늘 외출은 어떠셨어요?"
    assert state["command"]["intent"] == "greeting"
    assert state["command"]["origin"] == "scenario:HOMECOMING_GREETING"
    assert config == {"configurable": {"thread_id": SENIOR}}

    # 진짜 "보미야" 흐름(호출 응답 발행)은 타지 않았다.
    assert event_publisher.publishes == 0

    # 이어지는 발화는 정상적으로 run_user_turn 을 탄다(세션 계속).
    assert turns == ["고마워요"]


def test_homecoming_ends_after_two_user_turns(
    monkeypatch, settings_factory, frozen_clock,
):
    """귀가 인사는 사용자 답변 두 번 뒤 COMPLETED로 닫아 추종을 시작한다."""
    frozen_clock(start=NOW)
    monkeypatch.setattr(
        "bomi_ai_chat.stt.client.STTClient",
        lambda settings: ScriptedStt("오늘 괜찮았어", "이제 좀 쉬려고"),
    )
    heard: list[str] = []
    closing_flags: list[bool] = []

    def record_turn(app, senior, text, **kwargs):
        heard.append(text)
        closing_flags.append(bool(kwargs.get("closing_turn")))
        return {}

    monkeypatch.setattr(
        "bomi_ai_chat.graph.turn.run_user_turn",
        record_turn,
    )

    subscriber = RecordingSubscriber()
    runtime, pending = _make_runtime(subscriber=subscriber)
    pending.put_nowait(start_conversation_command())

    bootstrap.run_conversation_loop(
        runtime,
        ScriptedAudio(b"1", b"2"),
        settings_with(settings_factory),
        wake=InterruptibleWake(wakes=0),
        event_publisher=RecordingEventPublisher(),
        max_turns=3,  # seed 1 + 사용자 발화 2
    )

    assert heard == ["오늘 괜찮았어", "이제 좀 쉬려고"]
    assert closing_flags == [False, True]
    assert subscriber.ended == [("conversation-1", "COMPLETED", None)]


def test_homecoming_wake_word_removes_two_turn_limit(
    monkeypatch, settings_factory, frozen_clock,
):
    frozen_clock(start=NOW)
    monkeypatch.setattr(
        "bomi_ai_chat.stt.client.STTClient",
        lambda settings: ScriptedStt(
            "보미야 오늘 있었던 일 말해줄게",
            "그리고 친구도 만났어",
            "이제 갈게",
        ),
    )
    heard: list[str] = []
    closing_flags: list[bool] = []

    def record_turn(app, senior, text, **kwargs):
        heard.append(text)
        closing_flags.append(bool(kwargs.get("closing_turn")))
        return {}

    monkeypatch.setattr(
        "bomi_ai_chat.graph.turn.run_user_turn",
        record_turn,
    )

    subscriber = RecordingSubscriber()
    runtime, pending = _make_runtime(subscriber=subscriber)
    pending.put_nowait(start_conversation_command())

    bootstrap.run_conversation_loop(
        runtime,
        ScriptedAudio(b"1", b"2", b"3"),
        settings_with(settings_factory),
        wake=InterruptibleWake(wakes=0),
        event_publisher=RecordingEventPublisher(),
        max_turns=4,
    )

    assert heard == [
        "보미야 오늘 있었던 일 말해줄게",
        "그리고 친구도 만났어",
        "이제 갈게",
    ]
    assert closing_flags == [False, False, False]
    assert subscriber.ended == [("conversation-1", "COMPLETED", None)]


def test_backend_conversation_queue_is_checked_before_the_real_wake_flow(
    monkeypatch, settings_factory, frozen_clock,
):
    """큐에 아무것도 없으면 정상적으로 진짜 "보미야" 흐름을 탄다(회귀 안전망)."""
    frozen_clock(start=NOW)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt("안녕"))
    turns: list[str] = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    app = RecordingApp()
    runtime, _pending = _make_runtime(app=app)
    # 이 테스트의 전제는 '진짜 보미야가 한 번 온다'이다. 0 이면 첫 wait_for_wake 가
    # 곧장 KeyboardInterrupt 를 던져 루프가 웨이크워드 발행에 닿지도 못한다.
    wake = InterruptibleWake(wakes=1)
    event_publisher = RecordingEventPublisher()

    bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(b"1"), settings_with(settings_factory),
        wake=wake, event_publisher=event_publisher, max_turns=1,
    )

    assert app.invocations == [], "backend_command 경로는 타지 않아야 한다"
    assert event_publisher.publishes == 1, "진짜 웨이크워드는 정상 발행돼야 한다"
    assert turns == ["안녕"]


# ── 3. CONVERSATION_ENDED outcome 매핑 ───────────────────────────────────────


def test_post_homecoming_follow_stops_before_ambient_conversation(monkeypatch):
    app = RecordingApp()
    subscriber = RecordingSubscriber()
    subscriber._ambient = FixedAmbient()
    signal = RecordingSearchSignal()
    runtime = bootstrap.Runtime(
        app=app,
        senior_id=SENIOR,
        ai_command_subscriber=subscriber,
        search_signal=signal,
    )
    heard = []
    monkeypatch.setenv("HOMECOMING_FOLLOW_SECONDS", "0")
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "bomi_ai_chat.graph.turn.run_user_turn",
        lambda app, senior, text, **kwargs: heard.append((text, kwargs)) or {},
    )

    turns, reason = bootstrap._run_homecoming_follow_ambient_phase(
        runtime, ScriptedAudio(b"reply"), ScriptedStt("조금 덥구나"), 3)

    assert signal.events == [
        ("wake", None),
        ("stop", "homecoming_follow_phase_complete"),
    ]
    assert app.invocations[0][0]["command"]["origin"] == "homecoming:post_follow_ambient"
    assert "31도로 조금 높아요" in app.invocations[0][0]["command"]["text"]
    assert heard == [("조금 덥구나", {"closing_turn": True})]
    assert (turns, reason) == (5, "homecoming_follow_complete")


def test_post_follow_completion_tells_backend_to_return():
    subscriber = RecordingSubscriber()
    runtime, _pending = _make_runtime(subscriber=subscriber)
    command = start_conversation_command()

    bootstrap._publish_conversation_ended(
        runtime, command, "homecoming_follow_complete")

    assert subscriber.ended == [(
        "conversation-1", "COMPLETED", "HOMECOMING_FOLLOW_COMPLETED")]


def test_farewell_ends_the_conversation_as_completed(
    monkeypatch, settings_factory, frozen_clock,
):
    frozen_clock(start=NOW)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt("이제 됐어"))
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: {})

    subscriber = RecordingSubscriber()
    runtime, pending = _make_runtime(subscriber=subscriber)
    command = start_conversation_command()
    pending.put_nowait(command)
    wake = InterruptibleWake(wakes=0)

    bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(b"1"), settings_with(settings_factory),
        wake=wake, event_publisher=RecordingEventPublisher(), max_turns=2,
    )

    assert subscriber.ended == [("conversation-1", "COMPLETED", None)]


def test_silence_ends_the_conversation_as_no_response(
    monkeypatch, settings_factory, frozen_clock,
):
    frozen_clock(start=NOW)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt())  # 응답 없음
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: {})

    subscriber = RecordingSubscriber()
    runtime, pending = _make_runtime(subscriber=subscriber)
    command = start_conversation_command()
    pending.put_nowait(command)
    wake = InterruptibleWake(wakes=1)

    bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(), settings_with(settings_factory),
        wake=wake, event_publisher=RecordingEventPublisher(), max_turns=2,
    )

    assert subscriber.ended == [("conversation-1", "NO_RESPONSE", None)]


def test_seed_turn_failure_publishes_failed_and_does_not_crash_the_loop(
    monkeypatch, settings_factory, frozen_clock,
):
    """★ 첫 문장 발화 자체가 예외로 죽어도 루프는 살아 있고 백엔드는 알게 된다."""
    frozen_clock(start=NOW)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt())

    app = RecordingApp(fail_on_call=1)
    subscriber = RecordingSubscriber()
    runtime, pending = _make_runtime(app=app, subscriber=subscriber)
    command = start_conversation_command()
    pending.put_nowait(command)
    wake = InterruptibleWake(wakes=0)

    # 루프가 죽지 않는다는 것 자체가 이 테스트의 핵심 — max_turns=1 로 한
    # 바퀴만 돌리고 KeyboardInterrupt 없이 정상 반환하는지 본다.
    turns = bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(), settings_with(settings_factory),
        wake=InterruptibleWakeOnce(wake), event_publisher=RecordingEventPublisher(),
        max_turns=1,
    )

    assert turns == 0  # seed 실패는 turns 를 늘리지 않는다
    assert subscriber.ended == [("conversation-1", "FAILED", "INTERNAL_ERROR")]


class InterruptibleWakeOnce:
    """max_turns=1 에서 두 번째 wait_for_wake 호출을 막기 위한 아주 얇은 래퍼.

    run_conversation_loop 은 max_turns 를 '그래프 턴 수'로 세므로, seed 가
    실패해 turns 가 늘지 않으면 같은 반복이 다시 wait_for_wake 를 부를 수
    있다 — 이 대역은 그 두 번째 호출에서 KeyboardInterrupt 로 확실히 멈춘다.
    """

    def __init__(self, inner):
        self._inner = inner
        self._calls = 0

    @property
    def interrupt_check(self):
        return self._inner.interrupt_check

    @interrupt_check.setter
    def interrupt_check(self, value):
        self._inner.interrupt_check = value

    def wait_for_wake(self):
        self._calls += 1
        if self._calls > 1:
            raise KeyboardInterrupt
        return self._inner.wait_for_wake()
