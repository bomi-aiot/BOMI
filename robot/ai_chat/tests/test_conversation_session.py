"""세션 수명주기 — 자연스러운 대화 Phase 1 회귀.

이 파일이 처음이다
    그래프 '안'은 566개 테스트로 두껍게 덮여 있었지만, 그 바깥 — 웨이크워드 감지
    → 호출 응답 → 세션 지속 → 종료 → 재대기 — 는 자동 테스트가 0건이었다
    (docs/natural-conversation/current-state-audit.md §3-J). 실기(233)에서 사고가
    난 곳이 정확히 이 계층이다.

이 파일이 검증하는 것
    1. 시나리오 A: 웨이크워드 이전에는 어떤 발화도 처리되지 않는다
    2. 시나리오 B: 세션 안에서는 웨이크워드 없이 여러 발화가 이어진다
    3. 시나리오 L: 마무리 문구("이제 됐어")로 세션이 닫히고, 다시 웨이크워드
       대기로 돌아가며, 마무리 발화 자체는 그래프로 처리된다(= 종료 응답 존재)
    4. 무응답 15초: 조용히 세션이 닫힌다 (턴 0개, 재대기)
    5. 세션 상태 전이표(SessionState/next_state)의 정확성
    6. 감사 결함 B1: 재생이 '정상 종료'된 다음 턴은 barge-in 이 아니다
    7. 감사 결함 B2: barge-in 으로 잘린 나머지가 게이트에서 실제로 재경쟁한다

참고
    CLAUDE.md §13 (barge-in 배포 상태), docs/natural-conversation/implementation-plan.md Phase 1
"""

import pytest

from bomi_ai_chat import bootstrap, conversation_control
from bomi_ai_chat.conversation_control import SessionState, next_state
from bomi_ai_chat.graph import gate, ingress, output
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    # 모듈 전역 핸들을 반드시 비운다. 남기면 다음 테스트가 이 테스트의 재생
    # 핸들을 상속받아 barge-in 판정이 오염된다.
    output.TTS_HANDLES.clear()
    output.SPEECH_CONTEXT.clear()


def settings_with(settings_factory, **extra):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        SENIOR_ID=SENIOR,
        **extra,
    )


# ── 1. 세션 상태 전이표 ──────────────────────────────────────────────────────


def test_the_happy_path_walks_every_state():
    """웨이크 → 발화 → 처리 → 응답 → (반복) → 작별 → 닫힘 → IDLE."""
    s = SessionState.IDLE
    s = next_state(s, "wake_detected")
    assert s is SessionState.LISTENING
    s = next_state(s, "speech_captured")
    assert s is SessionState.PROCESSING
    s = next_state(s, "turn_done")
    assert s is SessionState.RESPONDING
    s = next_state(s, "playback_done")
    assert s is SessionState.LISTENING
    s = next_state(s, "farewell")
    assert s is SessionState.ENDING
    s = next_state(s, "session_closed")
    assert s is SessionState.IDLE


def test_stt_failure_keeps_listening_without_reasking():
    """STT 실패는 종료 사유가 아니다. 되묻지 않고 같은 상태에 머문다."""
    assert next_state(SessionState.LISTENING, "stt_empty") is SessionState.LISTENING


@pytest.mark.parametrize("event", ["no_speech", "interrupted", "farewell"])
def test_every_ending_reason_goes_through_ending(event):
    """종료 사유 3종이 전부 ENDING 을 거친다 — 정리 지점이 한 곳이어야 한다."""
    assert next_state(SessionState.LISTENING, event) is SessionState.ENDING


def test_processing_a_turn_while_idle_is_a_broken_gate():
    """★ IDLE 에서 발화가 처리되면 웨이크워드 게이트가 뚫린 것이다.

    조용히 넘어가면 실기에서야 드러난다. 전이표가 요란하게 실패해야
    테스트가 먼저 잡는다 (시나리오 A 의 논리적 보증).
    """
    with pytest.raises(ValueError, match="IDLE"):
        next_state(SessionState.IDLE, "speech_captured")


def test_live_loop_survives_a_bookkeeping_mistake(caplog):
    """상태 '기록'의 실수가 상태 '기계'(루프)를 죽이면 안 된다."""
    with caplog.at_level("WARNING"):
        result = bootstrap._advance(SessionState.IDLE, "speech_captured")
    assert result is SessionState.IDLE
    assert "session bookkeeping" in caplog.text


# ── 2. 세션 루프 (가짜 오디오/STT 로 전체 흐름) ──────────────────────────────


class GateKeeperWake:
    """정해진 횟수만 깨어나고, 다 쓰면 KeyboardInterrupt 로 루프를 끝낸다.

    events 리스트를 공유해 '언제 깨웠는지'와 '언제 수음했는지'의 순서를 남긴다 —
    시나리오 A(웨이크 이전 무반응)는 이 순서가 증거다.
    """

    def __init__(self, events: list, wakes: int):
        self.events = events
        self.wakes_left = wakes
        self.calls = 0

    def wait_for_wake(self):
        if self.wakes_left == 0:
            raise KeyboardInterrupt
        self.wakes_left -= 1
        self.calls += 1
        self.events.append("wake")


class SessionAudio:
    """정해진 발화 오디오를 순서대로 내보낸다. b"" 는 '무응답(onset 타임아웃)'."""

    def __init__(self, events: list, *chunks):
        self.events = events
        self.chunks = list(chunks)

    def capture(self, onset_timeout_seconds=None):
        self.events.append("capture")
        if not self.chunks:
            # 발화가 다 떨어졌다 = 어르신이 더 말하지 않는다 = 무응답 종료.
            return b""
        return self.chunks.pop(0)


class ScriptedStt:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else ""


def run_loop(monkeypatch, settings_factory, *, wakes, chunks, stt_texts):
    """세션 루프를 가짜 오디오/STT/그래프로 돌리고 (이벤트 순서, 처리된 발화, 턴 수)를 준다."""
    events: list = []
    turns: list = []
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt(*stt_texts))
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    wake = GateKeeperWake(events, wakes=wakes)
    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    count = bootstrap.run_conversation_loop(
        runtime, SessionAudio(events, *chunks), settings_with(settings_factory),
        wake=wake)
    return events, turns, count, wake


def test_scenario_a_nothing_is_processed_before_the_wakeword(
    monkeypatch, settings_factory, frozen_clock):
    """★ 시나리오 A: 가족이 "순자야, 병원 갈 거야?"라고 해도 로봇은 무반응.

    구조적 보증: wait_for_wake 가 리턴하기 전에는 capture 자체가 호출되지 않는다.
    이벤트 순서에서 첫 'capture' 는 반드시 첫 'wake' 뒤여야 한다.
    """
    frozen_clock(start=1_700_000_000.0)
    events, turns, _count, _wake = run_loop(
        monkeypatch, settings_factory,
        wakes=1, chunks=[b"a"], stt_texts=["안녕"])

    assert "capture" in events, "웨이크 후에는 수음이 열려야 한다"
    assert events.index("wake") < events.index("capture"), \
        "웨이크워드 이전에 수음이 열리면 게이트가 뚫린 것"


def test_scenario_b_one_wake_carries_multiple_utterances(
    monkeypatch, settings_factory, frozen_clock):
    """★ 시나리오 B: "보미야" 한 번으로 후속 질문("비는?")까지 이어진다."""
    frozen_clock(start=1_700_000_000.0)
    _events, turns, count, wake = run_loop(
        monkeypatch, settings_factory,
        wakes=1, chunks=[b"1", b"2"],
        stt_texts=["오늘 날씨 어때", "비는 와"])

    assert turns == ["오늘 날씨 어때", "비는 와"], \
        "두 발화 모두 웨이크워드 재요구 없이 그래프에 도달해야 한다"
    assert count == 2
    assert wake.calls == 1, "대화 중간에 웨이크워드를 다시 요구하면 안 된다"


def test_scenario_l_farewell_closes_and_rearms_the_wakeword(
    monkeypatch, settings_factory, frozen_clock):
    """★ 시나리오 L: "이제 됐어" → 그 발화에 응답 → 세션 종료 → 재대기.

    '종료 응답'은 별도의 고정 인사가 아니라 마무리 발화에 대한 그래프의 응답이다 —
    run_user_turn 이 마무리 발화도 받았는지가 그 증거다. 종료 뒤 루프는 다시
    wait_for_wake 로 돌아가야 한다(두 번째 wake 호출이 그 증거).
    """
    frozen_clock(start=1_700_000_000.0)
    _events, turns, count, wake = run_loop(
        monkeypatch, settings_factory,
        wakes=1, chunks=[b"1", b"2", b"3"],
        stt_texts=["오늘 날씨 어때", "고마워", "이제 됐어"])

    assert turns[-1] == "이제 됐어", "마무리 발화도 응답을 받아야 한다(시나리오 L)"
    assert count == 3
    # 세션이 닫힌 뒤 루프가 다시 웨이크 대기로 갔고, GateKeeperWake 의 잔여
    # 횟수가 0 이라 KeyboardInterrupt 로 프로그램이 끝났다. 즉 두 번째
    # wait_for_wake 호출이 실제로 일어났다.
    assert wake.wakes_left == 0


def test_silence_ends_the_session_quietly(monkeypatch, settings_factory, frozen_clock):
    """무응답 15초(onset 타임아웃) → 로봇은 아무 말 없이 세션을 닫고 재대기.

    빈 집에 "왜 말이 없으세요?"라고 묻는 로봇을 막는다 (§14 — 침묵이 자연).
    """
    frozen_clock(start=1_700_000_000.0)
    _events, turns, count, wake = run_loop(
        monkeypatch, settings_factory,
        wakes=1, chunks=[],  # 첫 리슨부터 무응답
        stt_texts=[])

    assert turns == [], "무응답에 턴이 생기면 안 된다"
    assert count == 0
    assert wake.wakes_left == 0, "세션 종료 후 다시 웨이크워드 대기로 돌아가야 한다"


def test_farewell_cue_matches_the_scenario_phrase():
    """시나리오 L 의 실제 문구가 큐 목록에 있어야 한다. 완료 보고와는 구분한다."""
    assert conversation_control.is_farewell("이제 됐어") is True
    assert conversation_control.is_farewell("약 다 먹었어, 됐어") is False, \
        "'됐어' 단독은 완료 보고일 수 있다 — 종료로 오인하면 안 된다"


# ── 3. 감사 결함 B1: 정상 종료된 재생은 barge-in 이 아니다 ───────────────────


class DoneHandle:
    """재생이 이미 끝난 핸들."""

    is_done = True

    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def remaining_sentences(self):
        return []


class LiveHandle:
    """아직 재생 중인 핸들."""

    is_done = False

    def __init__(self, remaining):
        self.cancelled = False
        self._remaining = remaining

    def cancel(self):
        self.cancelled = True

    def remaining_sentences(self):
        return list(self._remaining)


def reactive_state(**overrides):
    return {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": "무릎이 아파",
        "user_input_duration_sec": 2.0,
        "speaking": True,
        **overrides,
    }


def test_a_turn_after_normal_playback_is_not_a_bargein(frozen_clock):
    """★ 감사 결함 B1 의 회귀.

    emit 은 speaking=True 를 쓰지만 재생이 '정상 종료'될 때 되돌리는 노드가 없다.
    그래서 반이중 대기로 응답을 다 듣고 말한 다음 발화조차 state 상으로는
    '끼어들기'였다. 핸들이 끝나 있으면 평범한 턴으로 바로잡아야 한다.
    """
    frozen_clock(start=1_700_000_000.0)
    handle = DoneHandle()
    output.TTS_HANDLES[SENIOR] = handle

    out = ingress.note_interaction(reactive_state())

    assert out["speaking"] is False, "재생이 끝났으면 말하는 중이 아니다"
    assert handle.cancelled is False, "끝난 재생을 '취소'하면 안 된다 — 끼어들기가 아니다"
    assert "interrupted_remainder" not in out, "재큐할 나머지도 없어야 한다"
    assert SENIOR not in output.TTS_HANDLES, "끝난 핸들은 정리되어야 한다"


def test_a_turn_with_no_handle_at_all_is_not_a_bargein(frozen_clock):
    """핸들이 아예 없으면(재생기 미장착 환경) 역시 평범한 턴이다."""
    frozen_clock(start=1_700_000_000.0)

    out = ingress.note_interaction(reactive_state())

    assert out["speaking"] is False
    assert "interrupted_remainder" not in out


def test_a_real_interruption_still_yields_and_extracts_the_remainder(frozen_clock):
    """진짜 끼어들기(핸들이 살아 있음)는 기존대로 양보하고 나머지를 꺼낸다."""
    frozen_clock(start=1_700_000_000.0)
    handle = LiveHandle(remaining=["그리고 인슐린은 저녁에 맞으세요."])
    output.TTS_HANDLES[SENIOR] = handle
    output.SPEECH_CONTEXT[SENIOR] = {
        "intent": "schedule", "priority": "high", "origin": "scheduler|meds",
    }

    out = ingress.note_interaction(reactive_state())

    assert out["speaking"] is False
    assert handle.cancelled is True, "살아 있는 재생은 양보(취소)해야 한다"
    remainder = out["interrupted_remainder"]
    assert remainder is not None
    assert remainder["seed"] == "그리고 인슐린은 저녁에 맞으세요."
    assert remainder["priority"] == "high", "나머지는 원래 우선순위를 유지한다"


# ── 4. 감사 결함 B2: 잘린 나머지가 게이트에서 재경쟁한다 ─────────────────────

# 낮 시간(서울 14시) 기준. quiet hours 창(22:00~07:00) 밖이다.
DAYTIME_EPOCH = 1785542400.0 + (14.0 - 9.0) * 3600.0

DAY_PROFILE = {
    "timeZone": "Asia/Seoul",
    "quietHoursStart": "22:00",
    "quietHoursEnd": "07:00",
}


def proactive_state(**overrides):
    return {
        "senior_id": SENIOR,
        "trigger_type": "proactive",
        "ctx": {"profile": DAY_PROFILE},
        **overrides,
    }


def remainder_proposal(**extra):
    return {
        "intent": "schedule",
        "priority": "high",
        "seed": "그리고 인슐린은 저녁에 맞으세요.",
        "origin": "scheduler|meds|resumed",
        "meta": {"resumed": True},
        **extra,
    }


def test_the_interrupted_remainder_competes_and_wins(frozen_clock):
    """★ 감사 결함 B2 의 회귀 — 잘린 나머지가 실제로 다시 말해진다.

    이 배선이 없으면 "복약 두 알, 그리고 인슐린은—" 이 잘렸을 때 인슐린 이야기가
    영원히 사라진다 (§13.3). 나머지는 다음 능동 턴의 게이트에서 다른 제안과
    같은 규칙으로 경쟁해야 하고, 이기면 state 에서 소비되어야 한다.
    """
    frozen_clock(start=DAYTIME_EPOCH)
    state = proactive_state(interrupted_remainder=remainder_proposal())

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "speak"
    assert result["user_input"] == "그리고 인슐린은 저녁에 맞으세요."
    assert result["speech_priority"] == "high"
    assert result["interrupted_remainder"] is None, \
        "이겼으면 소비 — 안 지우면 다음 턴에 같은 말을 또 한다"


def test_a_losing_remainder_stays_for_the_next_tick(frozen_clock):
    """critical 생존 프로브에 밀린 나머지는 버려지지 않고 다음 틱을 기다린다."""
    frozen_clock(start=DAYTIME_EPOCH)
    state = proactive_state(
        interrupted_remainder=remainder_proposal(priority="medium"),
        proposals=[{"intent": "companion", "priority": "critical",
                    "seed": "어르신, 괜찮으세요?", "origin": "silence_ladder"}],
    )

    result = gate.proactive_gate(state)

    assert result["speech_priority"] == "critical"
    assert "interrupted_remainder" not in result, \
        "밀린 나머지를 지우면 barge-in 복구가 조용히 사라진다"


def test_an_expired_remainder_is_discarded_not_retried(frozen_clock):
    """만료된 나머지는 폐기다. 남기면 매 능동 턴마다 다시 평가되고 영원히 안 사라진다."""
    frozen_clock(start=DAYTIME_EPOCH)
    state = proactive_state(
        interrupted_remainder=remainder_proposal(expires_at=DAYTIME_EPOCH - 1.0))

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "silent"
    assert result["interrupted_remainder"] is None
