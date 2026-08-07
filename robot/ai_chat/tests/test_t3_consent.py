"""T3 동의 지연 흐름 — S15P11E102-253 완료 조건.

이 파일이 검증하는 것
    1. 누적 문턱을 넘겨야만 동의 질문이 큐에 오른다(정서 신호 누적).
    2. "우리끼리 얘기" 가 섞인 대화는 봉인되고, 그 대화로는 절대 질문이 안 만들어진다.
    3. "응"/"아니" 답을 규칙으로 판정한다. LLM 을 부르지 않는다.
    4. "응" -> outbox 에 T3 정확히 한 건, 발화 원문 없음.
       "아니" -> outbox 에 아무것도 안 나가고, 다시 묻지 않는다.
    5. 자연스러운 창이 아니면(사다리 진행 중, 안전 확인 대기, AWAY) 올리지 않는다.
    6. 새 틱이 스케줄러 양쪽(add_job, run_all_ticks_once)에 등록돼 있다.
    7. 재시작을 넘어 누적 신호와 미뤄 둔 질문이 이어진다.
    8. 킬스위치(정책 상수 + 환경변수) 둘 중 하나만 꺼져도 질문이 올라가지 않는다.
    9. 상위 동의(guardianSharingConsentGranted)가 없으면 질문 자체를 안 만든다.

참고
    CLAUDE.md §8(확인은 규칙으로), §9(T1~T4), §16(생성 호출 예산)
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import handlers
from bomi_ai_chat.jobs import scheduler as scheduler_module
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import consent as consent_store
from bomi_ai_chat.localstore import context_cache, db, emotion, outbox
from bomi_ai_chat.localstore import proposals as proposal_store
from bomi_ai_chat.localstore import runtime as runtime_store

SENIOR = "senior-1"
CONVERSATION = "conv-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    handlers.set_llm(None)


@pytest.fixture(autouse=True)
def guardian_sharing_granted(isolated_localstore):
    """상위 동의가 있는 어르신을 기본값으로 둔다 (S15P11E102-253).

    왜 autouse 인가
        이 파일의 기존 테스트는 전부 "그 밖의 조건"(문턱, 봉인, 자연스러운 창,
        킬스위치)을 검증한다. 상위 동의 게이트가 새로 생기면서 그 테스트들이
        전부 "동의가 없어서 0"으로 통과해 버리면, 정작 검증하려던 조건이
        무력화된 것을 아무도 모른다 — 초록불이 공백을 가리는 상황이다.
        그래서 기본값을 '동의함'으로 두고, 동의 없는 경우는 아래 §9 에서
        명시적으로 덮어써서 따로 검증한다.
    """
    context_cache.save(SENIOR, {"profile": {"guardianSharingConsentGranted": True}})


class RecordingLLM:
    """호출 횟수를 남긴다. 이 파일의 테스트는 대부분 0회를 기대한다."""

    def __init__(self, reply="그러셨어요."):
        self.reply = reply
        self.calls = 0

    def generate(self, text, weather_data=None):
        self.calls += 1
        return self.reply


def emotional_state(text, **extra):
    return {
        "senior_id": SENIOR, "conversation_id": CONVERSATION, "ctx": {},
        "intent": "emotional", "user_input": text, **extra,
    }


def _queue_a_consent_question() -> None:
    """문턱을 넘겨 질문 하나를 큐에 넣는다. 다른 테스트 파일과 같은 헬퍼."""
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    ticks.consent_tick(SENIOR)


# ── 1. 누적 문턱 ─────────────────────────────────────────────────────────────


def test_signals_below_threshold_do_not_queue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD - 1):
        handlers.handle_emotional(emotional_state("외로워"))
    added = ticks.consent_tick(SENIOR)

    assert added == 0
    assert proposal_store.pending(SENIOR) == []


def test_pending_signal_count_tracks_emotional_turns(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    handlers.handle_emotional(emotional_state("외로워"))
    handlers.handle_emotional(emotional_state("보고 싶다"))

    assert emotion.pending_signal_count(SENIOR) == 2


def test_crossing_the_threshold_consumes_the_signals(frozen_clock):
    """★ 문턱을 넘겨 질문을 올리면, 그 신호들은 다시 세지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    _queue_a_consent_question()

    assert emotion.pending_signal_count(SENIOR) == 0


# ── 2. 봉인(T4) ──────────────────────────────────────────────────────────────


def test_a_seal_marker_seals_the_conversation(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    handlers.handle_emotional(emotional_state("우리끼리 얘기인데 요즘 너무 외로워"))

    assert emotion.is_conversation_sealed(SENIOR, CONVERSATION) is True


def test_a_sealed_turn_does_not_count_toward_the_threshold(frozen_clock):
    """★★ 봉인된 턴은 신호로도 남지 않는다 — 다른 대화의 문턱에 몰래 기여하면 안 된다."""
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD + 2):
        handlers.handle_emotional(emotional_state("우리끼리 얘기인데 외로워"))

    assert emotion.pending_signal_count(SENIOR) == 0
    assert ticks.consent_tick(SENIOR) == 0


def test_a_sealed_conversation_never_raises_a_consent_question(frozen_clock):
    """★★★ (완료 조건) 봉인된 대화로는 동의 요청이 만들어지지 않는다.

    신호는 다른(봉인되지 않은) 대화에서 이미 쌓여 있어도, 지금 열려 있는
    대화가 봉인돼 있으면 consent_tick 은 질문을 올리지 않는다.
    """
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워", conversation_id="conv-open"))
    # 같은 대화 안에서 뒤이어 "우리끼리 얘기"가 나와 지금 열린 대화가 봉인된다.
    handlers.handle_emotional(
        emotional_state("우리끼리 얘기인데 그냥 그렇다고", conversation_id="conv-open"))
    runtime_store.save(SENIOR, conversation_id="conv-open")

    added = ticks.consent_tick(SENIOR)

    assert added == 0
    assert proposal_store.pending(SENIOR) == []


# ── 3·4. 답 판정과 outbox ────────────────────────────────────────────────────


def _asked_state(request_id: int, answer_text: str) -> dict:
    return {
        "senior_id": SENIOR, "intent": "emotional", "ctx": {},
        "user_input": answer_text,
        "pending_consent": {"request_id": request_id, "asked_at": 1_700_000_000.0},
    }


def test_asking_the_question_speaks_the_seed_without_calling_the_llm(frozen_clock):
    """★★ (완료 조건) 동의 질문 턴은 생성 호출이 0회다."""
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    _queue_a_consent_question()
    proposal = proposal_store.pending(SENIOR)[0]

    # 누적 단계(정서 발화 세 번)는 각자 _generate 를 부른다. 지금 재는 것은
    # '질문을 던지는 이 턴 하나'의 호출 수이므로, 여기서 새로 갈아 끼운다.
    asking_llm = RecordingLLM()
    handlers.set_llm(asking_llm)

    result = handlers.handle_emotional({
        "senior_id": SENIOR, "intent": "emotional", "ctx": {},
        "user_input": proposal["seed"],
        "speech_origin": proposal["origin"],
    })

    assert result["response"] == proposal["seed"]
    assert result["pending_consent"]["request_id"] == proposal["meta"]["request_id"]
    assert asking_llm.calls == 0


def test_granted_answer_enqueues_exactly_one_t3_with_no_raw_text():
    request_id = consent_store.create_request(SENIOR, CONVERSATION)
    handlers.set_llm(RecordingLLM())

    result = handlers.handle_emotional(_asked_state(request_id, "응, 전해줘"))

    assert result["pending_consent"] is None
    assert outbox.pending_count() == 1
    assert consent_store.get(request_id)["status"] == "GRANTED"
    assert handlers._llm().calls == 0  # noqa: SLF001


def test_declined_answer_sends_nothing_and_does_not_reask():
    request_id = consent_store.create_request(SENIOR, CONVERSATION)
    handlers.set_llm(RecordingLLM())

    result = handlers.handle_emotional(_asked_state(request_id, "아니, 됐어"))

    assert result["pending_consent"] is None
    assert outbox.pending_count() == 0
    assert consent_store.get(request_id)["status"] == "DECLINED"


def test_an_ambiguous_answer_keeps_the_question_pending():
    """★ "글쎄"를 거절로 접으면 안 된다 — contract_dialogue 와 같은 원칙."""
    request_id = consent_store.create_request(SENIOR, CONVERSATION)
    handlers.set_llm(RecordingLLM())

    result = handlers.handle_emotional(_asked_state(request_id, "글쎄"))

    assert result["pending_consent"] == {"request_id": request_id, "asked_at": 1_700_000_000.0}
    assert outbox.pending_count() == 0
    assert consent_store.get(request_id)["status"] == "PENDING"


def test_the_outbox_payload_never_contains_the_utterance():
    """보호자 alert 에 발화 원문이 실리면 T4 약속이 T3 알림에서 깨진다."""
    request_id = consent_store.create_request(SENIOR, CONVERSATION)
    handlers.set_llm(RecordingLLM())

    handlers.handle_emotional(_asked_state(request_id, "응"))

    import json

    connection = db.outbox_db()
    row = connection.execute("SELECT payload FROM outbox").fetchone()
    payload = json.loads(row["payload"])
    assert "응" not in json.dumps(payload, ensure_ascii=False)
    assert "user_input" not in payload


# ── classify_intent 라우팅 ───────────────────────────────────────────────────


def test_classify_intent_routes_the_answer_turn_to_emotional_even_if_intent_leaked():
    """pending_consent 는 checkpoint 에 남은 다른 intent 보다 먼저 확인된다."""
    state = {
        "user_input": "응", "pending_consent": {"request_id": 1, "asked_at": 0.0},
        # 사이에 다른 능동 발화가 끼어 intent 가 "schedule" 로 남아 있다고 가정한다.
        "intent": "schedule",
    }

    assert context_node.classify_intent(state) == {"intent": "emotional"}


def test_classify_intent_defers_when_the_senior_asks_something_instead():
    """동의 질문에 답하는 대신 새 질문을 하면, 그 질문에 먼저 답해야 한다."""
    state = {"user_input": "오늘 며칠이야?", "pending_consent": {"request_id": 1}}

    result = context_node.classify_intent(state)

    assert result.get("intent") != "emotional" or "intent" not in result


# ── 5. 자연스러운 창 ─────────────────────────────────────────────────────────


def test_the_tick_does_not_ask_while_the_silence_ladder_is_running(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    runtime_store.save(SENIOR, silence_level=1)

    assert ticks.consent_tick(SENIOR) == 0


def test_the_tick_does_not_ask_during_a_pending_safety_check(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    runtime_store.save(SENIOR, safety_check_until=1_700_010_000.0)

    assert ticks.consent_tick(SENIOR) == 0


def test_the_tick_does_not_ask_while_away(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    runtime_store.save(SENIOR, occupancy="AWAY")

    assert ticks.consent_tick(SENIOR) == 0


# ── 6. 스케줄러 등록 ─────────────────────────────────────────────────────────


def test_consent_tick_is_registered_in_the_scheduler():
    pytest.importorskip("apscheduler")
    # build_scheduler 는 등록만 하고 시작하지 않는다(jobs/scheduler.py 참고) —
    # 그래서 시작하지 않은 스케줄러는 shutdown 도 필요 없다.
    scheduler = scheduler_module.build_scheduler(SENIOR)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "consent_tick" in job_ids


def test_consent_tick_runs_inside_run_all_ticks_once(monkeypatch, frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    calls = []
    monkeypatch.setattr(ticks, "consent_tick", lambda senior_id: calls.append(senior_id))

    scheduler_module.run_all_ticks_once(SENIOR)

    assert calls == [SENIOR]


# ── 7. 재시작을 넘어 이어진다 ────────────────────────────────────────────────


def test_signals_and_a_pending_request_survive_a_restart(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    handlers.handle_emotional(emotional_state("외로워"))
    request_id = consent_store.create_request(SENIOR, CONVERSATION)

    db.close_all()  # 재부팅을 흉내낸다 (test_localstore.py 와 같은 방법).

    assert emotion.pending_signal_count(SENIOR) == 1
    assert consent_store.get(request_id)["status"] == "PENDING"


# ── 8. 킬스위치 ──────────────────────────────────────────────────────────────


def test_the_policy_kill_switch_blocks_the_tick(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    monkeypatch.setattr(policy, "T3_CONSENT_ENABLED", False)

    assert ticks.consent_tick(SENIOR) == 0
    assert proposal_store.pending(SENIOR) == []


def test_the_env_kill_switch_blocks_the_tick(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    monkeypatch.setenv("T3_CONSENT_ENABLED", "false")
    from bomi_ai_chat.config import clear_settings_cache

    clear_settings_cache()
    try:
        assert ticks.consent_tick(SENIOR) == 0
        assert proposal_store.pending(SENIOR) == []
    finally:
        clear_settings_cache()


# ── 9. 상위 동의 (S15P11E102-253 완료 조건의 마지막 항목) ──────────────────────


def _cross_the_threshold() -> None:
    """다른 조건은 전부 통과시킨 채 상위 동의만 남긴다."""
    handlers.set_llm(RecordingLLM())
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))


def test_no_question_when_guardian_sharing_consent_is_denied(frozen_clock):
    """DENIED 인 어르신에게는 질문 자체가 만들어지지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    context_cache.save(SENIOR, {"profile": {"guardianSharingConsentGranted": False}})
    _cross_the_threshold()

    assert ticks.consent_tick(SENIOR) == 0
    assert proposal_store.pending(SENIOR) == []


def test_no_question_when_the_profile_never_carried_the_field(frozen_clock):
    """필드가 아예 없는 구버전 응답도 '동의 아님'으로 본다 — 모르면 묻지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    context_cache.save(SENIOR, {"profile": {"name": "김순자"}})
    _cross_the_threshold()

    assert ticks.consent_tick(SENIOR) == 0
    assert proposal_store.pending(SENIOR) == []


def test_no_question_when_there_is_no_cached_context_at_all(frozen_clock):
    """한 번도 문맥을 못 받은 상태(캐시 없음)에서도 묻지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    db.close_all()  # autouse 픽스처가 심어 둔 캐시를 비운다

    import shutil

    from bomi_ai_chat.config import get_settings

    shutil.rmtree(get_settings().localstore_dir, ignore_errors=True)
    _cross_the_threshold()

    assert ticks.consent_tick(SENIOR) == 0
    assert proposal_store.pending(SENIOR) == []


def test_the_question_is_queued_once_consent_is_granted(frozen_clock):
    """상위 동의가 있으면(그리고 나머지 조건도 통과하면) 정확히 한 건 올라간다."""
    frozen_clock(start=1_700_000_000.0)
    _cross_the_threshold()

    assert ticks.consent_tick(SENIOR) == 1
    assert len(proposal_store.pending(SENIOR)) == 1
