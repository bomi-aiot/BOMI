"""정서 핸들러 — S15P11E102-263 완료 조건.

이 파일이 검증하는 것
    1. "외로워" 에 응답이 나온다 (그전에는 무응답이었다)
    2. 정서와 정보가 섞인 발화도 응답이 나온다
    3. 자해 표지는 이 핸들러에 도달하지 않는다 — 트리아지가 먼저 잡는다
    4. T3 동의 질문이 '같은 턴에' 나가지 않는다. 큐에만 들어간다
    5. 지연이 실제로 지켜진다 — 게이트가 not_before 를 본다
    6. 태도 지시가 프롬프트에 실리고, 정서 턴에만 실린다

가장 중요한 두 가지
    test_a_lonely_utterance_gets_an_answer
        이 제품에서 가장 나쁜 모양의 실패였다. 외로움이 1번 문제인데(CLAUDE.md §1)
        하필 외로움 표현에만 침묵했다. 정보 질문에는 답하고 잡담에도 답하면서.

    test_the_consent_question_is_not_asked_in_the_same_turn
        속마음을 꺼내는 순간 "아드님께 전해드릴까요?"로 끊으면, 로봇은 그 한 문장으로
        말벗에서 감시 장치가 된다. 그 뒤로 어르신은 털어놓지 않고, 그러면 T3 로 보낼
        내용 자체가 사라진다 (CLAUDE.md §9).

참고
    CLAUDE.md §1(세 기둥), §9(티어), §14(발화 규칙), §16(프롬프트 조립)
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import gate, handlers, output, triage
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import context_cache, db
from bomi_ai_chat.localstore import proposals as proposal_store
from bomi_ai_chat.prompts import build_prompt

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    handlers.set_llm(None)
    output.set_player(None)


@pytest.fixture(autouse=True)
def guardian_sharing_granted(isolated_localstore):
    """상위 동의가 있는 어르신을 기본값으로 둔다 (S15P11E102-253).

    consent_tick 이 상위 동의를 확인하게 되면서, 이 파일의 동의 질문 관련
    테스트들도 그 전제를 명시해야 한다. 없으면 "동의가 없어서 0건"으로 통과해
    정작 검증하려던 문턱·게이트 동작이 무력화된다.
    """
    context_cache.save(SENIOR, {"profile": {"guardianSharingConsentGranted": True}})


class RecordingLLM:
    """호출 횟수와 마지막 프롬프트를 남긴다. 네트워크를 쓰지 않는다."""

    def __init__(self, reply="그러셨어요. 어떤 일이 있으셨는지 말씀해 주시겠어요?"):
        self.reply = reply
        self.calls = 0
        self.last_prompt = ""

    def generate(self, text, weather_data=None):
        self.calls += 1
        self.last_prompt = text
        return self.reply


def emotional_state(text, **extra):
    return {"senior_id": SENIOR, "ctx": {}, "intent": "emotional", "user_input": text, **extra}


# ── 1. 응답이 나온다 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("utterance", ["외로워", "보고 싶다", "혼자 있으니 적적해", "요즘 우울해"])
def test_a_lonely_utterance_gets_an_answer(utterance):
    """★★ 그전에는 NotImplementedError 로 무응답이었다.

    run_user_turn 이 예외를 삼켜서 로봇이 멈추지는 않았지만, 어르신은 "외로워"라고
    말하고 침묵을 받았다. 정보 질문에는 답하는 로봇이 정서 표현에만 조용했다.
    """
    llm = RecordingLLM()
    handlers.set_llm(llm)

    result = handlers.handle_emotional(emotional_state(utterance))

    assert result["response"]
    assert llm.calls == 1


def test_generation_stays_at_one_call_per_turn():
    """T3 동의 큐잉이 생성 호출을 늘리지 않는다.

    큐잉은 로컬 SQLite 쓰기 한 번이다. LLM 을 부르면 턴 예산이 무너진다 (§16).
    """
    llm = RecordingLLM()
    handlers.set_llm(llm)

    handlers.handle_emotional(emotional_state("외로워"))

    assert llm.calls == 1


def test_a_generation_failure_still_answers():
    """생성이 실패해도 침묵하지 않는다. 정서 턴에서 특히 그렇다."""

    class BrokenLLM:
        def generate(self, text, weather_data=None):
            raise RuntimeError("gemini down")

    handlers.set_llm(BrokenLLM())

    result = handlers.handle_emotional(emotional_state("외로워"))

    assert result["response"]


def test_a_generation_failure_uses_the_emotional_fallback_not_the_generic_one():
    """★ (253 완료 조건) 마음을 꺼낸 사람에게 "다시 말씀해 주시겠어요?"는 최악이다.

    핸들러가 공통 폴백을 그대로 쓰면 정서 턴도 서비스 오류처럼 들린다.
    """
    class BrokenLLM:
        def generate(self, text, weather_data=None):
            raise RuntimeError("gemini down")

    handlers.set_llm(BrokenLLM())

    result = handlers.handle_emotional(emotional_state("외로워"))

    assert result["response"] == handlers._EMOTIONAL_FALLBACK  # noqa: SLF001


def test_a_missing_prompt_template_still_answers_on_the_emotional_path(monkeypatch):
    """★★ (253 잔여 결함) build_prompt 호출이 try 밖에 있으면 이 테스트가 죽는다.

    263 코드는 build_prompt() 호출이 생성 호출을 감싸는 try 바깥에 있었다.
    템플릿 파일이 없으면 FileNotFoundError 가 핸들러를 그대로 뚫고 나가서,
    예외가 안 잡히면 결국 로봇이 침묵한 것과 같은 결과가 된다.
    """
    from bomi_ai_chat.prompts import builder

    def explode(name):
        raise FileNotFoundError(f"missing template: {name}")

    monkeypatch.setattr(builder, "load_template", explode)
    handlers.set_llm(RecordingLLM())

    result = handlers.handle_emotional(emotional_state("외로워"))

    assert result["response"] == handlers._EMOTIONAL_FALLBACK  # noqa: SLF001


# ── 2. 정서 + 정보가 섞인 발화 ──────────────────────────────────────────────


def test_a_mixed_utterance_is_heard_before_it_is_answered():
    """★ "외로운데 오늘 며칠이야" 는 날짜를 알려주는 턴이 아니라 듣는 턴이다.

    분류가 정서를 정보보다 먼저 보는 것은 의도다. 정보로 처리하면 사람이 아니라
    검색창처럼 반응한다. 다만 그 결과로 응답이 아예 없으면 최악이었다 — 날짜도
    못 듣고 위로도 못 받는다.
    """
    assert context_node.classify_intent(
        {"user_input": "외로운데 오늘 며칠이야"})["intent"] == "emotional"

    llm = RecordingLLM()
    handlers.set_llm(llm)

    result = handlers.handle_emotional(emotional_state("외로운데 오늘 며칠이야"))

    assert result["response"]


# ── 3. 자해는 여기 오지 않는다 ──────────────────────────────────────────────


@pytest.mark.parametrize("utterance", ["그만 살고 싶어", "죽고 싶다"])
def test_self_harm_never_reaches_this_handler(utterance):
    """★★ 트리아지가 먼저 잡아 T1 으로 보낸다. 동의를 무시한다 (§9).

    이 핸들러에 상담 로직을 쓰고 있다면 방향이 잘못된 것이다 — 그건 사람의 몫이다
    (§1 비목표). 그래서 '여기 오지 않는다'를 회귀로 고정한다.
    """
    result = triage.safety_triage({"senior_id": SENIOR, "user_input": utterance,
                                   "trigger_type": "user_utterance"})

    assert result.get("safety_level") == "T1", (
        "자해 표지가 정서 핸들러로 흘러가면 로봇이 상담을 시도하게 된다")


# ── 4. T3 동의는 '지금' 묻지 않는다 ─────────────────────────────────────────


def test_the_consent_question_is_not_asked_in_the_same_turn(frozen_clock):
    """★★★ 이 티켓에서 가장 중요한 검증.

    속마음을 꺼내는 순간 공유 이야기로 끊으면, 로봇은 그 한 문장으로 말벗에서
    감시 장치가 된다. 그 뒤로 어르신은 털어놓지 않는다.
    """
    frozen_clock(start=1_700_000_000.0)
    llm = RecordingLLM()
    handlers.set_llm(llm)

    result = handlers.handle_emotional(emotional_state("외로워"))

    assert "가족" not in result["response"]
    assert "아드님" not in result["response"]
    # 태도 지시가 프롬프트에서도 그것을 금지하고 있어야 한다. 응답만 확인하면
    # 대역 LLM 이 마침 그런 말을 안 했을 뿐인 경우와 구분되지 않는다.
    assert "지금 꺼내지 않습니다" in llm.last_prompt


def test_a_single_emotional_utterance_does_not_queue_a_consent_question(frozen_clock):
    """★★★ (253 완료 조건) 한 번의 정서 발화로는 동의 요청이 생기지 않는다.

    263 은 첫 마디에 곧바로 큐잉했다. 하루에 스쳐 지나가듯 한 말에도 45분 뒤
    "가족분께 전해도 될까요"가 날아오면 그 자체가 감시처럼 느껴진다 — 그래서
    253 은 누적 문턱을 넘겨야만 묻는다(policy.T3_CONSENT_SIGNAL_THRESHOLD).
    """
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    handlers.handle_emotional(emotional_state("외로워"))
    ticks.consent_tick(SENIOR)

    assert proposal_store.pending(SENIOR) == []


def test_the_consent_question_is_queued_once_the_threshold_is_crossed(frozen_clock):
    """누적 신호가 문턱을 넘기면 정확히 한 건, 지금 묻지는 않는다(큐에만 들어간다)."""
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    ticks.consent_tick(SENIOR)

    queued = proposal_store.pending(SENIOR)
    assert len(queued) == 1
    assert (queued[0].get("meta") or {}).get("t3_consent") is True
    assert queued[0]["priority"] == "low", (
        "동의 질문이 복약이나 안전 프로브를 밀어낼 이유가 없다")


def test_only_one_consent_question_is_pending_at_a_time(frozen_clock):
    """★ 정서 대화가 이어질 때마다 만들면 하루에 여러 번 같은 것을 묻게 된다."""
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD * 3):
        handlers.handle_emotional(emotional_state("외로워"))
        ticks.consent_tick(SENIOR)

    assert len(proposal_store.pending(SENIOR)) == 1


def test_the_consent_turn_does_not_queue_another_consent_question(frozen_clock):
    """★ 동의 질문이 동의 질문을 낳으면 큐가 무한히 자란다.

    능동 턴은 게이트가 이긴 제안의 origin 을 speech_origin 으로 실어 준다.
    그 표식으로 '이번 턴이 이미 동의를 여쭤보는 턴'임을 알아본다.
    """
    frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())

    handlers.handle_emotional(emotional_state(
        "아까 하신 이야기, 가족분께 전해도 될까요?",
        speech_origin="t3_consent: 어르신이 마음을 이야기하셨습니다."))

    assert proposal_store.pending(SENIOR) == []


def test_no_senior_id_means_nothing_is_queued():
    """큐의 키가 어르신 id 다. 임의의 키로 넣으면 아무도 집어가지 않는 행이 쌓인다."""
    handlers.set_llm(RecordingLLM())

    result = handlers.handle_emotional(
        {"ctx": {}, "intent": "emotional", "user_input": "외로워"})

    assert result["response"]
    assert proposal_store.pending("") == []


# ── 5. 지연이 실제로 지켜진다 ───────────────────────────────────────────────


def _queue_a_consent_question() -> None:
    """테스트용 헬퍼: 문턱을 넘겨 동의 질문 하나를 큐에 넣는다."""
    for _ in range(policy.T3_CONSENT_SIGNAL_THRESHOLD):
        handlers.handle_emotional(emotional_state("외로워"))
    ticks.consent_tick(SENIOR)


def test_the_gate_defers_a_proposal_that_is_not_due_yet(frozen_clock):
    """★★ 이 확인이 없으면 T3_CONSENT_DELAY_SEC 는 장식이다.

    큐에 넣은 제안은 다음 틱에 바로 후보가 된다. 45분 뒤에 묻겠다는 의도가
    코드 어디에서도 지켜지지 않는다.
    """
    sim = frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    _queue_a_consent_question()

    proposal = proposal_store.pending(SENIOR)[0]

    assert gate.is_too_early(proposal) is True

    sim.advance(policy.T3_CONSENT_DELAY_SEC + 1)
    assert gate.is_too_early(proposal) is False


def test_deferring_is_not_discarding(frozen_clock):
    """★ 아직 이른 제안을 폐기하면 영영 사라진다 — 정확히 반대 방향의 실수다."""
    sim = frozen_clock(start=1_700_000_000.0)
    handlers.set_llm(RecordingLLM())
    _queue_a_consent_question()

    proposal = proposal_store.pending(SENIOR)[0]
    # 아직 이르지만, 만료된 것은 아니다.
    assert gate.is_too_early(proposal) is True
    assert gate.is_still_valid(proposal, {"senior_id": SENIOR}) is True

    sim.advance(policy.T3_CONSENT_DELAY_SEC + policy.T3_CONSENT_TTL_SEC + 1)
    # 이제는 만료다. 이틀 전 이야기를 다시 묻는 것은 어색하다.
    assert gate.is_still_valid(proposal, {"senior_id": SENIOR}) is False


def test_a_proposal_without_not_before_is_unaffected():
    """기존 제안 전부가 이 게이트를 그냥 통과해야 한다."""
    assert gate.is_too_early({"intent": "companion", "priority": "low"}) is False
    assert gate.is_too_early({"meta": {"slot_key": "med-09:00"}}) is False


# ── 6. 태도 지시는 정서 턴에만 ──────────────────────────────────────────────


def test_the_stance_instructions_are_only_in_emotional_prompts():
    """★ system.md 에 넣으면 모든 턴에 들어간다.

    "조언하지 마세요"를 늘 켜 두면 정보 질문에도 조언을 못 하게 되고,
    "약은 식후에 드세요"를 말하지 못한다. 태도는 턴의 성격에 따라 바뀐다.
    """
    emotional = build_prompt({}, "emotional", "외로워")
    info = build_prompt({}, "info", "오늘 며칠이야")

    assert "조언하지 않습니다" in emotional
    assert "조언하지 않습니다" not in info


def test_the_prompt_forbids_narrating_internal_machinery():
    """기록·저장·알림 같은 내부 동작을 말하지 않는다 (§17.9)."""
    prompt = build_prompt({}, "emotional", "외로워")

    assert "기록" in prompt
    assert "상담" in prompt

def test_the_avoid_list_still_applies_on_the_emotional_path():
    """★★ 사별 이야기가 나오는 턴이 하필 정서 턴이다.

    "보고 싶다" 는 돌아가신 배우자 이야기일 가능성이 높은 발화다. 바로 그 턴에서
    회피 목록이 빠지면, 로봇이 돌아가신 분을 살아 있는 것처럼 꺼낼 수 있다 —
    이 시스템이 낼 수 있는 최악의 실패 중 하나다 (CLAUDE.md §17.5).

    정서 턴에만 태도 지시를 '추가'하는 구조라서, 공통 블록이 빠지지 않았는지
    확인해 둔다.
    """
    ctx = {"profile": {"name": "김순자", "avoidTopics": ["남편 사망"]}}

    prompt = build_prompt(ctx, "emotional", "보고 싶다")

    assert "말하지 않을 주제" in prompt
    assert "남편 사망" in prompt
    # 끝에서 한 번 더 못박는 것까지 유지되어야 한다. 모델은 마지막에 읽은 것을
    # 더 잘 따르고, 이것이 이 프롬프트에서 가장 어겨서는 안 되는 제약이다.
    assert prompt.rindex("말하지 않을") > prompt.index("지금 필요한 태도")
