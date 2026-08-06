"""에코 억제와 barge-in 양보 검증.

이 파일이 검증하는 완료 조건
    1. TTS 재생 중 로봇이 자기 말에 멈추지 않는다  -> 에코 가드
    2. "응/그래" 발화 시 로봇이 문장을 끝까지 말한다  -> 맞장구 판별
    3. 진짜 끼어들기 시 재생이 중단되고 잔여분이 큐로 돌아간다  -> 취소 + 재큐

여기서 검증하지 '못하는' 것  ★ 실기 필요
    실제 스피커 소리가 실제 마이크로 되돌아오는 현상 자체. 그건 하드웨어가 있어야
    측정된다. 여기서 고정하는 것은 "에코라고 판정했을 때 올바르게 행동하는가"이고,
    "무엇을 에코로 판정할 것인가"의 임계치는 실기에서 정한다.

    확인 항목: docs/hardware/audio-echo-bargein-verification.md

참고
    CLAUDE.md §13 (barge-in), §22 3단계
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.audio import EchoAwareVad, EchoGuard, SentencePlayer
from bomi_ai_chat.graph import ingress, output

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def clean_speech_registries():
    output.TTS_HANDLES.clear()
    output.SPEECH_CONTEXT.clear()
    yield
    output.TTS_HANDLES.clear()
    output.SPEECH_CONTEXT.clear()
    output.set_player(None)


class RecordingSink:
    """합성과 재생을 대신 기록한다. 하드웨어 대역."""

    def __init__(self, block: "list | None" = None):
        self.synthesized: list[str] = []
        self.played: list[bytes] = []
        # 재생을 붙잡아 둘 수 있게 한다. 취소 시점을 제어하려면 필요하다.
        self._gate = block

    def synthesize(self, text: str) -> bytes:
        self.synthesized.append(text)
        return text.encode("utf-8")

    def play(self, audio: bytes) -> None:
        if self._gate is not None:
            self._gate.pop(0).wait(2)
        self.played.append(audio)


# ── 완료 조건 1: 재생 중 자기 목소리에 멈추지 않는다 ────────────────────────


def test_input_right_after_playback_start_is_ignored(frozen_clock):
    """재생 직후 가드 구간의 입력은 버린다.

    스피커가 소리를 내기 시작하는 구간이고, 이때 들어오는 것은 거의 확실히
    우리 목소리다.
    """
    sim = frozen_clock(start=1_000.0)
    guard = EchoGuard()
    guard.mark_playback_started()

    assert guard.should_ignore_input() is True

    sim.advance(policy.ECHO_GUARD_SEC + 0.01)
    assert guard.should_ignore_input() is False


def test_threshold_is_raised_while_playing_but_not_infinite(frozen_clock):
    """재생 중에는 임계치를 올린다. 막지는 않는다.

    막으면 barge-in 이 원리적으로 불가능해지고 양보 우선 정책이 죽는다.
    """
    frozen_clock(start=1_000.0)
    guard = EchoGuard()
    base = 0.3

    assert guard.vad_threshold(base) == pytest.approx(base)

    guard.mark_playback_started()
    raised = guard.vad_threshold(base)

    assert raised > base
    assert raised < 1_000_000, "완전 차단이 아니어야 한다"


def test_quiet_echo_rejected_but_loud_speech_accepted_while_playing(frozen_clock):
    """(완료 조건 1) 되돌아온 자기 목소리는 무시하고, 진짜 발화는 받는다."""
    sim = frozen_clock(start=1_000.0)
    guard = EchoGuard()
    base = 0.3
    guard.mark_playback_started()
    sim.advance(policy.ECHO_GUARD_SEC + 0.01)  # 가드 구간은 지났다

    # 스피커에서 되돌아온 정도의 약한 신호 — 평소라면 발화로 볼 수준이다.
    assert guard.accepts(0.35, base) is False
    # 어르신이 로봇 소리를 뚫고 말하는 정도의 강한 신호.
    assert guard.accepts(0.95, base) is True


def test_after_playback_stops_normal_threshold_returns(frozen_clock):
    """재생이 끝나면 평소 감도로 돌아간다. 안 그러면 조용한 말을 못 듣는다."""
    frozen_clock(start=1_000.0)
    guard = EchoGuard()
    guard.mark_playback_started()
    guard.mark_playback_stopped()

    assert guard.accepts(0.35, 0.3) is True


def test_echo_aware_vad_does_not_even_call_the_model_during_guard(frozen_clock):
    """가드 구간에서는 모델을 부르지 않는다. 프레임마다 도는 경로라 값싸야 한다."""
    frozen_clock(start=1_000.0)
    guard = EchoGuard()
    calls = []

    class CountingDetector:
        def speech_probability(self, frame: bytes) -> float:
            calls.append(frame)
            return 1.0

    vad = EchoAwareVad(CountingDetector(), guard, base_threshold=0.3)
    guard.mark_playback_started()

    assert vad.is_speech(b"frame") is False
    assert calls == []


# ── 완료 조건 2: 맞장구에는 계속 말한다 ─────────────────────────────────────


@pytest.mark.parametrize("text", ["응", "어", "그래", "네"])
def test_backchannel_while_speaking_does_not_stop_playback(text, frozen_clock):
    """(완료 조건 2) "응/그래"에는 문장을 끝까지 말한다.

    노인 대화에는 맞장구가 대단히 많다. 이걸 끼어들기로 처리하면 로봇은 문장 하나를
    끝내지 못한다.
    """
    frozen_clock(start=1_000.0)
    sink = RecordingSink()
    output.set_player(SentencePlayer(sink.synthesize, sink.play))
    output.emit({"senior_id": SENIOR, "sentences": ["첫 문장", "둘째 문장"]})

    result = ingress.note_interaction({
        "senior_id": SENIOR,
        "speaking": True,
        "user_input": text,
        "user_input_duration_sec": 0.4,
    })

    assert result["is_backchannel"] is True
    # 재생에 손대지 않았다. 핸들이 그대로 남아 있어야 한다.
    assert SENIOR in output.TTS_HANDLES


def test_backchannel_turn_ends_immediately():
    """맞장구 턴은 END 로 끝난다.

    "응"에 대답하려면 백엔드 호출 한 번, LLM 한 번, TTS 한 번이 들고
    아무도 듣고 싶지 않은 결과물이 나온다.
    """
    from langgraph.graph import END

    assert ingress.route_interaction({"is_backchannel": True}) == END
    assert ingress.route_interaction({"is_backchannel": False}) == "safety_triage"


def test_long_utterance_matching_backchannel_text_is_a_real_interruption(frozen_clock):
    """텍스트가 맞장구여도 길면 진짜 끼어들기다.

    길이와 텍스트 둘 다 요구하는 이유다. 여기서의 오탐은 '어르신이 실제로 한 말을
    로봇이 무시하는 것'이다.
    """
    frozen_clock(start=1_000.0)
    sink = RecordingSink()
    output.set_player(SentencePlayer(sink.synthesize, sink.play))
    output.emit({"senior_id": SENIOR, "sentences": ["첫 문장"]})

    result = ingress.note_interaction({
        "senior_id": SENIOR,
        "speaking": True,
        "user_input": "응",
        "user_input_duration_sec": policy.BACKCHANNEL_MAX_SEC + 0.5,
    })

    assert result["is_backchannel"] is False


def test_backchannel_when_robot_is_silent_is_a_normal_turn(frozen_clock):
    """로봇이 조용할 때의 "응"은 그냥 평범한 턴이다."""
    frozen_clock(start=1_000.0)

    result = ingress.note_interaction({
        "senior_id": SENIOR,
        "speaking": False,
        "user_input": "응",
        "user_input_duration_sec": 0.3,
    })

    assert result["is_backchannel"] is False


# ── 완료 조건 3: 진짜 끼어들기 → 중단 + 재큐 ───────────────────────────────


def test_playback_that_already_finished_is_not_an_interruption(frozen_clock):
    """재생이 다 끝난 뒤의 발화는 끼어들기가 아니라 평범한 다음 턴이다.

    (원래 이름은 real_interruption_cancels_playback_and_requeues_remainder 였는데,
    감사 결함 B1 수정으로 이 시나리오의 올바른 의미가 '끼어들기 아님'이 되면서
    이름도 바로잡았다. 진짜 끼어들기+재큐는 아래
    test_remainder_keeps_original_priority_and_is_marked_resumed 와
    tests/test_conversation_session.py 가 검증한다.)
    """
    frozen_clock(start=1_000.0)
    sink = RecordingSink()
    player = SentencePlayer(sink.synthesize, sink.play)
    output.set_player(player)
    output.emit({
        "senior_id": SENIOR,
        "sentences": ["약 두 알 드시고요", "인슐린도 맞으셔야 해요"],
        "intent": "schedule",
        "speech_priority": "medium",
        "speech_origin": "scheduler:med",
    })
    output.TTS_HANDLES[SENIOR].wait(2)  # 재생이 끝난 상태를 만든다

    # 재생이 이미 끝났으면 이것은 끼어들기가 아니라 평범한 다음 턴이다.
    # (감사 결함 B1 수정 — 예전에는 state 의 낡은 speaking=True 만 보고
    #  끼어들기로 처리했다. 지금은 핸들의 생사가 권위다.)
    result = ingress.note_interaction({
        "senior_id": SENIOR,
        "speaking": True,
        "user_input": "잠깐만",
        "user_input_duration_sec": 1.5,
    })

    assert result["speaking"] is False
    # 끼어들기가 아니므로 재큐할 나머지도 만들지 않는다.
    assert result.get("interrupted_remainder") is None
    # 끝난 핸들은 정리된다.
    assert SENIOR not in output.TTS_HANDLES


def test_remainder_keeps_original_priority_and_is_marked_resumed():
    """잘린 나머지는 '원래 우선순위'로 돌아간다.

    낮춰서 돌려보내면 복약 알림의 뒷부분이 잡담보다 뒤로 밀린다.
    """
    handle = _StubHandle(spoken=1, sentences=["약 두 알 드시고요", "인슐린도 맞으셔야 해요"])
    output.TTS_HANDLES[SENIOR] = handle
    output.SPEECH_CONTEXT[SENIOR] = {
        "sentences": handle.sentences,
        "intent": "schedule",
        "priority": "high",
        "origin": "scheduler:insulin",
    }

    remainder = ingress._yield_playback({"senior_id": SENIOR})

    assert handle.cancelled is True
    assert remainder is not None
    assert remainder["priority"] == "high"
    assert remainder["intent"] == "schedule"
    assert "인슐린" in remainder["seed"]
    assert "약 두 알" not in remainder["seed"], "이미 말한 문장은 다시 말하지 않는다"
    assert remainder["meta"]["resumed"] is True


def test_liveness_probe_remainder_is_discarded_not_resumed():
    """★ 생존 확인 프로브는 재개하지 않는다.

    끼어든 것 자체가 프로브가 물으려던 것을 이미 증명했다. 재개하면 방금 대답한
    사람에게 "괜찮으세요?"를 다시 묻는 로봇이 된다. barge-in 은 생존 증거다.
    """
    handle = _StubHandle(spoken=0, sentences=["어르신, 괜찮으세요?", "대답 좀 해주세요"])
    output.TTS_HANDLES[SENIOR] = handle
    output.SPEECH_CONTEXT[SENIOR] = {
        "sentences": handle.sentences,
        "intent": "companion",
        "priority": "critical",
        "origin": "silence_ladder:3",
    }

    remainder = ingress._yield_playback({"senior_id": SENIOR})

    assert handle.cancelled is True, "재생은 멈춰야 한다"
    assert remainder is None, "critical 프로브의 나머지는 버린다"


def test_interruption_resets_the_silence_ladder(frozen_clock):
    """끼어들기는 생존 증거다. 사다리가 처음으로 돌아간다."""
    frozen_clock(start=5_000.0)

    result = ingress.note_interaction({
        "senior_id": SENIOR,
        "speaking": False,
        "user_input": "나 여기 있어",
        "user_input_duration_sec": 1.2,
    })

    assert result["silence_level"] == 0
    assert result["last_user_interaction_at"] == pytest.approx(5_000.0)
    # 발화는 현관 센서를 이긴다. 목소리가 들리면 집에 있는 것이다.
    assert result["occupancy"] == "HOME"


def test_yield_without_a_playback_handle_is_safe():
    """재생기가 없는 환경에서도 turn 이 깨지지 않는다."""
    assert ingress._yield_playback({"senior_id": "nobody"}) is None


# ── 재생 핸들: 진행 상황의 권위 ────────────────────────────────────────────


def test_sentences_are_fed_one_by_one():
    """전체를 한 덩어리로 넘기면 어디서 끊겼는지 알 수 없다."""
    sink = RecordingSink()
    handle = SentencePlayer(sink.synthesize, sink.play).speak_async(["하나", "둘", "셋"])
    handle.wait(2)

    assert sink.synthesized == ["하나", "둘", "셋"]
    assert handle.spoken_count == 3
    assert handle.remaining_sentences() == []


def test_playback_marks_echo_guard_while_speaking(frozen_clock):
    """재생 시작·종료가 에코 가드에 반영된다."""
    frozen_clock(start=1_000.0)
    guard = EchoGuard()
    sink = RecordingSink()

    handle = SentencePlayer(sink.synthesize, sink.play, guard).speak_async(["한 문장"])
    handle.wait(2)

    assert guard.is_playing is False, "끝나면 가드가 풀려야 한다"


def test_failed_synthesis_does_not_count_as_spoken():
    """합성이 실패한 문장을 '말했다'고 세면 재큐에서 조용히 사라진다."""
    class BrokenSink(RecordingSink):
        def synthesize(self, text: str) -> bytes:
            if text == "둘":
                raise RuntimeError("tts down")
            return super().synthesize(text)

    sink = BrokenSink()
    handle = SentencePlayer(sink.synthesize, sink.play).speak_async(["하나", "둘", "셋"])
    handle.wait(2)

    assert handle.spoken_count == 1
    assert handle.remaining_sentences() == ["둘", "셋"]


class _StubHandle:
    """진행 상황을 직접 정해줄 수 있는 재생 핸들 대역.

    실제 SpeechPlayback 의 계약을 그대로 따라야 한다 — is_done 이 빠져 있으면
    note_interaction 의 '재생이 이미 끝났는가' 확인(감사 결함 B1 수정)에서
    AttributeError 가 난다. 대역이 실제 인터페이스에서 조용히 벗어나는 것이
    이 저장소의 최빈 실패 유형이다(PROGRESS.md §2.0).
    """

    # 이 대역은 '재생 중'을 흉내낸다. 끝난 재생을 흉내내려면 True 로 바꾼다.
    is_done = False

    def __init__(self, spoken: int, sentences: list[str]):
        self.sentences = sentences
        self._spoken = spoken
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def remaining_sentences(self) -> list[str]:
        return self.sentences[self._spoken :]
