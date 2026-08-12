"""현재 대화 문맥(지역) — 자연스러운 대화 Phase 2 회귀.

이 파일이 검증하는 필수 시나리오
    B: "오늘 날씨 어때?" 다음의 "비는?" 이 같은 지역으로 조회된다
    D: "이번 주말에 제주도 가" 뒤의 날씨·"거기" 질문이 제주로 이어진다
    E: "그런데 오늘 분리수거 날이야?" 는 제주 문맥을 끌어오지 않는다
    H: "대전 말고 대구" 정정 후 "거긴 덥나?" 가 대구로 해석되고 대전은 사라진다

핵심 설계 (graph/context_slots.py)
    문장 수준 이어짐은 LLM+최근 대화 블록의 몫이지만, '조회 파라미터'는
    프롬프트를 읽지 못한다. 그래서 지역만 결정론 규칙으로 유지·감쇠·정정한다.
    값이 아니라 근거(출처·신뢰도·만료)를 함께 저장한다 — 틀렸을 때 설명할 수
    있어야 고칠 수 있다.

참고
    docs/natural-conversation/target-architecture.md §3, CLAUDE.md §30
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import context_slots, ingress
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"
NOW = 1_700_000_000.0


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()
    context_node.set_weather_client(None)


# ── 1. 순수 함수: 수명 규칙 ─────────────────────────────────────────────────


def test_an_explicit_city_becomes_a_full_confidence_candidate():
    out = context_slots.update([], "이번 주말에 제주도 가", NOW)

    assert len(out) == 1
    assert out[0]["value"] == "제주"
    assert out[0]["confidence"] == 1.0
    assert out[0]["source"] == context_slots.USER_EXPLICIT


def test_unrelated_turns_decay_the_candidate_until_it_dies():
    """관련 없는 이야기가 이어지면 지역 문맥은 서서히 잊힌다.

    '이전 지역명을 모든 후속 질문에 무조건 적용'(금지 사항)과 '한 턴 만에
    버리기'(시나리오 D 파괴)의 중간이 감쇠다.
    """
    candidates = context_slots.update([], "제주도 가", NOW)
    # 임계(0.4) 밑으로 내려갈 때까지 관련 없는 턴을 반복한다.
    for _ in range(10):
        candidates = context_slots.update(candidates, "아이고 무릎이야", NOW)
    assert context_slots.active(candidates, context_slots.LOCATION, NOW) is None


def test_a_few_unrelated_turns_do_not_kill_the_context():
    """시나리오 D: "날씨 어때?" → "옷은?" 정도로는 제주가 살아 있어야 한다."""
    candidates = context_slots.update([], "제주도 가", NOW)
    candidates = context_slots.update(candidates, "날씨 어때?", NOW)
    candidates = context_slots.update(candidates, "옷은 뭘 입지?", NOW)

    found = context_slots.active(candidates, context_slots.LOCATION, NOW)
    assert found is not None and found["value"] == "제주"


def test_a_reference_term_refreshes_instead_of_decaying():
    """"거기 음식은 뭐가 유명해?" — 문맥을 쓰는 중이니 잊으면 안 된다."""
    candidates = context_slots.update([], "제주도 가", NOW)
    before = context_slots.active(candidates, context_slots.LOCATION, NOW)["confidence"]

    candidates = context_slots.update(candidates, "거기 음식은 뭐가 유명해?", NOW + 60)

    after = context_slots.active(candidates, context_slots.LOCATION, NOW + 60)
    assert after is not None and after["confidence"] == before, \
        "지시 표현이 있는 턴은 감쇠하지 않는다"


def test_scenario_e_a_topic_shift_drops_the_old_region():
    """★ 시나리오 E: "그런데 오늘 분리수거 날이야?" 는 제주가 아니다."""
    candidates = context_slots.update([], "제주도 가", NOW)
    candidates = context_slots.update(candidates, "그런데 오늘 분리수거 날이야?", NOW)

    assert context_slots.active(candidates, context_slots.LOCATION, NOW) is None, \
        "화제 전환 표지 한 번이면 이전 지역의 영향이 임계 밑으로 내려가야 한다"


def test_scenario_h_a_correction_replaces_the_wrong_city():
    """★ 시나리오 H: "대전 말고 대구" — 앞의 오인식(대전)을 지우고 대구만 남긴다.

    단순 첫 매치(extract_city)는 이 문장에서 '대전'을 집는다. 정정 표지 뒤쪽을
    보는 이유다.
    """
    candidates = context_slots.update([], "내일 대전 가", NOW)  # STT 오인식
    candidates = context_slots.update(candidates, "대전 말고 대구", NOW + 10)

    found = context_slots.active(candidates, context_slots.LOCATION, NOW + 10)
    assert found is not None and found["value"] == "대구"
    values = [c["value"] for c in candidates if c["type"] == context_slots.LOCATION]
    assert "대전" not in values, "이후의 '거기'가 대전을 다시 가리키면 안 된다"


def test_candidates_expire_after_their_ttl():
    """한나절 전의 제주가 저녁 질문을 삼키면 안 된다 — 만료가 최후의 방어선."""
    candidates = context_slots.update([], "제주도 가", NOW)
    later = NOW + policy.CONTEXT_CANDIDATE_TTL_SEC + 1.0

    assert context_slots.active(candidates, context_slots.LOCATION, later) is None


def test_resolve_prefers_the_current_utterance_over_context():
    """현재 발화의 명시 정보가 항상 최우선이다 (문맥 선택 1순위)."""
    candidates = context_slots.update([], "제주도 가", NOW)

    city, source = context_slots.resolve_location(candidates, "부산 날씨 어때?", NOW)

    assert (city, source) == ("부산", "utterance")


def test_resolve_falls_back_to_the_living_context():
    candidates = context_slots.update([], "제주도 가", NOW)

    city, source = context_slots.resolve_location(candidates, "날씨 어때?", NOW)

    assert city == "제주"
    assert source == context_slots.USER_EXPLICIT, "근거가 함께 나와야 한다"


def test_resolve_returns_none_when_nothing_is_known():
    """모르면 모른다고 한다. 지어내지 않는다 — 되묻기는 호출부의 몫."""
    assert context_slots.resolve_location([], "날씨 어때?", NOW) == (None, "none")


# ── 2. note_interaction 배선: 턴마다 갱신, 경계에서 리셋 ────────────────────


def reactive_state(text, **overrides):
    return {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": text,
        "user_input_duration_sec": 2.0,
        **overrides,
    }


def test_note_interaction_updates_the_candidates_every_turn(frozen_clock):
    frozen_clock(start=NOW)

    out = ingress.note_interaction(reactive_state("이번 주말에 제주도 가"))

    values = [c["value"] for c in out["context_candidates"]]
    assert values == ["제주"]


def test_a_conversation_boundary_clears_session_context(frozen_clock):
    """30분 넘게 자리를 비웠다 돌아온 "날씨 어때?"는 아침의 제주가 아니다.

    문맥의 수명과 '최근 대화'(conversation_id)의 수명이 같아야 프롬프트에는
    없는 지역으로 조회하는 어긋남이 안 생긴다.
    """
    clk = frozen_clock(start=NOW)
    candidates = context_slots.update([], "제주도 가", NOW)
    clk.advance(policy.CONVERSATION_BOUNDARY_IDLE_SEC + 60.0)

    out = ingress.note_interaction(reactive_state(
        "날씨 어때?",
        context_candidates=candidates,
        last_user_interaction_at=NOW,
    ))

    assert out["conversation_id"] is None, "경계를 넘었으니 새 대화"
    assert out["context_candidates"] == [], "SESSION 문맥도 함께 비워야 한다"


# ── 3. 날씨 조회가 문맥을 실제로 쓴다 (시나리오 B·D·H 의 조회 단면) ─────────


class FakeWeather:
    def __init__(self, forecast=None):
        self.forecast = forecast or {"기온": "22", "하늘상태": "1"}
        self.cities: list[str] = []

    def get_forecast(self, city):
        self.cities.append(city)
        return self.forecast


def lookup_state(text, candidates):
    return {
        "senior_id": SENIOR,
        "trigger_type": "user_utterance",
        "user_input": text,
        "context_candidates": candidates,
    }


def test_scenario_d_weather_follows_the_trip_context(frozen_clock):
    """★ 시나리오 D: "제주도 가" 다음의 "날씨 어때?" 가 제주로 조회된다."""
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    candidates = context_slots.update([], "이번 주말에 제주도 가", NOW)

    docs, _ = context_node._gather_lookup_documents(
        lookup_state("날씨 어때?", candidates))

    assert weather.cities == ["제주"]
    assert docs and docs[0]["title"] == "제주 날씨"


def test_scenario_b_a_followup_keeps_the_region(frozen_clock):
    """★ 시나리오 B: 이어지는 질문에 지역을 다시 말하지 않아도 부산으로 조회된다."""
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    candidates = context_slots.update([], "부산 날씨 어때?", NOW)

    docs, _ = context_node._gather_lookup_documents(
        lookup_state("내일 날씨는?", candidates))

    assert weather.cities == ["부산"]
    assert docs


def test_scenario_h_after_a_correction_the_lookup_uses_the_new_city(frozen_clock):
    """★ 시나리오 H 후반: 정정 뒤의 질문은 대구로 조회된다."""
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    candidates = context_slots.update([], "내일 대전 가", NOW)
    candidates = context_slots.update(candidates, "대전 말고 대구", NOW)

    docs, _ = context_node._gather_lookup_documents(
        lookup_state("거기 날씨 덥나?", candidates))

    assert weather.cities == ["대구"]
    assert docs


def test_a_followup_needs_an_open_weather_thread(frozen_clock):
    """★ "비는?" 은 날씨 대화가 열려 있을 때만 조회된다 (2026-08-10 피드백).

    조회 표지는 '날씨' 하나로 좁혔다 — "오늘 좀 춥네" 같은 잡담이 예보를 프롬프트에
    밀어 넣지 않게 하려는 것이다. 후속 질문은 그 규칙의 예외이고, 예외를 여는 열쇠는
    어르신이 쥔다: 먼저 '날씨'를 꺼낸 대화 안에서만 넓은 표지가 살아난다.

    아래 두 경우가 정확히 그 차이다. 같은 "거긴 덥나?"인데 앞선 발화가 다르다.
    """
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    candidates = context_slots.update([], "부산 날씨 어때?", NOW)

    opened = context_node.next_weather_thread_at(
        lookup_state("부산 날씨 어때?", candidates))
    assert opened is not None

    for followup in ("비는?", "거긴 덥나?"):
        weather.cities.clear()
        state = lookup_state(followup, candidates)
        state["weather_thread_at"] = opened
        docs, _ = context_node._gather_lookup_documents(state)
        assert weather.cities == ["부산"], followup
        assert docs, followup

    # 날씨를 꺼낸 적 없는 대화(여행 이야기만 오간 경우)에서는 같은 말이 조용하다.
    trip_only = context_slots.update([], "내일 대구 가", NOW)
    weather.cities.clear()
    docs, _ = context_node._gather_lookup_documents(
        lookup_state("거긴 덥나?", trip_only))
    assert weather.cities == []
    assert docs == []


def test_the_weather_thread_expires(frozen_clock):
    """열어둔 창은 policy.WEATHER_FOLLOWUP_WINDOW_SEC 이 지나면 닫힌다.

    닫히지 않으면 한나절 뒤의 "덥네" 한마디가 아침에 한 날씨 질문을 근거로 다시
    기상청을 부른다 — 좁힌 이유가 그대로 무너진다.
    """
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)
    candidates = context_slots.update([], "부산 날씨 어때?", NOW)

    stale = NOW - policy.WEATHER_FOLLOWUP_WINDOW_SEC - 1
    state = lookup_state("비는?", candidates)
    state["weather_thread_at"] = stale

    docs, _ = context_node._gather_lookup_documents(state)

    assert weather.cities == []
    assert docs == []
    assert context_node.next_weather_thread_at(state) is None


def test_no_context_and_no_city_still_means_no_lookup(frozen_clock):
    """문맥도 도시도 없으면 조회하지 않는다 — 모델이 되묻는 기존 동작 유지.

    (프로필 주소가 계약에 들어오면 PROFILE_DEFAULT 후보가 이 빈자리를 채운다.)
    """
    frozen_clock(start=NOW)
    weather = FakeWeather()
    context_node.set_weather_client(weather)

    docs, _ = context_node._gather_lookup_documents(lookup_state("날씨 어때?", []))

    assert weather.cities == []
    assert docs == []
