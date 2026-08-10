"""런타임 배선 — S15P11E102-232 회귀.

이 파일이 검증하는 것
    1. 어르신 id 없이는 기동하지 않는다
    2. 재부팅 전 사다리 칸이 복원된다
    3. 배경 작업 하나가 죽어도 대화는 뜬다
    4. 입력 루프가 그래프를 부른다
    5. 종료 시 배경 스레드를 정리한다

가장 중요한 두 가지
    test_it_refuses_to_start_without_a_senior_id
        thread_id 가 곧 어르신 id 다. 임의의 기본값으로 기동하면 그 값으로 상태가
        쌓이고, 진짜 id 로 바꾸는 순간 사다리와 재실 기록이 통째로 사라진다.

    test_a_restart_does_not_reset_the_silence_ladder
        사다리가 2칸에서 재부팅으로 0 이 되면, 응답 없는 어르신에 대한 시계가
        처음부터 다시 흐른다.

참고
    CLAUDE.md §6(아키텍처), §22(개발 순서)
"""

import pytest

from bomi_ai_chat import bootstrap
from bomi_ai_chat.graph import build as graph_build
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import handlers, output
from bomi_ai_chat.localstore import db
from bomi_ai_chat.localstore import runtime as runtime_store

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    context_node.set_client(None)
    handlers.set_llm(None)
    output.set_player(None)
    graph_build.set_conversation_client(None)


def settings_with(settings_factory, **extra):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        SENIOR_ID=SENIOR,
        **extra,
    )


class FakeAudioOut:
    def __init__(self):
        self.played = []

    def play(self, audio_bytes):
        self.played.append(audio_bytes)


class ScriptedAudioIn:
    """정해진 발화를 순서대로 내보내고, 다 떨어지면 KeyboardInterrupt 로 루프를 끝낸다."""

    def __init__(self, *chunks):
        self.chunks = list(chunks)

    def capture(self, onset_timeout_seconds=None):
        # bootstrap.py 가 capture(onset_timeout_seconds=...) 로 호출한다(298).
        # 이 인자를 받지 않으면 매 호출이 TypeError 로 죽고, 그 예외를 삼키며
        # 도는 루프가 chunks 를 하나도 소비하지 못한 채 영원히 돈다(299 와 같은 유형).
        if not self.chunks:
            raise KeyboardInterrupt
        return self.chunks.pop(0)


# ── 1. 어르신 id ─────────────────────────────────────────────────────────────


def test_it_refuses_to_start_without_a_senior_id(settings_factory):
    """★ 임의의 기본값으로 기동하면 그 값으로 상태가 쌓인다.

    나중에 진짜 id 로 바꾸는 순간 그동안의 사다리와 재실 기록이 통째로 사라진다.
    조용히 시작하는 것보다 요란하게 실패하는 편이 낫다.
    """
    settings = settings_factory(
        RTZR_CLIENT_ID="id", RTZR_CLIENT_SECRET="s",
        GEMINI_API_KEY="g", TYPECAST_API_KEY="t")

    with pytest.raises(RuntimeError, match="SENIOR_ID"):
        bootstrap.build_runtime(settings, start_background=False)


# ── 2. 재부팅 복원 ───────────────────────────────────────────────────────────


def test_a_restart_does_not_reset_the_silence_ladder(settings_factory, frozen_clock):
    """★★ 사다리가 2칸에서 0 으로 돌아가면, 응답 없는 어르신에 대한 시계가
    처음부터 다시 흐르고 에스컬레이션이 그만큼 늦어진다."""
    frozen_clock(start=1_700_000_000.0)
    runtime_store.save(SENIOR, silence_level=2, occupancy="AWAY")

    runtime = bootstrap.build_runtime(
        settings_with(settings_factory), start_background=False)

    state = runtime.app.get_state(graph_build.thread(SENIOR)).values
    assert state["silence_level"] == 2
    assert state["occupancy"] == "AWAY"
    assert state["senior_id"] == SENIOR


def test_a_fresh_robot_starts_from_a_clean_slate(settings_factory, frozen_clock):
    """처음 켠 로봇은 UNKNOWN 에서 시작한다. HOME 으로 가정하면 빈 집에 사다리가 돈다."""
    frozen_clock(start=1_700_000_000.0)

    runtime = bootstrap.build_runtime(
        settings_with(settings_factory), start_background=False)

    state = runtime.app.get_state(graph_build.thread(SENIOR)).values
    assert state["silence_level"] == 0
    assert state["occupancy"] == "UNKNOWN"


# ── 3. 배경 작업이 죽어도 대화는 뜬다 ────────────────────────────────────────


def test_the_scheduler_failure_is_swallowed_inside(monkeypatch, settings_factory,
                                                   frozen_clock, caplog):
    frozen_clock(start=1_700_000_000.0)

    def explode(senior_id, app):
        raise RuntimeError("apscheduler missing")

    monkeypatch.setattr("bomi_ai_chat.jobs.scheduler.build_scheduler", explode)
    monkeypatch.setattr(bootstrap, "_start_door_subscriber", lambda *a, **k: None)

    with caplog.at_level("ERROR"):
        runtime = bootstrap.build_runtime(settings_with(settings_factory))

    assert runtime.app is not None
    assert runtime.scheduler is None
    assert "only respond when spoken to" in caplog.text


def test_a_missing_broker_does_not_stop_the_conversation(
    monkeypatch, settings_factory, frozen_clock):
    """브로커가 없으면 현관 신호가 없을 뿐이다. 대화는 돌아야 한다."""
    frozen_clock(start=1_700_000_000.0)
    monkeypatch.setattr(bootstrap, "_start_scheduler", lambda *a, **k: None)

    runtime = bootstrap.build_runtime(settings_with(settings_factory))

    assert runtime.app is not None
    assert runtime.door_subscriber is None


# ── 4. 입력 루프가 그래프를 부른다 ───────────────────────────────────────────


class RecordingStt:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else ""


def test_the_loop_puts_each_utterance_through_the_graph(monkeypatch, settings_factory,
                                                        frozen_clock):
    """★ 옛 파이프라인은 LLM 을 직접 불렀다. 여기는 그래프에 태운다 —
    그래서 트리아지가 생성보다 위에 있고 모든 출력이 정제기를 통과한다."""
    frozen_clock(start=1_700_000_000.0)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: RecordingStt("무릎이 아파", "고마워"))

    turns = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    count = bootstrap.run_conversation_loop(
        runtime, ScriptedAudioIn(b"a", b"b"), settings_with(settings_factory))

    assert count == 2
    assert turns == ["무릎이 아파", "고마워"]


def test_silence_does_not_produce_a_turn(monkeypatch, settings_factory, frozen_clock):
    """★ 아무 말도 안 한 사람에게 "네?"라고 하는 로봇은 성가시다."""
    frozen_clock(start=1_700_000_000.0)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: RecordingStt("", "   "))
    turns = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    count = bootstrap.run_conversation_loop(
        runtime, ScriptedAudioIn(b"a", b"b"), settings_with(settings_factory))

    assert count == 0
    assert turns == []


def test_a_capture_failure_does_not_kill_the_loop(monkeypatch, settings_factory,
                                                  frozen_clock):
    """★ 로봇이 멈추면 어르신은 고장 난 기계 앞에 남는다."""
    frozen_clock(start=1_700_000_000.0)
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: RecordingStt("안녕"))
    turns = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})

    class FlakyAudio:
        def __init__(self):
            self.calls = 0

        def capture(self, onset_timeout_seconds=None):
            self.calls += 1
            if self.calls == 1:
                raise OSError("device busy")
            if self.calls == 2:
                return b"audio"
            raise KeyboardInterrupt

    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    count = bootstrap.run_conversation_loop(
        runtime, FlakyAudio(), settings_with(settings_factory))

    assert count == 1
    assert turns == ["안녕"]


# ── 5. 종료 정리 ─────────────────────────────────────────────────────────────


def test_shutdown_stops_background_work():
    """★ 정리하지 않으면 재시작할 때마다 스케줄러 스레드가 쌓이고,
    침묵 틱이 두 번씩 돌아 프로브가 겹쳐 나간다."""
    stopped = []

    class Sub:
        def stop(self):
            stopped.append("door")

    class Sched:
        def shutdown(self):
            stopped.append("scheduler")

    runtime = bootstrap.Runtime(
        app=object(), senior_id=SENIOR, scheduler=Sched(), door_subscriber=Sub())
    runtime.shutdown()

    assert sorted(stopped) == ["door", "scheduler"]


def test_shutdown_survives_a_broken_closer():
    """종료 경로에서 예외를 올리면 나머지가 정리되지 않는다."""
    stopped = []

    class BrokenSub:
        def stop(self):
            raise RuntimeError("already gone")

    class Sched:
        def shutdown(self):
            stopped.append("scheduler")

    runtime = bootstrap.Runtime(
        app=object(), senior_id=SENIOR, scheduler=Sched(), door_subscriber=BrokenSub())
    runtime.shutdown()

    assert stopped == ["scheduler"]


# ── 8. 대화가 끝나면 추출 flush 를 당긴다 (S15P11E102-393) ───────────────────


class _FakeScheduler:
    def __init__(self):
        self.modified = []

    def modify_job(self, job_id, **kwargs):
        self.modified.append((job_id, kwargs))


def test_the_end_of_a_conversation_brings_the_extraction_flush_forward():
    """방금 말한 약속이 큐에 들어 있는 순간이 여기다 — 60초를 기다릴 이유가 없다."""
    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    runtime.scheduler = _FakeScheduler()

    bootstrap._flush_extraction_after_conversation(runtime)

    assert runtime.scheduler.modified[0][0] == "extraction_flush"


def test_the_end_of_a_conversation_is_safe_without_a_scheduler():
    """스케줄러 시작에 실패한 로봇에서도 대화 루프가 죽지 않는다.

    이 경로에서 잃는 것은 '조금 늦어진다'가 아니라 아예 없다 — 스케줄러가 없으면
    애초에 주기 틱도 없다. 그래도 여기서 예외가 나가면 대화 자체가 끊긴다.
    """
    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    runtime.scheduler = None

    bootstrap._flush_extraction_after_conversation(runtime)
