"""기억 프라이버시 — "우리끼리 얘기"와 "기억하지 마" (자연스러운 대화 Phase 5-1단계).

이 파일이 검증하는 것
    1. T4 봉인이 정서 턴만이 아니라 '모든' 반응형 턴에서 걸린다 (§9 — T4 는
       진짜여야 한다. 인텐트 분류 결과에 따라 지켜지는 비밀은 비밀이 아니다)
    2. 시나리오 K: "기억하지 마" → 이 대화의 추출 대기 행이 지워지고, 이후
       발화도 봉인으로 추출되지 않는다
    3. 정직한 한계: 이미 서버로 제출된(extracted=1) 행은 로컬에서 지우지 않는다 —
       대신 서버 취소 요청이 큐잉되어 백엔드의 /cancel 로 전달된다 (S15P11E102-348)
    4. 프로필의 대화 성향·만성 통증 부위가 프롬프트에 실린다 (Phase 3)
    5. 프로필 주소가 오면 "오늘 날씨 어때?"가 그 지역으로 조회된다 (시나리오 C
       의 로봇 쪽 절반 — 계약에 주소가 없는 동안은 기존 되묻기 유지)
    6. 서버 취소 큐: forget 이 큐잉하고, flush 가 성공 시에만 지우며, 실패 행은
       남아 재시도된다 — "지웠어요"가 네트워크 단절에 지지 않는다

참고
    CLAUDE.md §9(T4)·§30, docs/natural-conversation/implementation-plan.md P1-B1·P1-A5
"""

import pytest

from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import ingress
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import cancellations, db, emotion, extraction
from bomi_ai_chat.prompts.builder import build_prompt

SENIOR = "senior-1"
CONV = "conv-77"
NOW = 1_700_000_000.0


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    context_node.set_weather_client(None)


def reactive_state(text, **overrides):
    return {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "conversation_id": CONV,
        "user_input": text,
        "user_input_duration_sec": 2.0,
        **overrides,
    }


# ── 1. 봉인이 인텐트와 무관하게 걸린다 ──────────────────────────────────────


def test_a_seal_marker_in_casual_talk_seals_the_conversation(frozen_clock):
    """★ 잡담 중의 "우리끼리 얘긴데"도 봉인이다.

    예전에는 handle_emotional 안에서만 검사해서, companion 으로 분류된 턴의
    비밀 요청이 조용히 무시되고 그 발화가 추출 큐로 들어갔다.
    """
    frozen_clock(start=NOW)

    ingress.note_interaction(reactive_state("우리끼리 얘긴데 요즘 입맛이 통 없어"))

    assert emotion.is_conversation_sealed(SENIOR, CONV) is True


def test_an_ordinary_turn_does_not_seal_anything(frozen_clock):
    frozen_clock(start=NOW)

    ingress.note_interaction(reactive_state("오늘 날씨 어때"))

    assert emotion.is_conversation_sealed(SENIOR, CONV) is False


# ── 2. 시나리오 K: "기억하지 마" ────────────────────────────────────────────


def test_scenario_k_forget_drops_pending_rows_and_seals(frozen_clock):
    """★ "아까 아들 이야기는 기억하지 마" — 대기 중 추출이 지워지고 봉인된다."""
    frozen_clock(start=NOW)
    extraction.enqueue(
        SENIOR, conversation_id=CONV, source_message_id="msg-1",
        content="아들이 이번 주에도 못 온대")
    assert extraction.pending_count(SENIOR) == 1

    ingress.note_interaction(reactive_state("아까 아들 이야기는 기억하지 마"))

    assert extraction.pending_count(SENIOR) == 0, "대기 행이 지워져야 한다"
    assert emotion.is_conversation_sealed(SENIOR, CONV) is True, \
        "봉인까지 걸려야 '이후' 발화도 추출되지 않는다"


def test_forget_leaves_other_conversations_alone(frozen_clock):
    """다른 대화의 기억까지 지우면 안 된다 — 요청은 '이 이야기'에 대한 것이다."""
    frozen_clock(start=NOW)
    extraction.enqueue(
        SENIOR, conversation_id="conv-earlier", source_message_id="msg-0",
        content="어제 병원 다녀왔어")

    ingress.note_interaction(reactive_state("기억하지 마"))

    assert extraction.pending_count(SENIOR) == 1


def test_forget_does_not_touch_already_submitted_rows(frozen_clock):
    """★ 정직한 한계: extracted=1(이미 제출됨)은 지우지 않는다.

    로봇 쪽 행을 지워 봐야 서버의 fact_candidate 는 그대로다. 지울 수 없는 것을
    지웠다고 보고하는 것이 이 저장소가 금지하는 실패 유형이다(§26).
    """
    frozen_clock(start=NOW)
    row_id = extraction.enqueue(
        SENIOR, conversation_id=CONV, source_message_id="msg-1",
        content="아들이 못 온대")
    extraction.mark_extracted(row_id)

    dropped = extraction.forget_conversation(SENIOR, CONV)

    assert dropped == 0


def test_forget_without_a_conversation_id_is_a_safe_noop(frozen_clock):
    """대화를 특정할 수 없으면(첫 턴 등) 아무것도 지우지 않는다 — 과잉 삭제 방지."""
    frozen_clock(start=NOW)
    extraction.enqueue(
        SENIOR, conversation_id="conv-earlier", source_message_id="msg-0",
        content="어제 병원 다녀왔어")

    ingress.note_interaction(reactive_state("기억하지 마", conversation_id=None))

    assert extraction.pending_count(SENIOR) == 1


# ── 2b. 서버 취소 큐 (S15P11E102-348 로봇 절반) ─────────────────────────────


class RecordingCancelClient:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def cancel_conversation(self, senior_id, conversation_id):
        if self.fail:
            raise RuntimeError("backend down")
        self.calls.append((senior_id, conversation_id))


def test_forget_queues_the_server_cancel(frozen_clock):
    """★ "기억하지 마"는 로컬 삭제에 더해 서버 취소를 큐잉한다.

    이미 서버로 제출된 후보는 로컬 삭제가 닿지 못한다 — 서버의 /cancel 절반이
    있어야 약속이 온전해진다. 턴 경로에서 HTTP 를 부르지 않는 이유는 지연
    예산(§16)과 네트워크 단절 시 유실 방지다.
    """
    frozen_clock(start=NOW)

    ingress.note_interaction(reactive_state("아까 아들 이야기는 기억하지 마"))

    assert cancellations.pending_count(SENIOR) == 1


def test_the_flush_delivers_and_marks_done(frozen_clock):
    frozen_clock(start=NOW)
    cancellations.enqueue(SENIOR, CONV)
    client = RecordingCancelClient()

    sent = ticks._flush_cancel_requests(SENIOR, client)

    assert sent == 1
    assert client.calls == [(SENIOR, CONV)]
    assert cancellations.pending_count(SENIOR) == 0


def test_a_failed_delivery_stays_queued_for_retry(frozen_clock):
    """★ 네트워크가 끊긴 순간의 "지웠어요"가 거짓말이 되지 않는다 — 행이 남아
    다음 flush 가 재시도한다. 서버 쪽이 멱등이라 중복 전송은 안전하다."""
    frozen_clock(start=NOW)
    cancellations.enqueue(SENIOR, CONV)

    sent = ticks._flush_cancel_requests(SENIOR, RecordingCancelClient(fail=True))

    assert sent == 0
    assert cancellations.pending_count(SENIOR) == 1, "실패한 요청을 잃으면 안 된다"


def test_a_repeat_forget_after_done_requeues(frozen_clock):
    """처리 완료된 대화에 새 요청이 오면 다시 대기로 돌아간다 — 그 사이 새 후보가
    제출됐을 수 있고, 어르신의 새 요청은 그것까지 지우라는 뜻이다."""
    frozen_clock(start=NOW)
    cancellations.enqueue(SENIOR, CONV)
    ticks._flush_cancel_requests(SENIOR, RecordingCancelClient())
    assert cancellations.pending_count(SENIOR) == 0

    cancellations.enqueue(SENIOR, CONV)

    assert cancellations.pending_count(SENIOR) == 1


def test_duplicate_forget_requests_collapse_into_one_row(frozen_clock):
    frozen_clock(start=NOW)
    cancellations.enqueue(SENIOR, CONV)
    cancellations.enqueue(SENIOR, CONV)

    assert cancellations.pending_count(SENIOR) == 1


# ── 3. Phase 3: 프로필 필드가 실제로 쓰인다 ─────────────────────────────────


def test_conversation_preferences_and_chronic_pain_reach_the_prompt():
    """백엔드가 주는데 로봇이 안 읽던 필드 2개(감사 C1)가 프롬프트에 실린다."""
    prompt = build_prompt(
        ctx={"profile": {
            "preferredName": "순자 어르신",
            "conversationPreferences": "짧고 다정한 말투를 좋아함",
            "chronicPainArea": "무릎",
        }},
        intent="companion", user_input="안녕",
    )

    assert "짧고 다정한 말투" in prompt
    assert "무릎" in prompt
    assert "새 증상과 구분" in prompt, "만성 부위는 '구분해서 들으라'는 맥락까지 실려야 한다"


class FakeWeather:
    def __init__(self):
        self.cities = []

    def get_forecast(self, city):
        self.cities.append(city)
        return {"기온": "22", "하늘상태": "1"}


def test_scenario_c_profile_address_becomes_the_default_region(frozen_clock):
    """★ 시나리오 C(로봇 쪽 절반): 주소가 오면 "오늘 날씨 어때?"가 그 지역이 된다.

    백엔드 계약(SeniorProfile)에는 아직 address 가 없다 — 이 테스트는 '필드가
    오는 순간' 동작한다는 준비 상태를 고정한다. 계약 확장은 BE 티켓.
    """
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    state = {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": "오늘 날씨 어때?",
        "context_candidates": [],
        "ctx": {"profile": {"address": "부산광역시 부산진구"}},
    }

    docs, _ = context_node._gather_lookup_documents(state)

    assert weather.cities == ["부산"]
    assert docs and docs[0]["title"] == "부산 날씨"


def test_no_address_keeps_the_ask_back_behavior(frozen_clock):
    """주소가 없으면 현행 유지 — 조회하지 않고 모델이 되묻는다. 지어내지 않는다."""
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    state = {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": "오늘 날씨 어때?",
        "context_candidates": [],
        "ctx": {"profile": {}},
    }

    docs, _ = context_node._gather_lookup_documents(state)

    assert weather.cities == []
    assert docs == []
