# robot/ai_chat/tests/test_wake_movement_wait.py
"""이동 중 침묵(CLAUDE.md §3a) 이 웨이크 흐름에 실제로 배선됐는지 확인한다.

이 파일이 검증하는 것
    1. navigation_watcher 가 있으면 WAKE_ACK_MOVING_MESSAGE 를 말하고,
       도착(ARRIVED)을 기다린 뒤에야 리슨을 연다.
    2. 도착을 못 받아도(타임아웃) 그 자리에서 대화를 연다 — 침묵 고착 방지.
    3. navigation_watcher 가 없으면(기능 꺼짐) 기존 WAKE_ACK_MESSAGE 그대로다
       — _speak_ack 시그니처를 바꾼 뒤에도 정상 웨이크 흐름이 그대로임을
       실제로 발화 문구까지 확인한다(이전에는 tts=None 이라 이 경로 자체가
       테스트된 적이 없었다).

참고
    CLAUDE.md §3a, bootstrap.py 의 "백엔드가 시작하는 대화" 절 인접 로직
"""

from bomi_ai_chat import bootstrap

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


class RecordingTts:
    def __init__(self):
        self.spoken: list[str] = []

    def synthesize(self, text):
        self.spoken.append(text)
        return b"audio-bytes"


class RecordingAudioOut:
    def __init__(self):
        self.played: list[bytes] = []

    def play(self, audio):
        self.played.append(audio)


class OneWake:
    def __init__(self, wakes=1):
        self.wakes_left = wakes
        self.interrupt_check = None

    def wait_for_wake(self):
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


class FakeArrivalWatcher:
    """navigation_watch.NavigationArrivalWatcher 대역."""

    def __init__(self, *, arrives: bool):
        self._arrives = arrives
        self.reset_calls = 0
        self.wait_calls: list[float] = []

    def reset(self):
        self.reset_calls += 1

    def wait_for_arrival(self, timeout_sec: float) -> bool:
        self.wait_calls.append(timeout_sec)
        return self._arrives


def _run(monkeypatch, settings_factory, *, navigation_watcher, wakes=1,
         chunks=(b"1",), stt_texts=("고마워요",)):
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: ScriptedStt(*stt_texts))
    monkeypatch.setattr("bomi_ai_chat.tts.client.TTSClient",
                        lambda settings: tts)
    turns: list[str] = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    tts = RecordingTts()
    audio_out = RecordingAudioOut()
    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR,
                                navigation_watcher=navigation_watcher)
    wake = OneWake(wakes=wakes)

    bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(*chunks), settings_with(settings_factory),
        wake=wake, audio_out=audio_out, max_turns=len(chunks),
    )
    return tts, audio_out, turns


def test_movement_wait_speaks_the_moving_ack_and_waits_for_arrival(
    monkeypatch, settings_factory, frozen_clock,
):
    frozen_clock(start=NOW)
    watcher = FakeArrivalWatcher(arrives=True)

    tts, audio_out, turns = _run(
        monkeypatch, settings_factory, navigation_watcher=watcher,
    )

    assert tts.spoken == ["네, 지금 갈게요."]
    assert len(audio_out.played) == 1
    assert watcher.reset_calls == 1, "새 대화 전에 지난 신호를 지워야 한다"
    assert watcher.wait_calls == [45.0], (
        "policy.WAKE_MOVEMENT_WAIT_TIMEOUT_SEC 를 그대로 써야 한다")
    assert turns == ["고마워요"], "도착 뒤에는 정상적으로 리슨이 이어진다"


def test_movement_wait_times_out_and_starts_anyway(
    monkeypatch, settings_factory, frozen_clock, caplog,
):
    """★ ARRIVED 를 못 받아도 침묵으로 고착되지 않는다."""
    frozen_clock(start=NOW)
    watcher = FakeArrivalWatcher(arrives=False)

    with caplog.at_level("WARNING"):
        tts, audio_out, turns = _run(
            monkeypatch, settings_factory, navigation_watcher=watcher,
        )

    assert tts.spoken == ["네, 지금 갈게요."]
    assert "ARRIVED not observed" in caplog.text
    assert turns == ["고마워요"], "타임아웃이어도 대화는 정상 진행된다"


def test_without_a_watcher_the_normal_ack_is_used(
    monkeypatch, settings_factory, frozen_clock,
):
    """★ 회귀: 기능이 꺼져 있으면(navigation_watcher=None) 문구가 안 바뀐다."""
    frozen_clock(start=NOW)

    tts, audio_out, turns = _run(
        monkeypatch, settings_factory, navigation_watcher=None,
    )

    assert tts.spoken == ["네, 말씀하세요."]
    assert turns == ["고마워요"]
