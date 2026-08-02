"""계약 주도형 대화 — 209 완료 조건 회귀.

이 파일이 검증하는 완료 조건
    1. 온보딩 세션을 음성만으로 완주 (필수 질문 + 동의 거절 경로)
    2. 복약 용량 누락 시 한 필드만 재질의
    3. 한 대화에서 두 번째 후보를 질의하지 않음
    4. 백엔드에 못 닿을 때 시도하지 않고 조용히 넘어감

가장 중요한 세 가지
    test_a_non_committal_answer_is_not_a_confirmation
        "글쎄"를 긍정으로 읽으면, 어르신이 동의한 적 없는 건강정보 처리에 동의
        기록이 남는다. 이 한 줄이 그것을 막는다.

    test_a_direct_question_is_answered_before_the_pending_re_ask
        보류된 재질의가 어르신의 질문을 가로채면 대화 상대가 아니라 심문관이 된다.

    test_consent_is_never_decided_by_the_model
        동의 판정이 모델로 넘어가면 "동의한 것으로 보인다"가 되고, 그 근거는
        재현되지 않는다.

참고
    CLAUDE.md §8 (확인으로 인정하지 않는 것), §12 (계약 주도형 대화)
    S15P11E102-209, S15P11E102-227(서버 측)
"""

import pytest

from bomi_ai_chat.backend_client.contract_client import BackendUnavailable
from bomi_ai_chat.graph import context, contract_dialogue, handlers
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import db, proposals

SENIOR = "senior-1"
SESSION = "session-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


@pytest.fixture(autouse=True)
def reset_clients():
    """핸들러의 전역 클라이언트를 테스트마다 비운다."""
    yield
    handlers.set_contract_clients(None, None)
    handlers.set_llm(None)


class FakeLLM:
    """지정한 문자열을 그대로 돌려주는 대역. 호출 횟수를 센다."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else ""


class FakeOnboarding:
    """227 온보딩 API 대역."""

    def __init__(self, *, questions=None, outcomes=None, offline=False):
        self.questions = list(questions or [])
        self.outcomes = list(outcomes or [])
        self.offline = offline
        self.submitted: list[dict] = []
        self.status = "IN_PROGRESS"

    def start_or_resume(self, senior_id, robot_id):
        self._guard()
        return {"sessionId": SESSION, "seniorId": senior_id, "status": self.status,
                "startedChannel": "APP"}

    def next_question(self, session_id):
        self._guard()
        return self.questions.pop(0) if self.questions else None

    def submit_answer(self, session_id, question_code, answer_value, *, confirmed,
                      conversation_id=None, source_message_id=None):
        self._guard()
        self.submitted.append({
            "questionCode": question_code,
            "answerValue": answer_value,
            "confirmed": confirmed,
        })
        return self.outcomes.pop(0) if self.outcomes else {"outcome": "ACCEPTED"}

    def _guard(self):
        if self.offline:
            raise BackendUnavailable("robot-onboarding unreachable: test")


class FakeClarification:
    """227 재질의 API 대역."""

    def __init__(self, *, candidates=None, outcomes=None, offline=False):
        self.candidates = list(candidates or [])
        self.outcomes = list(outcomes or [])
        self.offline = offline
        self.answered: list[dict] = []

    def active(self, senior_id):
        self._guard()
        return self.candidates.pop(0) if self.candidates else None

    def answer(self, candidate_id, field_values, *, confirmed,
               conversation_id=None, source_message_id=None):
        self._guard()
        self.answered.append({
            "candidateId": candidate_id,
            "fieldValues": field_values,
            "confirmed": confirmed,
        })
        return self.outcomes.pop(0) if self.outcomes else {"outcome": "CONFIRMED"}

    def _guard(self):
        if self.offline:
            raise BackendUnavailable("robot-clarification unreachable: test")


def consent_question(code="HEALTH_DATA_CONSENT"):
    return {
        "questionCode": code,
        "robotPrompt": "건강 상태와 복약 정보를 돌봄 서비스에 사용하도록 저장해도 될까요?",
        "requiredFields": ["consentStatus"],
        "sensitive": True,
        "requiresConfirmation": True,
        "status": "IN_PROGRESS",
    }


def medication_question():
    return {
        "questionCode": "MEDICATION",
        "robotPrompt": "현재 드시는 약의 이름과 한 번에 드시는 양, 단위를 알려 주세요.",
        "requiredFields": ["medicationName", "dose", "doseUnit"],
        "sensitive": True,
        "requiresConfirmation": True,
        "status": "IN_PROGRESS",
    }


# ── 확인 판정: 결정적이어야 하는 부분 ────────────────────────────────────────


@pytest.mark.parametrize("text", ["네", "응", "그래", "그렇게 해줘", "알겠어", "동의해요"])
def test_explicit_yes_is_a_confirmation(text):
    assert contract_dialogue.read_affirmation(text) is True
    assert contract_dialogue.is_confirmation(text) is True


@pytest.mark.parametrize("text", ["아니요", "싫어", "안 돼", "하지 마", "됐어"])
def test_explicit_no_is_a_refusal(text):
    assert contract_dialogue.read_affirmation(text) is False
    assert contract_dialogue.is_confirmation(text) is False


@pytest.mark.parametrize("text", ["글쎄", "아마도", "잘 모르겠어", "나중에 얘기해", "몰라"])
def test_a_non_committal_answer_is_not_a_confirmation(text):
    """★ 얼버무림은 긍정도 부정도 아니다.

    긍정으로 읽으면 동의한 적 없는 동의가 기록된다. 부정으로 읽으면 거절한 적 없는
    거절이 기록되고 그에 딸린 질문이 영영 안 나온다. 판정 불가의 올바른 처리는
    '다시 묻기'다.
    """
    assert contract_dialogue.read_affirmation(text) is None


def test_silence_is_not_a_confirmation():
    assert contract_dialogue.read_affirmation("") is None
    assert contract_dialogue.read_affirmation("   ") is None


def test_an_answer_to_a_different_question_is_not_a_confirmation():
    """멀쩡한 문장이지만 예/아니오가 아니다. '답변이 있었다'로 처리하면 안 된다."""
    assert contract_dialogue.read_affirmation("오늘 날씨가 참 좋네") is None


def test_negation_is_read_before_affirmation():
    """★ "그래, 그건 아니야" 를 긍정으로 읽으면 정반대로 판정한다.

    206 의 `_is_completion_report` 가 "약 안 먹었어"에서 만난 것과 같은 함정이다.
    """
    assert contract_dialogue.read_affirmation("그래, 그건 아니야") is False


def test_gwaenchana_is_not_treated_as_yes():
    """한국어에서 권유에 대한 "괜찮아요"는 거절인 경우가 많다.

    동의 판정에서 그 모호함은 감당할 수 없으므로 긍정 목록에 넣지 않았다.
    """
    assert contract_dialogue.read_affirmation("괜찮아요") is None


def test_read_back_reads_values_not_field_names():
    """복창은 값만 읽는다. 필드명은 계약의 언어이지 사람의 언어가 아니다."""
    spoken = contract_dialogue.read_back({"medicationName": "혈압약", "dose": 1, "doseUnit": "정"})

    assert "혈압약" in spoken
    assert "medicationName" not in spoken
    assert "dose" not in spoken


# ── 온보딩: 음성만으로 완주 ──────────────────────────────────────────────────


def test_the_contract_sentence_is_spoken_verbatim():
    """★ robotPrompt 를 다시 쓰지 않는다.

    LLM 으로 다듬으면 앱이 화면에 보여주는 문장과 달라진다. 동의 문구라면 어르신이
    들은 동의와 기록된 동의가 다른 것이 된다.
    """
    llm = FakeLLM("이건 절대 쓰이면 안 되는 문장")
    handlers.set_llm(llm)
    handlers.set_contract_clients(FakeOnboarding(questions=[consent_question()]), None)

    out = handlers.handle_onboarding({"senior_id": SENIOR, "robot_id": "robot-1"})

    assert out["response"] == consent_question()["robotPrompt"]
    # 질문을 말하는 데 생성 호출을 쓰지 않는다.
    assert llm.prompts == []


def test_consent_is_never_decided_by_the_model():
    """★ 동의 판정에 LLM 을 쓰지 않는다.

    모델에게 물으면 "동의한 것으로 보인다"가 되고, 그 판정은 재현되지 않는다.
    나중에 "어르신이 정말 동의했는가"에 답할 수 있어야 한다.
    """
    llm = FakeLLM()
    handlers.set_llm(llm)
    client = FakeOnboarding(questions=[None])
    handlers.set_contract_clients(client, None)

    handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "네, 그렇게 해요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION,
            "question_code": "HEALTH_DATA_CONSENT", "fields": ["consentStatus"],
            "stage": "ask", "fact_type": "HEALTH_DATA_CONSENT",
        },
    })

    assert llm.prompts == []
    assert client.submitted[0]["answerValue"] == {"consentStatus": "GRANTED"}


def test_refusing_consent_is_sent_as_denied():
    """동의 거절 경로. 거절도 답변이며, 기록되어야 그에 딸린 질문이 건너뛰어진다."""
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding(questions=[None])
    handlers.set_contract_clients(client, None)

    handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "아니요, 싫어요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION,
            "question_code": "HEALTH_DATA_CONSENT", "fields": ["consentStatus"],
            "stage": "ask", "fact_type": "HEALTH_DATA_CONSENT",
        },
    })

    assert client.submitted[0]["answerValue"] == {"consentStatus": "DENIED"}


def test_a_vague_consent_answer_is_asked_again_not_recorded():
    """★ "글쎄"에는 아무것도 제출하지 않는다."""
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding()
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "글쎄, 잘 모르겠는데",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION,
            "question_code": "HEALTH_DATA_CONSENT", "fields": ["consentStatus"],
            "stage": "ask", "fact_type": "HEALTH_DATA_CONSENT",
        },
    })

    assert client.submitted == []
    assert out["response"]
    # 같은 질문을 계속 기다린다.
    assert out["pending_contract"]["question_code"] == "HEALTH_DATA_CONSENT"


def test_accepting_an_answer_moves_straight_to_the_next_question():
    """대화가 이어지는 동안 온보딩을 진행한다. 한 질문에 10분씩 기다리지 않는다."""
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding(
        questions=[medication_question()],
        outcomes=[{"outcome": "ACCEPTED"}])
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "네",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION,
            "question_code": "HEALTH_DATA_CONSENT", "fields": ["consentStatus"],
            "stage": "ask", "fact_type": "HEALTH_DATA_CONSENT",
        },
    })

    assert out["response"] == medication_question()["robotPrompt"]
    assert out["pending_contract"]["question_code"] == "MEDICATION"


def test_finishing_the_question_set_ends_in_silence():
    """더 물을 것이 없으면 말하지 않는다. "끝났어요"라고 선언하지 않는다."""
    handlers.set_llm(FakeLLM())
    handlers.set_contract_clients(FakeOnboarding(questions=[]), None)

    out = handlers.handle_onboarding({"senior_id": SENIOR, "robot_id": "robot-1"})

    assert out["response"] == ""
    assert out["pending_contract"] is None


# ── 민감 항목: 복창하고 확인받는다 ───────────────────────────────────────────


def test_a_sensitive_value_is_read_back_before_it_is_confirmed():
    handlers.set_llm(FakeLLM('{"medicationName": "혈압약", "dose": 1, "doseUnit": "정"}'))
    client = FakeOnboarding(outcomes=[{
        "outcome": "NEEDS_CONFIRMATION",
        "valueToConfirm": {"medicationName": "혈압약", "dose": 1, "doseUnit": "정"},
    }])
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "혈압약 한 정 먹어요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION, "question_code": "MEDICATION",
            "fields": ["medicationName", "dose", "doseUnit"], "stage": "ask",
            "fact_type": "MEDICATION",
        },
    })

    assert "혈압약" in out["response"]
    assert out["pending_contract"]["stage"] == "confirm"
    # 아직 확정하지 않았다.
    assert client.submitted[0]["confirmed"] is False


def test_only_an_explicit_yes_confirms_a_sensitive_value():
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding(questions=[None], outcomes=[{"outcome": "ACCEPTED"}])
    handlers.set_contract_clients(client, None)

    handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "네, 맞아요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION, "question_code": "MEDICATION",
            "fields": ["dose"], "stage": "confirm", "value": {"dose": 1},
            "fact_type": "MEDICATION",
        },
    })

    assert client.submitted[0]["confirmed"] is True


def test_a_vague_reply_to_a_read_back_asks_once_more():
    """★ 얼버무림은 거절이 아니다. 확정도 하지 않고, 거절로 기록하지도 않는다."""
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding()
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "글쎄요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION, "question_code": "MEDICATION",
            "fields": ["dose"], "stage": "confirm", "value": {"dose": 1},
            "fact_type": "MEDICATION",
        },
    })

    assert client.submitted == []
    assert out["pending_contract"]["stage"] == "confirm"


def test_saying_no_to_a_read_back_re_asks_the_field():
    """값이 틀렸다는 뜻이다. 거절이 아니라 처음부터 다시 묻는다."""
    handlers.set_llm(FakeLLM("한 번에 몇 알 드세요?"))
    client = FakeOnboarding()
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "아니에요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION, "question_code": "MEDICATION",
            "fields": ["dose"], "stage": "confirm", "value": {"dose": 5},
            "fact_type": "MEDICATION",
        },
    })

    assert client.submitted == []
    assert out["pending_contract"]["stage"] == "ask"
    assert out["pending_contract"]["value"] == {}


# ── 재질의: 한 필드만, 필드명은 읽지 않는다 ──────────────────────────────────


def test_a_missing_dose_is_asked_as_a_human_question():
    """★ 필드명을 소리내어 읽지 않는다. "dose 가 뭐예요?"는 사람의 말이 아니다."""
    llm = FakeLLM("한 번에 몇 알 드세요?")
    handlers.set_llm(llm)
    handlers.set_contract_clients(None, FakeClarification(candidates=[{
        "factCandidateId": "cand-1",
        "clarificationReason": "MISSING_REQUIRED_FIELD",
        "missingFields": ["dose"],
        "factType": "MEDICATION",
        "riskLevel": "SENSITIVE",
        "proposedValue": {"medicationName": "혈압약"},
    }]))

    out = handlers.handle_clarification({"senior_id": SENIOR})

    assert out["response"] == "한 번에 몇 알 드세요?"
    assert "dose" not in out["response"]
    assert out["pending_contract"]["fields"] == ["dose"]


def test_a_generated_question_that_leaks_the_field_name_is_rejected():
    """모델이 필드명을 그대로 뱉으면 쓰지 않는다."""
    handlers.set_llm(FakeLLM("dose 를 알려주세요"))
    handlers.set_contract_clients(None, FakeClarification(candidates=[{
        "factCandidateId": "cand-1",
        "clarificationReason": "MISSING_REQUIRED_FIELD",
        "missingFields": ["dose"],
        "factType": "MEDICATION",
        "riskLevel": "SENSITIVE",
        "proposedValue": {},
    }]))

    out = handlers.handle_clarification({"senior_id": SENIOR})

    assert "dose" not in out["response"]


def test_the_model_cannot_invent_fields_the_contract_did_not_ask_for():
    """★ 계약이 요구하지 않은 필드는 버린다.

    모델이 만들어낸 값이 백엔드로 새어나가면, 어르신이 말한 적 없는 사실이 후보가 된다.
    """
    handlers.set_llm(FakeLLM('{"dose": 2, "bloodPressure": "높음", "mood": "좋음"}'))
    client = FakeClarification(outcomes=[{"outcome": "CONFIRMED"}])
    handlers.set_contract_clients(None, client)

    handlers.handle_clarification({
        "senior_id": SENIOR,
        "user_input": "두 알이요",
        "pending_contract": {
            "kind": "clarification", "candidate_id": "cand-1", "fields": ["dose"],
            "stage": "ask", "fact_type": "MEDICATION", "question_code": "MEDICATION",
        },
    })

    assert client.answered[0]["fieldValues"] == {"dose": 2}


def test_extraction_that_returns_nothing_does_not_submit():
    """"한 알쯤"에서 1 을 만들어내지 않는다. 못 뽑았으면 다시 묻는다."""
    handlers.set_llm(FakeLLM("{}"))
    client = FakeClarification()
    handlers.set_contract_clients(None, client)

    out = handlers.handle_clarification({
        "senior_id": SENIOR,
        "user_input": "한 알쯤 되나",
        "pending_contract": {
            "kind": "clarification", "candidate_id": "cand-1", "fields": ["dose"],
            "stage": "ask", "fact_type": "MEDICATION", "question_code": "MEDICATION",
        },
    })

    assert client.answered == []
    assert out["response"]


def test_nothing_pending_ends_in_silence():
    """물을 후보가 없는 것은 흔한 정상 결과다."""
    handlers.set_llm(FakeLLM())
    handlers.set_contract_clients(None, FakeClarification(candidates=[]))

    out = handlers.handle_clarification({"senior_id": SENIOR})

    assert out["response"] == ""
    assert out["pending_contract"] is None


# ── 어르신의 질문을 가로채지 않는다 ─────────────────────────────────────────


def test_a_direct_question_is_answered_before_the_pending_re_ask():
    """★★ 보류된 재질의가 어르신의 질문을 가로채면 대화 상대가 아니라 심문관이 된다.

    "오늘 며칠이야?"에 "약을 몇 알 드세요?"로 답하는 로봇은 쓸 수 없다.
    먼저 답하고, 재질의는 다음 턴에 이어진다.
    """
    out = context.classify_intent({
        "user_input": "오늘 며칠이야?",
        "pending_contract": {"kind": "clarification", "candidate_id": "cand-1"},
    })

    assert out["intent"] == "info"


def test_a_plain_answer_goes_to_the_pending_contract_question():
    out = context.classify_intent({
        "user_input": "혈압약 한 알이요",
        "pending_contract": {"kind": "clarification", "candidate_id": "cand-1"},
    })

    assert out["intent"] == "clarification"


def test_a_question_without_a_question_mark_still_counts():
    """ASR 은 물음표를 잘 붙이지 않는다. 어미로도 본다."""
    assert contract_dialogue.looks_like_a_question("오늘 무슨 요일이지") is False
    assert contract_dialogue.looks_like_a_question("밥 먹었나요") is True
    assert contract_dialogue.looks_like_a_question("이거 뭐야") is True


def test_no_pending_question_leaves_classification_alone():
    out = context.classify_intent({"user_input": "심심해"})

    assert out["intent"] == "companion"


# ── 오프라인: 시도하지 않는다 ────────────────────────────────────────────────


def test_onboarding_is_not_attempted_when_the_backend_is_unreachable():
    """★ 계약을 서버가 강제하는데 서버에 못 닿으면 계약이 없는 상태다.

    캐시된 질문을 되풀이하면 이미 답한 것을 또 묻고, 옛 문구로 동의를 받게 된다.
    개방형 핸들러가 캐시로 내려가는 것과 정반대의 결정이다.
    """
    handlers.set_llm(FakeLLM())
    handlers.set_contract_clients(FakeOnboarding(offline=True), None)

    out = handlers.handle_onboarding({"senior_id": SENIOR, "robot_id": "robot-1"})

    assert out["response"] == ""


def test_clarification_is_not_attempted_when_the_backend_is_unreachable():
    handlers.set_llm(FakeLLM())
    handlers.set_contract_clients(None, FakeClarification(offline=True))

    out = handlers.handle_clarification({"senior_id": SENIOR})

    assert out["response"] == ""


def test_an_offline_submit_keeps_the_question_pending():
    """제출에 실패해도 대기 상태를 잃지 않는다. 잃으면 어르신의 답이 사라진다."""
    handlers.set_llm(FakeLLM())
    pending = {
        "kind": "clarification", "candidate_id": "cand-1", "fields": ["dose"],
        "stage": "confirm", "value": {"dose": 1}, "fact_type": "MEDICATION",
        "question_code": "MEDICATION",
    }
    handlers.set_contract_clients(None, FakeClarification(offline=True))

    out = handlers.handle_clarification({
        "senior_id": SENIOR, "user_input": "네", "pending_contract": pending,
    })

    assert out["response"] == ""
    assert out["pending_contract"] == pending


def test_the_contract_tick_queues_nothing_when_offline():
    added = ticks.contract_tick(
        SENIOR, robot_id="robot-1",
        clarification_client=FakeClarification(offline=True))

    assert added == 0
    assert proposals.pending(SENIOR) == []


# ── 한 대화에 후보 하나 ─────────────────────────────────────────────────────


def test_only_one_contract_proposal_per_conversation():
    """★★ (완료 조건) 한 대화에서 두 번째 후보를 질의하지 않는다.

    백엔드가 하나만 내려주지만 그것만으로는 부족하다. 한 대화 안에서 틱이 여러 번
    돌면 첫 후보가 해결된 뒤 곧바로 두 번째가 나오고, 어르신은 연달아 심문받는다.
    """
    client = FakeClarification(candidates=[
        {"factCandidateId": "cand-1", "factType": "MEDICATION"},
        {"factCandidateId": "cand-2", "factType": "APPOINTMENT"},
    ])

    first = ticks.contract_tick(SENIOR, conversation_id="conv-1",
                                clarification_client=client)
    second = ticks.contract_tick(SENIOR, conversation_id="conv-1",
                                 clarification_client=client)

    assert first == 1
    assert second == 0
    assert len(proposals.pending(SENIOR)) == 1


def test_a_new_conversation_may_raise_the_next_candidate():
    """다음 대화에서는 다시 물을 수 있다. 영구히 막으면 후보가 영영 해결되지 않는다."""
    client = FakeClarification(candidates=[
        {"factCandidateId": "cand-1", "factType": "MEDICATION"},
        {"factCandidateId": "cand-2", "factType": "APPOINTMENT"},
    ])

    ticks.contract_tick(SENIOR, conversation_id="conv-1", clarification_client=client)
    added = ticks.contract_tick(SENIOR, conversation_id="conv-2", clarification_client=client)

    assert added == 1
    assert len(proposals.pending(SENIOR)) == 2


def test_clarification_is_raised_before_onboarding():
    """꺼내 놓은 이야기를 먼저 마무리한다. 온보딩은 새 질문이다."""
    added = ticks.contract_tick(
        SENIOR, robot_id="robot-1",
        clarification_client=FakeClarification(candidates=[
            {"factCandidateId": "cand-1", "factType": "MEDICATION"}]),
        onboarding_client=FakeOnboarding())

    assert added == 1
    assert proposals.pending(SENIOR)[0]["intent"] == "clarification"


def test_the_proposal_uses_the_clarification_priority():
    """게이트가 잡담보다 위, 안전보다 아래로 다루도록 한다 (policy.PRIORITY_RANK)."""
    ticks.contract_tick(
        SENIOR, robot_id="robot-1",
        clarification_client=FakeClarification(candidates=[
            {"factCandidateId": "cand-1", "factType": "MEDICATION"}]))

    assert proposals.pending(SENIOR)[0]["priority"] == "clarification"


def test_a_completed_session_is_not_raised_again():
    """끝난 온보딩을 다시 꺼내지 않는다."""
    onboarding = FakeOnboarding()
    onboarding.status = "COMPLETED"

    added = ticks.contract_tick(
        SENIOR, robot_id="robot-1",
        clarification_client=FakeClarification(),
        onboarding_client=onboarding)

    assert added == 0


def test_without_a_robot_id_onboarding_is_not_started():
    """새 ROBOT 세션에는 robot_id 가 필요하다. 없으면 400 을 받아 오프라인으로
    오인하는 대신 아예 시도하지 않는다."""
    added = ticks.contract_tick(
        SENIOR,
        clarification_client=FakeClarification(),
        onboarding_client=FakeOnboarding())

    assert added == 0


def test_a_long_story_starting_with_geurae_is_not_a_confirmation():
    """★ 실제로 잡힌 오탐 2.

    "그래"는 부분 일치로 이야기의 시작에도 걸린다. 복창 확인 단계에서 그것을 긍정으로
    읽으면 어르신이 확인한 적 없는 복약 용량이 확정된다.
    """
    assert contract_dialogue.read_affirmation(
        "그래서 어제 병원에 갔는데 의사 선생님이 그러시더라고") is None


def test_a_whole_word_yes_counts_even_in_a_longer_sentence():
    """낱말이 통째로 일치하면 길이와 무관하다. "네, 그리고..."의 "네"는 명백한 긍정이다."""
    assert contract_dialogue.read_affirmation(
        "네, 그리고 어제는 손자가 놀러 왔어요 아주 반가웠지") is True


@pytest.mark.parametrize("text", ["좋네", "약이 참 많네", "그러네", "비가 오네"])
def test_words_ending_in_ne_are_not_yes(text):
    """★ 실제로 잡힌 오탐 1. "네"를 부분 문자열로 찾으면 이것들이 전부 걸렸다."""
    assert contract_dialogue.read_affirmation(text) is not True


# ── 워크스루에서 잡힌 것들 ───────────────────────────────────────────────────


def test_a_consent_answer_is_not_read_back_as_an_enum():
    """★★ 워크스루에서 잡힌 결함 1 — 로봇이 어르신에게 "GRANTED" 라고 말했다.

    동의 질문은 이미 명확한 예/아니오 질문이고, 어르신은 그것을 듣고 답했다.
    값을 복창하면 내부 코드값을 읽어주는 것이고 확인에 아무것도 보태지 않는다
    (CLAUDE.md §17.9: 내부 기제를 절대 말하지 않는다).

    그래서 동의 답변은 '그 답이 곧 명시적 확인'으로 제출한다.
    """
    handlers.set_llm(FakeLLM())
    client = FakeOnboarding(questions=[None], outcomes=[{"outcome": "ACCEPTED"}])
    handlers.set_contract_clients(client, None)

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "네, 좋아요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION,
            "question_code": "PERSONALIZATION_CONSENT", "fields": ["consentStatus"],
            "stage": "ask", "fact_type": "PERSONALIZATION_CONSENT",
            "robot_prompt": "개인화된 대화를 위해 저장해도 될까요?",
        },
    })

    assert client.submitted[0]["confirmed"] is True
    assert "GRANTED" not in out["response"]


def test_a_generated_question_without_korean_is_not_spoken():
    """★★ 워크스루에서 잡힌 결함 2 — 모델이 "{}" 를 돌려줬고 그대로 TTS 로 나갔다.

    어르신은 로봇이 무의미한 소리를 내는 것을 들었다.
    """
    handlers.set_llm(FakeLLM("{}"))
    handlers.set_contract_clients(None, FakeClarification(candidates=[{
        "factCandidateId": "cand-1",
        "clarificationReason": "MISSING_REQUIRED_FIELD",
        "missingFields": ["dose"],
        "factType": "MEDICATION",
        "riskLevel": "SENSITIVE",
        "proposedValue": {},
    }]))

    out = handlers.handle_clarification({"senior_id": SENIOR})

    assert out["response"] != "{}"
    assert "{" not in out["response"]


def test_re_asking_an_onboarding_question_reuses_the_contract_sentence():
    """계약 문장이 있는데 새로 지어내면, 같은 질문이 두 번째에는 다른 문장으로 나간다.

    동의 문구라면 그것은 계약 위반이다.
    """
    llm = FakeLLM("완전히 다른 문장")
    handlers.set_llm(llm)
    handlers.set_contract_clients(FakeOnboarding(), None)
    prompt = "현재 드시는 약의 이름과 한 번에 드시는 양, 단위를 알려 주세요."

    out = handlers.handle_onboarding({
        "senior_id": SENIOR,
        "user_input": "아니요",
        "pending_contract": {
            "kind": "onboarding", "session_id": SESSION, "question_code": "MEDICATION",
            "fields": ["dose"], "stage": "confirm", "value": {"dose": 9},
            "fact_type": "MEDICATION", "robot_prompt": prompt,
        },
    })

    assert out["response"] == prompt
    assert llm.prompts == []
