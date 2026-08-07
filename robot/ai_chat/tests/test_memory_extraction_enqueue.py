"""graph/build.py.memory_write 의 사실 추출 큐잉 배선 검증 (S15P11E102-255).

이 파일이 검증하는 완료 조건
    - "요즘 손자가 자주 놀러 와요" 류의 정상 반응형 턴은 큐에 1행을 남긴다.
    - 여섯 가지 스킵 조건(킬스위치 둘, 능동 턴, T1, 계약 주도형 대화, 짧은 발화,
      봉인된 대화) 과 메시지 id 가 없는 경우 모두 큐잉하지 않는다.
    - 큐잉 실패가 턴을 죽이지 않는다.

무엇을 검증하지 '않는가'
    LLM 호출과 백엔드 제출은 jobs/ticks.extraction_flush 의 몫이다
    (test_extraction_flush.py 참고). 여기서는 큐잉 여부만 본다. "턴당 생성
    호출 1회" 완료 조건은 test_turn_end_to_end.py 가 그래프 전체를 태워 확인한다.

참고
    CLAUDE.md §8, §12, §16 / graph/build.py._enqueue_extraction
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.config import clear_settings_cache
from bomi_ai_chat.graph import build
from bomi_ai_chat.localstore import db, emotion, extraction

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    build.set_conversation_client(None)


class FakeConversationClient:
    """SENIOR 행에는 message_id 를, ROBOT 행에는 항상 None 을 돌려준다."""

    def __init__(self, *, conversation_id="conv-1", message_id="msg-1"):
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.turns = []

    def record_turn(self, senior_id, **fields):
        self.turns.append(fields)
        if fields.get("role") == "SENIOR":
            return self.conversation_id, self.message_id
        return self.conversation_id, None


def base_state(**overrides) -> dict:
    state = {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": "요즘 손자가 자주 놀러 와요",
        "response": "그러셨어요? 좋으셨겠어요.",
        "final_utterance": "그러셨어요? 좋으셨겠어요.",
        "intent": "companion",
    }
    state.update(overrides)
    return state


def test_a_normal_reactive_turn_enqueues_one_job(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state())

    assert extraction.pending_count(SENIOR) == 1
    row = extraction.pending()[0]
    assert row["content"] == "요즘 손자가 자주 놀러 와요"
    assert row["conversation_id"] == "conv-1"
    assert row["source_message_id"] == "msg-1"


def test_preceding_robot_utterance_comes_from_recent_messages(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(ctx={
        "recentMessages": [
            {"role": "SENIOR", "content": "안녕"},
            {"role": "ROBOT", "content": "요즘 가족들은 잘 지내세요?"},
        ],
    }))

    row = extraction.pending()[0]
    assert row["preceding_robot_utterance"] == "요즘 가족들은 잘 지내세요?"


def test_no_preceding_message_yields_empty_string(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(ctx={}))

    row = extraction.pending()[0]
    assert row["preceding_robot_utterance"] == ""


# ── 스킵 조건 ────────────────────────────────────────────────────────────────


def test_the_policy_kill_switch_blocks_enqueueing(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())
    monkeypatch.setattr(policy, "EXTRACTION_ENABLED", False)

    build.memory_write(base_state())

    assert extraction.pending_count(SENIOR) == 0


def test_the_env_kill_switch_blocks_enqueueing(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())
    monkeypatch.setenv("EXTRACTION_ENABLED", "false")
    clear_settings_cache()

    try:
        build.memory_write(base_state())
        assert extraction.pending_count(SENIOR) == 0
    finally:
        clear_settings_cache()


def test_a_proactive_turn_does_not_enqueue(frozen_clock):
    """능동 턴에는 어르신이 실제로 한 말이 없다."""
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(trigger_type="proactive", user_input=""))

    assert extraction.pending_count(SENIOR) == 0


def test_a_t1_turn_does_not_enqueue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(safety_level="T1"))

    assert extraction.pending_count(SENIOR) == 0


@pytest.mark.parametrize("intent", ["onboarding", "clarification"])
def test_contract_driven_turns_do_not_enqueue(frozen_clock, intent):
    """온보딩·재질의는 이미 자신의 fact_candidate 경로를 갖고 있다 (CLAUDE.md §12)."""
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(intent=intent))

    assert extraction.pending_count(SENIOR) == 0


def test_a_short_utterance_does_not_enqueue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    build.memory_write(base_state(user_input="네"))

    assert extraction.pending_count(SENIOR) == 0


def test_a_sealed_conversation_does_not_enqueue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient(conversation_id="conv-sealed"))
    emotion.mark_sealed(SENIOR, "conv-sealed")

    build.memory_write(base_state(conversation_id="conv-sealed"))

    assert extraction.pending_count(SENIOR) == 0


def test_missing_source_message_id_does_not_enqueue(frozen_clock):
    """서버가 메시지 id 를 못 돌려주면(오프라인 등) 큐잉하지 않는다.

    안 그러면 이 행은 영원히 제출에 실패하는데, 이 큐에는 시도 횟수 컬럼이
    없어 outbox 처럼 GAVE_UP 으로 포기하지도 못한다 (graph/build.py 참고).
    """
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient(message_id=None))

    build.memory_write(base_state())

    assert extraction.pending_count(SENIOR) == 0


def test_enqueue_failure_does_not_break_the_turn(frozen_clock, monkeypatch):
    """추출 큐잉이 실패해도 memory_write 는 정상적으로 끝난다."""
    frozen_clock(start=1_700_000_000.0)
    build.set_conversation_client(FakeConversationClient())

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(extraction, "enqueue", boom)

    result = build.memory_write(base_state())

    assert result["last_spoke_at"] is not None
