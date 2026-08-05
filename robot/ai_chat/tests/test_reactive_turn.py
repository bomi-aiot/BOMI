"""반응형 1왕복 검증 — 문맥 조회, 인텐트 분류, 정제, 지연 실측.

이 파일이 검증하는 완료 조건
    - 백엔드 차단 상태에서도 캐시로 응답하고, 단정적 표현을 피하도록 표시된다
    - 턴 왕복 시간이 실측되어 로그로 남는다 (목표 policy.TURN_LATENCY_BUDGET_SEC)
    - 턴당 생성 LLM 호출이 1회다

참고
    CLAUDE.md §16 (지연 예산과 LLM 예산), §18 (오프라인)
"""

import logging

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client import BackendContextClient
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph import handlers, output
from bomi_ai_chat.localstore import context_cache, db
from bomi_ai_chat.turn_timer import TurnTimer

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


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._payload


class FakeSession:
    """백엔드를 끊고 붙일 수 있는 대역 세션."""

    def __init__(self, payload=None, *, online=True):
        self.payload = payload or {}
        self.online = online
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        if not self.online:
            raise ConnectionError("backend unreachable")
        return FakeResponse(self.payload)


class CountingLLM:
    """생성 호출 횟수를 센다. 턴당 1회 예산을 검증하는 수단이다."""

    def __init__(self, reply="네, 그러시군요"):
        self.reply = reply
        self.calls = 0
        self.last_prompt = None

    def generate(self, text, weather_data=None):
        self.calls += 1
        self.last_prompt = text
        return self.reply


# ── 문맥 조회와 캐시 폴백 ──────────────────────────────────────────────────


def test_successful_fetch_is_not_marked_cached(settings_factory):
    session = FakeSession({"profile": {"name": "김순자"}})
    client = BackendContextClient(settings=settings_factory(), session=session)

    result = client.fetch_context(SENIOR, query="안녕")

    assert result.is_cached is False
    assert result.ctx["profile"]["name"] == "김순자"


def test_offline_falls_back_to_cache_and_marks_it(settings_factory):
    """(완료 조건) 백엔드 차단 상태에서도 캐시로 응답한다."""
    payload = {"profile": {"name": "김순자"}}
    online = BackendContextClient(settings=settings_factory(), session=FakeSession(payload))
    online.fetch_context(SENIOR, query="안녕")  # 캐시를 채운다

    offline = BackendContextClient(
        settings=settings_factory(), session=FakeSession(online=False))
    result = offline.fetch_context(SENIOR, query="안녕")

    assert result.is_cached is True
    assert result.ctx["profile"]["name"] == "김순자"


def test_offline_without_cache_still_returns_instead_of_raising(settings_factory):
    """캐시조차 없어도 예외를 던지지 않는다.

    문맥 실패는 턴을 중단시키는 것이 아니라 저하시켜야 한다. 예외가 올라가면
    어르신 입장에서는 그냥 대답 없는 로봇이다.
    """
    client = BackendContextClient(settings=settings_factory(), session=FakeSession(online=False))

    result = client.fetch_context(SENIOR, query="안녕")

    assert result.ctx == {}
    assert result.is_cached is True


def test_corrupt_cache_is_treated_as_missing(settings_factory):
    """깨진 캐시에서 두 번 실패하지 않는다."""
    connection = db.runtime_db()
    from bomi_ai_chat.localstore import schema

    schema.init_runtime(connection)
    connection.execute(
        "INSERT INTO context_cache (senior_id, payload, cached_at) VALUES (?, ?, 0)",
        (SENIOR, "{not json"))

    assert context_cache.load(SENIOR) is None


def test_documents_requested_only_for_info_intent(settings_factory):
    """잡담에 문서를 검색하면 지연을 낭비하고 프롬프트를 오염시킨다."""
    session = FakeSession({})
    client = BackendContextClient(settings=settings_factory(), session=session)
    captured = {}

    def capture(method, url, **kwargs):
        captured.update(kwargs.get("json") or {})
        return FakeResponse({})

    session.request = capture

    client.fetch_context(SENIOR, query="복지제도", documents=True)
    assert captured["includeDocuments"] is True

    client.fetch_context(SENIOR, query="심심해", documents=False)
    assert captured["includeDocuments"] is False


# ── 인텐트 분류: 로컬 규칙, LLM 왕복 없음 ─────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("오늘 며칠이야", "info"),
        ("지금 몇 시야", "info"),
        ("날씨 알려줘", "info"),
        ("약 먹었어", "schedule"),
        ("병원 예약 있나", "schedule"),
        ("요즘 너무 외로워", "emotional"),
        ("영감이 보고 싶네", "emotional"),
        ("그냥 이런저런 얘기나 하자", "companion"),
    ],
)
def test_intent_is_classified_by_local_rules(text, expected):
    assert context_node.classify_intent({"user_input": text}) == {"intent": expected}


def test_emotional_wins_over_information():
    """"외로운데 오늘 며칠이야"는 날짜를 알려주는 턴이 아니라 들어야 하는 턴이다.

    정보로 처리하면 사람이 아니라 검색창처럼 반응하게 된다.
    """
    assert context_node.classify_intent(
        {"user_input": "외로운데 오늘 며칠이야"}) == {"intent": "emotional"}


def test_existing_intent_is_not_reclassified():
    """게이트가 이긴 제안에서 인텐트가 이미 붙어 오면 그대로 둔다."""
    assert context_node.classify_intent({"intent": "greeting", "user_input": "안녕"}) == {}


def test_default_intent_is_companion_not_info():
    """기본값이 정보 제공이 아니라 대화인 것은 의도된 선택이다.

    외로움이 1번 문제이고 말벗이 본체다 (CLAUDE.md §1).
    """
    assert context_node.classify_intent({"user_input": "음"}) == {"intent": "companion"}


def _fake_medical_router(monkeypatch, is_medical):
    """실제 SentenceTransformer 모델을 로드하지 않고 의료 판정 결과만 흉내낸다.

    router.py 는 모듈을 불러오는 순간(import 시점) 임베딩 모델을 통째로 메모리에
    올린다. 유닛 테스트에서 그걸 그대로 하면 느리고, 모델이 캐시되어 있지 않은
    CI 환경에서는 네트워크까지 필요해진다. 그래서 sys.modules 에 가짜 모듈을
    먼저 꽂아 둔다 — context._is_medical 은 "from bomi_ai_chat.llm import router"를
    호출 시점에 매번 다시 하므로, 이미 꽂혀 있는 가짜를 그대로 집어 온다
    (test_medical_pipeline_safety.py 와 같은 패턴).
    """
    import sys
    from types import ModuleType

    fake_router = ModuleType("bomi_ai_chat.llm.router")
    fake_router.is_medical_query = lambda text: is_medical
    monkeypatch.setitem(sys.modules, "bomi_ai_chat.llm.router", fake_router)


def test_medical_question_routes_to_medical_not_info(monkeypatch):
    """병원/약국/의약품 질문은 "info"가 아니라 "medical"로 분류된다.

    "info"로 남아 있으면 handle_info(일반 LLM 생성)로 가서 DB를 안 거치고, 병원
    주소를 근거 없이 지어낼 위험이 생긴다(CLAUDE.md §8).
    """
    _fake_medical_router(monkeypatch, is_medical=True)

    assert context_node.classify_intent(
        {"user_input": "이 약 먹어도 되나요?"}) == {"intent": "medical"}


def test_non_medical_question_still_falls_back_to_companion(monkeypatch):
    """의료 판정기가 아니라고 하면(=False) 여전히 잡담으로 남는다."""
    _fake_medical_router(monkeypatch, is_medical=False)

    assert context_node.classify_intent(
        {"user_input": "오늘 기분이 어떠세요?"}) == {"intent": "companion"}


def test_medical_statement_without_question_mark_also_routes_to_medical(monkeypatch):
    """물음표 없이 평서형으로 끝나도 의료 판정기가 불려야 한다.

    예전에는 문장이 "까요/나요/가요/...?" 로 끝날 때만 판정기(_is_medical)를 불렀다.
    하지만 어르신 발화는 "궁금하네." 처럼 평서형으로 끝나는 경우가 흔하고, STT가
    억양만으로 물음표를 못 살리는 경우도 많다 — 그때는 판정기를 부르지도 못하고
    그냥 말벗으로 빠졌었다.
    """
    _fake_medical_router(monkeypatch, is_medical=True)

    assert context_node.classify_intent(
        {"user_input": "타이레놀 있는지 궁금하네."}) == {"intent": "medical"}


def test_medical_question_via_ambiguous_marker_still_routes_to_medical(monkeypatch):
    """"알려줘"/"어디야" 표지에 걸려도 의료 질문이면 info가 아니라 medical로 간다.

    실제로 "부산에 있는 병원 알려줘"가 이 표지에 먼저 걸려 곧장 info로 새는 사고가
    있었다 — handle_info(일반 LLM 생성)로 가서 DB 조회를 통째로 건너뛰었다.
    """
    _fake_medical_router(monkeypatch, is_medical=True)

    assert context_node.classify_intent(
        {"user_input": "부산에 있는 병원 알려줘"}) == {"intent": "medical"}


def test_ambiguous_marker_still_falls_back_to_info_when_not_medical(monkeypatch):
    """같은 표지("어디야")라도 의료 판정기가 아니라고 하면 여전히 info로 간다."""
    _fake_medical_router(monkeypatch, is_medical=False)

    assert context_node.classify_intent(
        {"user_input": "우리 아들 지금 어디야"}) == {"intent": "info"}


# 실제로 companion 으로 샜던 발화들. 전부 특정 기관명/시설 유형만 담고 있어서
# 임베딩 판정기(_is_medical)가 자주 놓쳤다 — _MEDICAL_FACILITY_MARKERS 는
# 문자열 포함만으로 판정하므로 router 를 가짜로 바꿀 필요가 없다(결정적이라
# _is_medical 를 아예 안 부른다).
@pytest.mark.parametrize(
    "text",
    [
        "서울대병원이 어디 있는지 알고 싶어",
        "행복약국 좀 찾아줘야겠어",
        "부산 강서구 병원 찾아줘",
        "남경의원 더 자세히 알려줘",
    ],
)
def test_facility_name_only_phrasings_route_to_medical(text):
    assert context_node.classify_intent({"user_input": text}) == {"intent": "medical"}


def test_facility_marker_does_not_override_schedule():
    """"병원 예약" 같은 일정 처리 표현은 여전히 schedule로 간다."""
    assert context_node.classify_intent(
        {"user_input": "다음 주에 병원 예약 있어"}) == {"intent": "schedule"}


def test_facility_marker_survives_stt_splitting_the_word():
    """STT가 "남경의원"을 "남경의 원"처럼 단어 중간에 공백을 넣어도 잡힌다.

    실제 로그에서 확인된 STT 출력이다. 표지("의원")가 원문에서 공백으로 갈라지면
    예전에는 부분 문자열 매칭이 깨져 companion/info 로 샜다.
    """
    assert context_node.classify_intent(
        {"user_input": "남경의 원 자세히 알려줘."}) == {"intent": "medical"}


def test_schedule_marker_still_needs_its_space():
    """공백 제거는 시설 표지에만 적용된다 — "약 먹었"처럼 공백이 의미를 가르는
    표지까지 뭉개면 안 된다."""
    assert context_node.classify_intent(
        {"user_input": "저녁 약 먹었어"}) == {"intent": "schedule"}


# ── 핸들러: 턴당 생성 호출 1회 ─────────────────────────────────────────────


def test_handler_makes_exactly_one_generation_call():
    """(LLM 예산) 턴당 생성 호출은 1회다.

    왕복 하나가 500~1500ms 이고 턴 전체 예산이 약 2초다 (CLAUDE.md §16).
    """
    llm = CountingLLM()
    handlers.set_llm(llm)

    handlers.handle_companion({"ctx": {}, "intent": "companion", "user_input": "안녕"})

    assert llm.calls == 1


def test_handler_prompt_carries_the_cached_warning():
    """캐시로 답하는 턴이면 프롬프트에 단정 금지가 실린다."""
    llm = CountingLLM()
    handlers.set_llm(llm)

    handlers.handle_info(
        {"ctx": {}, "intent": "info", "user_input": "내 약 뭐야", "ctx_is_cached": True})

    assert "단정적으로" in llm.last_prompt


def test_generation_failure_degrades_instead_of_raising():
    """생성이 실패해도 되묻는 문장으로 답한다. 침묵이 아니다.

    어르신은 방금 말을 걸었다. 아무 반응이 없으면 고장 난 기계다.
    """
    class BrokenLLM:
        def generate(self, text, weather_data=None):
            raise RuntimeError("gemini down")

    handlers.set_llm(BrokenLLM())

    result = handlers.handle_companion({"ctx": {}, "intent": "companion", "user_input": "안녕"})

    assert result["response"]
    assert "다시" in result["response"]


# ── 핸들러: 의료(병원·약국·의약품) DB 조회 ──────────────────────────────────


def test_handle_medical_delegates_to_medical_flow(monkeypatch):
    """handle_medical 은 자기가 문장을 짓지 않고 medical_flow 결과를 그대로 쓴다."""
    from bomi_ai_chat.llm import medical_flow

    monkeypatch.setattr(
        medical_flow, "handle_medical_query", lambda text: f"[DB 조회 결과] {text}")

    result = handlers.handle_medical({"user_input": "행복약국 어디야"})

    assert result == {"response": "[DB 조회 결과] 행복약국 어디야"}


def test_handle_medical_falls_back_on_unexpected_error(monkeypatch, caplog):
    """medical_flow 가 예상 못한 예외를 던져도 침묵 대신 되묻는 문장을 낸다.

    medical_flow 자체가 흔한 실패(DB 오류·시설 못 찾음)는 이미 안내 문장으로
    처리하므로, 여기서 잡는 예외는 그 밖의 진짜 버그다.
    """
    from bomi_ai_chat.llm import medical_flow

    def boom(text):
        raise RuntimeError("예상 못한 실패")

    monkeypatch.setattr(medical_flow, "handle_medical_query", boom)

    with caplog.at_level(logging.WARNING):
        result = handlers.handle_medical({"user_input": "타이레놀 있어?"})

    assert result["response"] == handlers._FALLBACK_RESPONSE
    assert any("medical query failed" in record.message for record in caplog.records)


# ── 출력 정제 ──────────────────────────────────────────────────────────────


def test_korean_sentences_split_without_trailing_punctuation():
    """한국어는 종결 부호가 빠지는 경우가 흔하다. 종결어미도 경계로 본다."""
    sentences = output.split_sentences("점심 드셨어요 오늘 날씨가 좋네요")

    assert len(sentences) == 2


def test_decimal_numbers_are_not_split():
    """"3.5도"를 "3." 과 "5도"로 쪼개면 로봇이 이상하게 말한다."""
    sentences = output.split_sentences("기온은 3.5도입니다. 따뜻하게 입으세요.")

    assert "3.5도입니다." in sentences[0]


def test_shaper_truncates_and_warns(caplog):
    """절단은 안전망이고, 일어나면 로그로 남는다.

    그 로그가 곧 "프롬프트를 고쳐야 한다"는 신호다. 절단은 중요한 절반을 날릴 수 있다.
    """
    long_text = "첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다."

    with caplog.at_level(logging.WARNING):
        result = output.response_shaper({"response": long_text})

    assert len(result["sentences"]) == policy.MAX_SENTENCES
    assert any("truncated" in record.message for record in caplog.records)


def test_terse_shaping_is_shorter():
    text = "어서 오세요. 오늘 하루 어떠셨어요."

    normal = output.response_shaper({"response": text})
    terse = output.response_shaper({"response": text, "terse": True})

    assert len(terse["sentences"]) == policy.MAX_SENTENCES_TERSE
    assert len(normal["sentences"]) >= len(terse["sentences"])


# ── emit: 비블로킹 ─────────────────────────────────────────────────────────


def test_emit_does_not_block_and_hands_sentences_one_by_one():
    """emit 은 재생 시작만 하고 즉시 반환한다.

    여기서 블로킹하면 말하는 동안 어르신의 끼어들기를 아무도 관찰하지 못해서
    양보 우선 정책이 원리적으로 불가능해진다 (CLAUDE.md §13).
    """
    class FakePlayer:
        def __init__(self):
            self.received = None

        def speak_async(self, sentences):
            self.received = list(sentences)
            return "handle-1"

    player = FakePlayer()
    output.set_player(player)

    result = output.emit({"senior_id": SENIOR, "sentences": ["첫 문장", "둘째 문장"]})

    assert result["speaking"] is True
    assert player.received == ["첫 문장", "둘째 문장"]
    assert output.TTS_HANDLES[SENIOR] == "handle-1"


def test_emit_without_sentences_does_not_claim_to_be_speaking():
    """할 말이 없으면 speaking=True 로 두지 않는다.

    두면 barge-in 로직이 존재하지 않는 재생을 끊으려 든다.
    """
    assert output.emit({"senior_id": SENIOR, "sentences": []})["speaking"] is False


# ── 지연 실측 ──────────────────────────────────────────────────────────────


def test_turn_timer_logs_breakdown_within_budget(caplog):
    """(완료 조건) 턴 왕복 시간이 실측되어 로그로 남는다."""
    ticks = iter([0.0, 0.0, 0.2, 0.25])
    timer = TurnTimer(monotonic=lambda: next(ticks))

    with timer.stage("graph"):
        pass

    with caplog.at_level(logging.INFO):
        total = timer.finish(senior_id=SENIOR, intent="companion")

    assert total == pytest.approx(0.25)
    assert any("turn latency" in record.message for record in caplog.records)
    assert any("graph=" in record.getMessage() for record in caplog.records)


def test_turn_timer_warns_when_budget_exceeded(caplog):
    """예산 초과는 WARNING 이다. INFO 로 두면 아무도 안 본다."""
    over = policy.TURN_LATENCY_BUDGET_SEC + 1.0
    ticks = iter([0.0, over])
    timer = TurnTimer(monotonic=lambda: next(ticks))

    with caplog.at_level(logging.INFO):
        timer.finish(senior_id=SENIOR, intent="info")

    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_turn_timer_records_stage_even_when_it_raises():
    """실패한 단계야말로 우리가 보고 싶은 단계다."""
    ticks = iter([0.0, 0.0, 3.0, 3.0])
    timer = TurnTimer(monotonic=lambda: next(ticks))

    with pytest.raises(RuntimeError), timer.stage("graph"):
        raise RuntimeError("boom")

    assert timer.stages["graph"] == pytest.approx(3.0)
