"""날씨·의료 조회가 context_read 에서 이뤄지는지 검증한다 (S15P11E102-311).

이 파일이 검증하는 완료 조건
    - 날씨·의료 질문의 "참고 자료"가 ctx["documents"] 에 실제로 담긴다
      (그래프를 태운 end-to-end 검증은 test_turn_end_to_end.py 참고)
    - 의료 판정(라우터 호출)이 한 턴에 한 번만 일어나고, context_read 는
      classify_intent 가 이미 계산한 값을 재사용한다
    - 조회 실패(API 에러 등)는 예외를 밖으로 던지지 않고, 지어내지 말라는
      지시가 담긴 "참고 자료"로 대체된다
    - 도시를 특정 못 하거나, 의료·일정·정서 표지가 아니거나, intent 가 이미
      info 가 아닌 것으로 정해졌으면 조회 자체를 시도하지 않는다

왜 핸들러가 아니라 context_read 를 직접 테스트하는가
    §23 은 핸들러의 직접 I/O 를 금지하고, 이 조회는 그 규칙 때문에 핸들러가
    아니라 context_read 로 올라왔다(CLAUDE.md §16 예산도 함께 걸려 있다).
    조회 여부·조합 규칙이 전부 이 노드 안에 있으므로, 노드 하나만 불러 검증할
    수 있다 — 그래프를 태우지 않고도 빠르게 반복할 수 있다는 뜻이다.

참고
    CLAUDE.md §6 (context_read 책임), §14 (날씨는 행동이다), §16 (생성 호출 1회),
    §23 (핸들러 직접 I/O 금지)
"""

from __future__ import annotations

import pytest

from bomi_ai_chat.backend_client import ContextResult
from bomi_ai_chat.graph import context as context_node

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def _reset_lazy_clients():
    """지연 생성 클라이언트를 테스트 사이에 새지 않게 한다."""
    yield
    context_node.set_client(None)
    context_node.set_weather_client(None)


class FakeContextClient:
    """백엔드 문맥 조회 대역. 이 파일에서는 문서 조회 여부에는 관심이 없다."""

    def __init__(self, ctx=None):
        self.ctx = ctx if ctx is not None else {}
        self.calls = 0

    def fetch_context(self, senior_id, **kwargs):
        self.calls += 1
        return ContextResult(ctx=dict(self.ctx), is_cached=False)


class FakeWeather:
    def __init__(self, forecast=None, error=None):
        self.forecast = forecast or {"기온": "18", "하늘상태": "1"}
        self.error = error
        self.calls: list[str] = []

    def get_forecast(self, city):
        self.calls.append(city)
        if self.error:
            raise self.error
        return self.forecast


def _turn(text: str, **overrides) -> dict:
    state = {"senior_id": SENIOR, "user_input": text}
    state.update(overrides)
    return state


# ─────────────────────────────────────────────────────────────────────────────
# 날씨 조회
# ─────────────────────────────────────────────────────────────────────────────


def test_weather_question_with_recognized_city_adds_a_reference_document():
    context_node.set_client(FakeContextClient())
    weather = FakeWeather({"기온": "22", "하늘상태": "1"})
    context_node.set_weather_client(weather)

    out = context_node.context_read(_turn("오늘 서울 날씨 어때"))

    assert weather.calls == ["서울"]
    documents = out["ctx"]["documents"]
    assert any("서울 날씨" in doc["title"] for doc in documents)
    assert any("22" in doc["content"] for doc in documents)


def test_local_weather_document_is_not_counted_as_a_corpus_hit():
    """로컬 도구 결과와 백엔드 문서 코퍼스 hit 수는 서로 다른 관측값이다."""
    context_node.set_client(FakeContextClient({
        "availability": {"semanticSearch": False, "documentCorpus": True},
        "documents": [],
    }))
    context_node.set_weather_client(FakeWeather({"기온": "22", "하늘상태": "1"}))

    out = context_node.context_read(_turn(
        "오늘 서울 날씨 어때", intent="info", is_medical_query=None))

    assert out["ctx"]["documents"], "날씨 도구 문서는 프롬프트에 남아야 한다"
    assert out["retrieval_status"]["documents_requested"] is True
    assert out["retrieval_status"]["document_hit_count"] == 0


def test_weather_question_without_a_city_skips_the_api_call_silently():
    """도시를 특정 못 하면 조회 자체를 안 한다 — legacy 경로와 같다.

    이것은 조회 '실패'가 아니라 정보 부족이므로, 완료 조건 5번의 "지어내지
    않는다" 처리(참고 자료로 감싸기) 대상이 아니다. 그냥 문서가 없다.
    """
    context_node.set_client(FakeContextClient())
    weather = FakeWeather()
    context_node.set_weather_client(weather)

    out = context_node.context_read(_turn("오늘 날씨 어때"))

    assert weather.calls == []
    assert not out["ctx"].get("documents")


def test_weather_lookup_failure_becomes_an_honest_reference_not_a_crash():
    """(완료 조건) 조회 실패는 지어내지 않고 솔직히 답하도록 지시한다."""
    context_node.set_client(FakeContextClient())
    context_node.set_weather_client(FakeWeather(error=RuntimeError("기상청 다운")))

    out = context_node.context_read(_turn("오늘 부산 날씨 어때"))

    documents = out["ctx"]["documents"]
    assert any(
        "확인이 어렵다" in doc["content"] or "지어내지" in doc["content"]
        for doc in documents
    )


# ─────────────────────────────────────────────────────────────────────────────
# 의료 조회 — 라우터는 항상 대역으로 바꾼다.
#
# 이 파일은 조회 호출 흐름에 집중한다. 의도 규칙의 정확도는 test_router.py가 맡고,
# 여기서는 context_node._is_medical 을 대역으로 바꿔 두 책임을 분리한다.
# ─────────────────────────────────────────────────────────────────────────────


def test_medical_question_adds_a_reference_document(monkeypatch):
    context_node.set_client(FakeContextClient())
    monkeypatch.setattr(context_node, "_is_medical", lambda text: True)
    monkeypatch.setattr(
        context_node, "handle_medical_query",
        lambda text: "서울대병원은 종로구에 있습니다.")

    out = context_node.context_read(_turn("근처 병원 어디야"))

    assert out["is_medical_query"] is True
    documents = out["ctx"]["documents"]
    assert any("서울대병원" in doc["content"] for doc in documents)


def test_medical_lookup_failure_becomes_an_honest_reference_not_a_crash(monkeypatch):
    """(완료 조건) 조회 실패(Gemini 다운 등)는 예외를 던지지 않고 솔직히 답한다."""
    context_node.set_client(FakeContextClient())
    monkeypatch.setattr(context_node, "_is_medical", lambda text: True)

    def boom(text):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(context_node, "handle_medical_query", boom)

    out = context_node.context_read(_turn("근처 병원 어디야"))

    documents = out["ctx"]["documents"]
    assert any(
        "확인이 어렵다" in doc["content"] or "지어내지" in doc["content"]
        for doc in documents
    )


def test_medical_determination_is_reused_by_context_read_in_the_same_turn(
    monkeypatch,
):
    """(완료 조건) 의료 판정은 한 턴에 한 번만 수행된다.

    classify_intent 가 라우터를 불러 판정한 결과를 state["is_medical_query"] 로
    남기면, context_read 는 그 값을 재사용해야 하며 라우터를 다시 불러서는 안
    된다. 여기서는 _is_medical 자체를 대역으로 바꿔 호출 횟수를 센다.
    """
    calls: list[str] = []

    def counting_router(text: str) -> bool:
        calls.append(text)
        return True

    context_node.set_client(FakeContextClient())
    monkeypatch.setattr(context_node, "_is_medical", counting_router)
    monkeypatch.setattr(
        context_node, "handle_medical_query", lambda text: "약국은 근처에 있습니다.")

    state = _turn("근처 약국 어디야")
    intent_out = context_node.classify_intent(state)
    assert intent_out == {"intent": "info", "is_medical_query": True}
    assert calls == ["근처 약국 어디야"], "classify_intent 가 라우터를 한 번만 불러야 한다"

    # LangGraph 가 노드 반환값을 state 에 병합하는 실제 순서로 이어 붙인다.
    context_node.context_read({**state, **intent_out})
    assert calls == ["근처 약국 어디야"], "context_read 가 라우터를 또 부르면 안 된다"


def test_medical_hint_routes_to_info_even_without_a_question_mark_or_info_marker(
    monkeypatch,
):
    """(회귀) "찾아줘"처럼 _INFO_MARKERS 에도 없고 물음표로도 안 끝나는 의료
    질문도 참고 자료가 실제로 쓰이는 info 로 가야 한다.

    실측 사고: "부산 강서구 정형외과 찾아줘."는 context_read._gather_lookup_documents
    가 (더 넓은 _MEDICAL_HINT_MARKERS 로) 이미 의료로 판정해 DB 조회까지 마쳤는데,
    classify_intent 의 예전 게이트(_INFO_MARKERS 매칭 또는 물음표로 끝남)를 통과
    못 해 companion 으로 빠졌다 — 조회는 됐는데 그 결과를 아무도 안 읽었다.
    """
    calls: list[str] = []

    def counting_router(text: str) -> bool:
        calls.append(text)
        return True

    context_node.set_client(FakeContextClient())
    monkeypatch.setattr(context_node, "_is_medical", counting_router)
    monkeypatch.setattr(
        context_node, "handle_medical_query", lambda text: "정형외과는 근처에 있습니다.")

    state = _turn("부산 강서구 정형외과 찾아줘.")
    intent_out = context_node.classify_intent(state)

    assert intent_out == {"intent": "info", "is_medical_query": True}
    context_out = context_node.context_read({**state, **intent_out})
    assert context_out["is_medical_query"] is True
    assert calls == ["부산 강서구 정형외과 찾아줘."], "라우터를 또 부르면 안 된다"


def test_medical_hint_gate_keeps_the_router_closed_for_ordinary_chatter(monkeypatch):
    """의료 관련 표지가 전혀 없는 잡담은 라우터를 아예 부르지 않는다.

    라우터 호출 자체가(모델 로딩 포함) 값싸지 않으므로, 힌트 없는 턴까지 매번
    부르면 그 비용을 아낄 이유가 사라진다.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        context_node, "_is_medical", lambda text: calls.append(text) or False)
    context_node.set_client(FakeContextClient())

    out = context_node.context_read(_turn("오늘 기분이 좋아요"))

    assert calls == []
    assert out["is_medical_query"] is None


def test_schedule_marker_wins_over_a_hospital_keyword(monkeypatch):
    """"병원 예약 있나"는 일정 조회이지, 병원 검색 조회가 아니다.

    _classify 의 우선순위(정서 > 일정 > 정보)와 어긋나면 안 된다 — 어긋나면
    "info 로는 스케줄로 분류되는데 조회는 의료로 나간다" 같은 모순이 생긴다.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        context_node, "_is_medical", lambda text: calls.append(text) or True)
    context_node.set_client(FakeContextClient())

    out = context_node.context_read(_turn("병원 예약 있나"))

    assert calls == []
    assert not out["ctx"].get("documents")


def test_already_classified_non_info_intent_skips_the_lookup(monkeypatch):
    """능동 턴이 이미 다른 인텐트를 확정했으면 조회를 새로 시도하지 않는다.

    백엔드가 내려보낸 인사 문구에 우연히 "날씨"가 들어 있다고 다시 기상청을
    부르면 낭비다(핸들러는 그 문구를 그대로 옮길 뿐, ctx 를 참고하지 않는다).
    """
    weather = FakeWeather()
    context_node.set_client(FakeContextClient())
    context_node.set_weather_client(weather)
    monkeypatch.setattr(
        context_node, "_is_medical", lambda text: (_ for _ in ()).throw(
            AssertionError("의료 라우터가 불려서는 안 된다")))

    out = context_node.context_read(
        _turn("오늘 날씨도 좋고 다녀오세요", intent="greeting"))

    assert weather.calls == []
    assert not out["ctx"].get("documents")
