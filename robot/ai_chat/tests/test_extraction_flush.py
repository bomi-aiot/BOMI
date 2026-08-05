"""추출 큐 flush(jobs/ticks.extraction_flush) 검증 (S15P11E102-255).

이 파일이 검증하는 것
    1. 대기 행마다 LLM 을 한 번 불러 사실을 뽑고, 있으면 fact_client 로 제출한다.
    2. 제출까지 성공한(또는 애초에 뽑을 것이 없던) 행만 큐에서 사라진다.
    3. LLM 실패/제출 실패는 그 행을 큐에 남겨 다음 flush 가 재시도하게 한다.
    4. 한 번의 flush 는 policy.EXTRACTION_FLUSH_BATCH_SIZE 건까지만 처리한다.
    5. 모델 출력이 상한(policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE)을 넘겨도
       파이썬 쪽에서 다시 자른다.
    6. 킬스위치(정책 상수 + 환경변수) 둘 중 하나만 꺼져도 아무것도 하지 않는다.
    7. 스케줄러 양쪽(add_job, run_all_ticks_once)에 틱이 등록돼 있다.

참고
    CLAUDE.md §8, §16 / jobs/ticks.extraction_flush, backend_client/fact_client.py
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client.fact_client import FactSubmissionError
from bomi_ai_chat.jobs import scheduler as scheduler_module
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import db, extraction

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class ScriptedLLM:
    """호출할 때마다 미리 정해둔 응답을 순서대로 돌려준다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, weather_data=None):
        self.prompts.append(prompt)
        if not self.replies:
            return "[]"
        return self.replies.pop(0)


class RecordingFactClient:
    """제출된 사실을 순서대로 모은다. 지정한 senior_id 에서는 실패한다."""

    def __init__(self, *, fail_for: set[str] | None = None):
        self.submissions = []
        self.fail_for = fail_for or set()

    def submit_fact_candidates(self, senior_id, *, conversation_id, source_message_id, facts):
        if senior_id in self.fail_for:
            raise FactSubmissionError("backend rejected the batch")
        self.submissions.append({
            "senior_id": senior_id,
            "conversation_id": conversation_id,
            "source_message_id": source_message_id,
            "facts": facts,
        })


def _enqueue(content="요즘 손자가 자주 놀러 와요", **overrides):
    fields = {
        "conversation_id": "conv-1",
        "source_message_id": "msg-1",
        "content": content,
    }
    fields.update(overrides)
    return extraction.enqueue(SENIOR, **fields)


# ── 1·2. 정상 경로 ───────────────────────────────────────────────────────────


def test_a_job_with_facts_is_submitted_and_removed_from_the_queue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}]'])
    fact_client = RecordingFactClient()

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 1, "submitted": 1, "failed": 0}
    assert extraction.pending_count(SENIOR) == 0
    assert fact_client.submissions[0]["facts"] == [
        {"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}
    ]
    assert fact_client.submissions[0]["source_message_id"] == "msg-1"


def test_a_job_with_no_facts_is_still_marked_processed(frozen_clock):
    """뽑을 것이 없어도(빈 배열) 그 행은 처리 완료로 표시된다 — 영원히 재시도하지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue(content="네 알겠습니다 그렇게 할게요")
    llm = ScriptedLLM(["[]"])
    fact_client = RecordingFactClient()

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 1, "submitted": 0, "failed": 0}
    assert extraction.pending_count(SENIOR) == 0
    assert fact_client.submissions == []


def test_prompt_carries_the_preceding_robot_utterance(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue(preceding_robot_utterance="요즘 가족들은 잘 지내세요?")
    llm = ScriptedLLM(["[]"])

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert "요즘 가족들은 잘 지내세요?" in llm.prompts[0]
    assert "요즘 손자가 자주 놀러 와요" in llm.prompts[0]


# ── 3. 실패는 재시도로 남는다 ────────────────────────────────────────────────


def test_an_llm_failure_leaves_the_job_pending(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()

    class BrokenLLM:
        def generate(self, prompt, weather_data=None):
            raise RuntimeError("gemini down")

    result = ticks.extraction_flush(SENIOR, llm=BrokenLLM(), fact_client=RecordingFactClient())

    assert result == {"processed": 0, "submitted": 0, "failed": 1}
    assert extraction.pending_count(SENIOR) == 1


def test_a_submission_failure_leaves_the_job_pending(frozen_clock):
    """fact_client 가 실패하면 그 행은 extracted=1 로 표시되지 '않는다'.

    표시해버리면 그 사실은 다시는 제출 시도되지 않는다
    (backend_client/fact_client.py 모듈 docstring 참고).
    """
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}]'])
    fact_client = RecordingFactClient(fail_for={SENIOR})

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 0, "submitted": 0, "failed": 1}
    assert extraction.pending_count(SENIOR) == 1


def test_an_unparseable_reply_is_treated_as_nothing_found(frozen_clock):
    """모델이 JSON 이 아닌 걸 돌려주면 뽑은 게 없다고 취급하고 넘어간다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(["죄송해요, 잘 모르겠어요."])

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert result == {"processed": 1, "submitted": 0, "failed": 0}
    assert extraction.pending_count(SENIOR) == 0


# ── 4·5. 상한 ────────────────────────────────────────────────────────────────


def test_a_flush_processes_at_most_the_batch_size(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    for _ in range(policy.EXTRACTION_FLUSH_BATCH_SIZE + 3):
        _enqueue()
    llm = ScriptedLLM(["[]"] * (policy.EXTRACTION_FLUSH_BATCH_SIZE + 3))

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert result["processed"] == policy.EXTRACTION_FLUSH_BATCH_SIZE
    assert extraction.pending_count(SENIOR) == 3


def test_facts_beyond_the_per_utterance_cap_are_trimmed(frozen_clock):
    """모델이 상한을 어겨도 파이썬 쪽에서 한 번 더 자른다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    over_the_cap = ", ".join(
        f'{{"factType": "OTHER", "content": "사실{i}"}}' for i in range(5)
    )
    llm = ScriptedLLM([f"[{over_the_cap}]"])
    fact_client = RecordingFactClient()

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert len(fact_client.submissions[0]["facts"]) == policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE


# ── 6. 킬스위치 ──────────────────────────────────────────────────────────────


def test_the_policy_kill_switch_blocks_the_flush(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    monkeypatch.setattr(policy, "EXTRACTION_ENABLED", False)

    result = ticks.extraction_flush(
        SENIOR, llm=ScriptedLLM(["[]"]), fact_client=RecordingFactClient())

    assert result == {"processed": 0, "submitted": 0, "failed": 0}
    assert extraction.pending_count(SENIOR) == 1


def test_the_env_kill_switch_blocks_the_flush(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    monkeypatch.setenv("EXTRACTION_ENABLED", "false")
    from bomi_ai_chat.config import clear_settings_cache

    clear_settings_cache()
    try:
        result = ticks.extraction_flush(
            SENIOR, llm=ScriptedLLM(["[]"]), fact_client=RecordingFactClient())
        assert result == {"processed": 0, "submitted": 0, "failed": 0}
        assert extraction.pending_count(SENIOR) == 1
    finally:
        clear_settings_cache()


# ── 7. 스케줄러 등록 ─────────────────────────────────────────────────────────


def test_extraction_flush_is_registered_in_the_scheduler():
    pytest.importorskip("apscheduler")
    scheduler = scheduler_module.build_scheduler(SENIOR)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "extraction_flush" in job_ids


def test_extraction_flush_runs_inside_run_all_ticks_once(monkeypatch, frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    calls = []
    monkeypatch.setattr(ticks, "extraction_flush", lambda senior_id: calls.append(senior_id))

    scheduler_module.run_all_ticks_once(SENIOR)

    assert calls == [SENIOR]
