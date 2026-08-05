"""그래프를 실제로 컴파일해 한 턴을 끝까지 돌린다.

이 파일이 검증하는 완료 조건
    STT 텍스트 -> 그래프 -> TTS 왕복. 외부 API(STT·LLM·TTS)와 오디오 장치는 대역으로
    바꾼다. 그 셋은 이미 검증된 기존 클라이언트이고, 이 티켓이 새로 만든 것은
    '그 사이를 잇는 판단 경로'다.

여기서 검증하지 '못하는' 것
    실제 마이크·스피커·외부 API 를 쓴 실기 왕복. 오디오 장치와 API 키가 필요하다.
    실기 확인은 205 번(에코 억제)에서 하드웨어와 함께 이뤄져야 한다.

참고
    CLAUDE.md §6 (진입 경로), §22 2단계
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client import ContextResult
from bomi_ai_chat.graph import build, handlers, output
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph.build import build_graph
from bomi_ai_chat.graph.turn import run_user_turn
from bomi_ai_chat.localstore import db
from bomi_ai_chat.turn_timer import TurnTimer

SENIOR = "senior-1"


class FakeContextClient:
    """백엔드 대역. online=False 로 두면 캐시 폴백 경로를 흉내낸다."""

    def __init__(self, ctx=None, *, is_cached=False):
        self.ctx = ctx if ctx is not None else {"profile": {"preferredName": "순자님"}}
        self.is_cached = is_cached
        self.calls = 0
        # 이번 턴이 fetch_context 에 실어 보낸 conversation_id 를 순서대로 기록한다.
        # S15P11E102-306 의 완료 조건("2턴째부터 conversation_id 가 실린다")을
        # 검증하는 유일한 창구다.
        self.received_conversation_ids: list[str | None] = []
        self.received_documents: list[bool] = []

    def fetch_context(self, senior_id, **kwargs):
        self.calls += 1
        self.received_conversation_ids.append(kwargs.get("conversation_id"))
        self.received_documents.append(bool(kwargs.get("documents")))
        return ContextResult(ctx=self.ctx, is_cached=self.is_cached)


class FakeLLM:
    def __init__(self, reply="무릎이 많이 불편하시겠어요. 오늘은 좀 어떠세요?"):
        self.reply = reply
        self.calls = 0
        self.prompts = []

    def generate(self, text, weather_data=None):
        self.calls += 1
        self.prompts.append(text)
        return self.reply


class FakeHandle:
    """재생 핸들 대역.

    205 에서 핸들이 barge-in 복구의 권위가 되면서 계약이 생겼다.
    cancel() 로 멈출 수 있고, remaining_sentences() 로 못 한 말을 알려줘야 하며,
    is_done 으로 재생이 끝났는지 답해야 한다(감사 결함 B1 수정이 이 값을 본다).
    이 대역은 '즉시 전부 말한 것'으로 치므로 is_done 도 항상 True 다 — 그래서
    다음 턴의 note_interaction 이 실기와 똑같이 '평범한 턴'으로 진행한다.
    """

    def __init__(self, sentences):
        self.sentences = list(sentences)
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def remaining_sentences(self):
        # 이 대역은 즉시 전부 말한 것으로 친다.
        return []

    @property
    def is_done(self) -> bool:
        # 즉시 전부 말했으므로 항상 끝난 상태다.
        return True


class FakePlayer:
    def __init__(self):
        self.spoken = []

    def speak_async(self, sentences):
        self.spoken.append(list(sentences))
        return FakeHandle(sentences)


class FakeConversationClient:
    """대화 적재 대역. 올라간 턴을 순서대로 모은다.

    순서를 보존하는 것이 중요하다 — 서버가 올라온 순서로 순번을 매기므로,
    로봇이 로봇 발화를 먼저 올리면 기록상 로봇이 먼저 말한 것이 된다.

    ★ 서버와 같은 계약을 흉내낸다 (S15P11E102-306)
        conversation_id 가 None 으로 들어오면 "새 대화"로 보고 새 id 를 발급한다.
        값이 이미 있으면 그대로 에코한다 — 실제 서버가 하는 일과 같다.

        예전 대역은 호출마다 무조건 "conversation-1"을 돌려줬다. 그러면 turn.py 가
        매 턴 conversation_id=None 을 무조건 흘려보내는 결함이 있어도 겉보기 대화는
        계속 이어지는 것처럼 보여서, 테스트가 그 결함을 가리는 함정이었다. 여기서
        같은 함정을 다시 만들지 않는다.
    """

    def __init__(self):
        self.turns = []
        self._next_conversation_id = 1
        self._next_message_id = 1

    def record_turn(self, senior_id, **fields):
        self.turns.append({"seniorId": senior_id, **fields})

        conversation_id = fields.get("conversation_id")
        if conversation_id is None:
            conversation_id = f"conversation-{self._next_conversation_id}"
            self._next_conversation_id += 1

        message_id = f"message-{self._next_message_id}"
        self._next_message_id += 1
        return conversation_id, message_id


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """그래프 주변의 외부 의존을 전부 대역으로 바꾼다."""
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()

    client = FakeContextClient()
    llm = FakeLLM()
    player = FakePlayer()
    conversations = FakeConversationClient()
    context_node.set_client(client)
    handlers.set_llm(llm)
    output.set_player(player)
    build.set_conversation_client(conversations)

    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))
    yield app, client, llm, player

    context_node.set_client(None)
    handlers.set_llm(None)
    output.set_player(None)
    build.set_conversation_client(None)
    db.close_all()


def test_user_utterance_completes_a_full_turn(wired):
    """(완료 조건) 발화 한 번이 문맥 조회 -> 생성 -> 정제 -> 재생까지 간다."""
    app, client, llm, player = wired

    state = run_user_turn(app, SENIOR, "무릎이 아파")

    assert client.calls == 1, "문맥을 한 번 조회해야 한다"
    assert llm.calls == 1, "턴당 생성 호출은 1회다"
    assert state["final_utterance"]
    assert player.spoken, "재생이 시작되어야 한다"


def test_turn_makes_exactly_one_generation_call(wired):
    """LLM 예산: 트리아지·인텐트 분류가 왕복을 추가하지 않는다."""
    app, _client, llm, _player = wired

    run_user_turn(app, SENIOR, "오늘 며칠이야")

    assert llm.calls == 1


def test_prompt_receives_context_from_backend(wired):
    """조회한 문맥이 실제로 프롬프트에 실린다."""
    app, _client, llm, _player = wired

    run_user_turn(app, SENIOR, "안녕하세요")

    assert "순자님" in llm.prompts[0]


def test_information_turn_requests_documents_and_preserves_retrieval_evidence(wired):
    """정보 분류→문서 요청→근거·검색 상태→프롬프트가 한 턴에서 이어진다."""
    app, _client, llm, _player = wired
    client = FakeContextClient({
        "documents": [{
            "title": "노인맞춤돌봄서비스",
            "content": "만 65세 이상 신청할 수 있습니다.",
            "source": "보건복지부",
            "version": "2026-07",
            "chunkId": "welfare-001#eligibility",
            "citation": "사업안내 12쪽",
        }],
        "availability": {
            "semanticSearch": False,
            "documentCorpus": True,
            "notes": ["semantic search unavailable"],
        },
        "retrieval": {
            "semanticRequested": True,
            "semanticUsed": False,
            "fallbackReason": "embedding_disabled",
            "hitCount": 0,
            "latencyMs": 7,
            "embeddingLatencyMs": 3,
            "vectorSearchLatencyMs": 4,
        },
    })
    context_node.set_client(client)

    timer = TurnTimer()
    state = run_user_turn(app, SENIOR, "복지제도 알려줘", timer=timer)

    assert state["intent"] == "info"
    assert client.received_documents == [True]
    assert state["retrieval_status"] == {
        "source": "backend",
        "documents_requested": True,
        "document_hit_count": 1,
        "semantic_available": False,
        "document_corpus_available": True,
        "semantic_requested": True,
        "semantic_used": False,
        "fallback_reason": "embedding_disabled",
        "hit_count": 0,
        "latency_ms": 7,
        "embedding_latency_ms": 3,
        "vector_search_latency_ms": 4,
        "notes": ["semantic search unavailable"],
    }
    assert {"context", "embedding", "vector_search", "llm", "tts_dispatch"} <= timer.stages.keys()
    assert timer.stages["embedding"] == pytest.approx(0.003)
    assert timer.stages["vector_search"] == pytest.approx(0.004)
    prompt = llm.prompts[0]
    assert "노인맞춤돌봄서비스" in prompt
    assert "출처=보건복지부" in prompt
    assert "버전=2026-07" in prompt
    assert "청크=welfare-001#eligibility" in prompt
    assert "인용=사업안내 12쪽" in prompt
    assert "의미 기반 기억 검색을 사용할 수 없습니다" in prompt


def test_cached_context_marks_the_turn(wired, monkeypatch, tmp_path):
    """백엔드가 막혀 캐시로 답하면 프롬프트에 단정 금지가 실린다."""
    app, _client, llm, _player = wired
    context_node.set_client(
        FakeContextClient({"profile": {"preferredName": "순자님"}}, is_cached=True))

    run_user_turn(app, SENIOR, "내 약 뭐야")

    assert "단정적으로" in llm.prompts[0]


def test_response_is_split_into_speakable_sentences(wired):
    """정제를 거치지 않고 스피커에 도달하는 것은 없다."""
    app, _client, _llm, player = wired

    state = run_user_turn(app, SENIOR, "무릎이 아파")

    assert state["sentences"], "문장으로 쪼개져야 한다"
    assert player.spoken[0] == state["sentences"]


def test_turn_survives_a_broken_llm(wired):
    """생성이 실패해도 턴이 끝나고 무언가 말한다.

    한 턴의 실패가 입력 루프를 죽이면 로봇이 그대로 멈춘다.
    """
    app, _client, _llm, player = wired

    class BrokenLLM:
        def generate(self, text, weather_data=None):
            raise RuntimeError("gemini down")

    handlers.set_llm(BrokenLLM())

    state = run_user_turn(app, SENIOR, "안녕")

    assert state["final_utterance"]
    assert player.spoken


def test_state_persists_across_turns(wired):
    """checkpointer 가 thread_id(어르신 id)별로 상태를 잇는다."""
    app, _client, _llm, _player = wired

    run_user_turn(app, SENIOR, "안녕하세요")
    second = run_user_turn(app, SENIOR, "무릎이 아파")

    # messages 는 add_messages 로 누적된다. 두 번째 턴에서 첫 턴의 흔적이 보여야 한다.
    assert second.get("last_user_interaction_at") is not None


def test_intent_is_reclassified_every_reactive_turn(wired):
    """(회귀) 첫 턴의 분류가 다음 턴까지 얼어붙지 않는다.

    checkpointer 는 thread_id(어르신 id)별로 이전 턴의 state 전체를 다음 턴에도
    그대로 넘긴다. note_interaction 이 intent 를 지우지 않으면, classify_intent
    의 "if state.get('intent'): return {}" 가드가 지난 턴 값을 "이미 분류됨"으로
    착각해 재분류를 건너뛴다 — 실기에서 첫 질문이 companion 이 되고 나면 그 뒤로
    뭘 물어도 계속 companion 으로만 답하는 사고로 이어졌다.
    """
    app, _client, _llm, _player = wired

    first = run_user_turn(app, SENIOR, "그냥 이런저런 얘기나 하자")
    assert first["intent"] == "companion"

    second = run_user_turn(app, SENIOR, "요즘 너무 외로워")
    assert second["intent"] == "emotional"


# ── 대화 연속성 (S15P11E102-306) ────────────────────────────────────────────
#
# graph/turn.py 가 conversation_id 를 매 턴 무조건 None 으로 덮어써서, 실런타임에서는
# 모든 발화가 새 conversation 행을 만들던 결함의 회귀 테스트. 아래 네 개가 티켓의
# 완료 조건과 1:1 로 대응한다.


def test_three_turns_stay_in_one_conversation(wired):
    """(완료 조건) 3턴을 돌려도 서버가 발급한 대화는 하나이고,
    2턴째 SENIOR 행의 conversation_id 는 비어 있지 않다."""
    app, _client, _llm, _player = wired

    run_user_turn(app, SENIOR, "안녕하세요")
    second = run_user_turn(app, SENIOR, "오늘 뭐 했어")
    run_user_turn(app, SENIOR, "졸리다")

    conversations = build._conversation_client()
    # 대역이 "새 대화"로 판단해 실제로 새 id 를 발급한 횟수. 세 턴이 한 대화로
    # 이어졌다면 이 값은 정확히 1 이어야 한다(첫 턴에서 딱 한 번).
    assert conversations._next_conversation_id - 1 == 1

    senior_rows = [turn for turn in conversations.turns if turn["role"] == "SENIOR"]
    assert len(senior_rows) == 3
    assert senior_rows[1]["conversation_id"] is not None, (
        "2턴째부터는 1턴째가 받은 conversation_id 를 실어 보내야 한다"
    )
    assert second["conversation_id"] == senior_rows[1]["conversation_id"]


def test_fetch_context_carries_conversation_id_from_the_second_turn(wired):
    """(완료 조건) fetch_context 가 2턴째부터 null 이 아닌 conversation_id 를 싣는다."""
    app, client, _llm, _player = wired

    run_user_turn(app, SENIOR, "안녕하세요")
    run_user_turn(app, SENIOR, "오늘 뭐 했어")

    assert client.received_conversation_ids[0] is None, "첫 턴은 아직 대화가 없다"
    assert client.received_conversation_ids[1] is not None


def test_idle_gap_past_the_boundary_opens_a_new_conversation(wired, frozen_clock):
    """(완료 조건) 유휴 임계값을 넘긴 뒤의 발화는 새 대화로 연다 (압축 시계로 검증)."""
    app, _client, _llm, _player = wired
    sim = frozen_clock(start=1_700_000_000.0)

    first = run_user_turn(app, SENIOR, "안녕하세요")
    assert first["conversation_id"]

    sim.advance(policy.CONVERSATION_BOUNDARY_IDLE_SEC + 1)

    second = run_user_turn(app, SENIOR, "오랜만이에요")

    assert second["conversation_id"] != first["conversation_id"]


def test_idle_gap_under_the_boundary_keeps_the_same_conversation(wired, frozen_clock):
    """대비 사례: 임계값 '밑'이면 그대로 이어 붙어야 한다."""
    app, _client, _llm, _player = wired
    sim = frozen_clock(start=1_700_000_000.0)

    first = run_user_turn(app, SENIOR, "안녕하세요")
    sim.advance(policy.CONVERSATION_BOUNDARY_IDLE_SEC - 1)
    second = run_user_turn(app, SENIOR, "밥은 먹었어")

    assert second["conversation_id"] == first["conversation_id"]


def test_record_turn_returns_a_message_id_for_the_senior_row(wired):
    """(완료 조건) record_turn 이 messageId 를 돌려주고 state 에 남는다.

    255 번의 fact_candidate 추출이 FactCandidate.fromConversationMessage 의
    sourceMessageId 로 이 값을 요구한다.
    """
    app, _client, _llm, _player = wired

    state = run_user_turn(app, SENIOR, "무릎이 아파")

    assert state["last_message_id"]


# ─────────────────────────────────────────────────────────────────────────────
# 사실 추출 큐잉 (S15P11E102-255)
# ─────────────────────────────────────────────────────────────────────────────


def test_a_memorable_utterance_queues_one_extraction_job_without_extra_llm_calls(wired):
    """(완료 조건) "요즘 손자가 자주 놀러 와요" 뒤 큐에 1행, 생성 호출은 여전히 1회.

    큐잉(graph/build.py._enqueue_extraction)은 LLM 을 부르지 않는다 — 실제
    추출은 jobs/ticks.extraction_flush 가 턴 밖에서 한다(CLAUDE.md §16).
    """
    from bomi_ai_chat.localstore import extraction

    app, _client, llm, _player = wired

    run_user_turn(app, SENIOR, "요즘 손자가 자주 놀러 와요")

    assert llm.calls == 1
    assert extraction.pending_count(SENIOR) == 1
    assert extraction.pending()[0]["content"] == "요즘 손자가 자주 놀러 와요"


def test_a_short_backchannel_like_reply_does_not_queue_an_extraction_job(wired):
    from bomi_ai_chat.localstore import extraction

    app, _client, _llm, _player = wired

    run_user_turn(app, SENIOR, "네")

    assert extraction.pending_count(SENIOR) == 0


# ─────────────────────────────────────────────────────────────────────────────
# emit 이 memory_write 의 블로킹 호출보다 먼저 일어난다 (S15P11E102-255)
# ─────────────────────────────────────────────────────────────────────────────


class OrderTrackingConversationClient(FakeConversationClient):
    """record_turn 호출 순서를 공유 리스트에 남기는 대역."""

    def __init__(self, events: list[str]):
        super().__init__()
        self._events = events

    def record_turn(self, senior_id, **fields):
        self._events.append(f"record:{fields.get('role')}")
        return super().record_turn(senior_id, **fields)


class OrderTrackingPlayer(FakePlayer):
    """speak_async 호출 순서를 공유 리스트에 남기는 대역."""

    def __init__(self, events: list[str]):
        super().__init__()
        self._events = events

    def speak_async(self, sentences):
        self._events.append("speak")
        return super().speak_async(sentences)


def test_speaking_starts_before_the_blocking_conversation_record_call(
    monkeypatch, tmp_path,
):
    """(완료 조건) 재생 시작이 대화 적재(블로킹 HTTP)보다 먼저 일어난다.

    순서가 뒤집혀 있으면 T1 확인 응답조차 record_turn 의 HTTP 왕복을 다 기다린
    뒤에야 말하기 시작한다 — 응급 응답이 통계성 기록 뒤에 줄을 서는 것과 같다
    (graph/build.py 의 엣지 재배선 참고).
    """
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()

    events: list[str] = []
    client = FakeContextClient()
    llm = FakeLLM()
    player = OrderTrackingPlayer(events)
    conversations = OrderTrackingConversationClient(events)
    context_node.set_client(client)
    handlers.set_llm(llm)
    output.set_player(player)
    build.set_conversation_client(conversations)

    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))
    try:
        run_user_turn(app, SENIOR, "무릎이 아파")
    finally:
        context_node.set_client(None)
        handlers.set_llm(None)
        output.set_player(None)
        build.set_conversation_client(None)
        db.close_all()

    assert "speak" in events
    assert events.index("speak") < events.index("record:ROBOT")


# ─────────────────────────────────────────────────────────────────────────────
# 날씨·의료 조회 — context_read 에서 그래프를 태워 확인한다 (S15P11E102-311)
#
# 이 절만 build_prompt() 를 직접 부르지 않고 app.invoke 로 전체 그래프를
# 돌린다. 완료 조건이 "그래프를 태워서" 확인하라고 명시했다 — context_read 가
# 채운 ctx["documents"] 가 실제로 handle_info -> build_prompt 까지 살아서
# 도착하는지는 노드 하나만 불러서는 보증할 수 없기 때문이다.
# ─────────────────────────────────────────────────────────────────────────────


class FakeWeather:
    """weather/client.WeatherClient 대역. 도시별 조회 결과나 실패를 흉내낸다."""

    def __init__(self, forecast=None, error=None):
        self.forecast = forecast or {"기온": "20", "하늘상태": "1"}
        self.error = error
        self.calls: list[str] = []

    def get_forecast(self, city):
        self.calls.append(city)
        if self.error:
            raise self.error
        return self.forecast


def test_weather_question_makes_exactly_one_generation_call(wired):
    """(완료 조건) 날씨 질문 1턴에서 생성 LLM 호출이 1회로 유지된다.

    조회(기상청 API) 자체는 LLM 호출이 아니다. handle_info._generate() 가
    부르는 한 번이 이 턴의 유일한 생성 호출이어야 한다(CLAUDE.md §16).
    """
    app, _client, llm, _player = wired
    weather = FakeWeather({"기온": "22", "하늘상태": "1"})
    context_node.set_weather_client(weather)
    try:
        run_user_turn(app, SENIOR, "오늘 서울 날씨 어때")
    finally:
        context_node.set_weather_client(None)

    assert weather.calls == ["서울"]
    assert llm.calls == 1, "조회가 늘어도 생성 호출은 여전히 1회여야 한다"


def test_weather_question_renders_reference_material_in_the_prompt(wired):
    """(완료 조건) 날씨 질문의 프롬프트에 '참고 자료' 섹션이 실제로 렌더된다.

    build_prompt() 를 직접 부르는 것이 아니라 app.invoke 로 그래프를 태워
    확인한다 — context_read 가 채운 문서가 handle_info 까지 실제로 전달되는지
    보려면 그 경로 전체가 살아 있어야 한다.
    """
    app, _client, llm, _player = wired
    context_node.set_weather_client(FakeWeather({"기온": "22", "하늘상태": "1"}))
    try:
        run_user_turn(app, SENIOR, "오늘 서울 날씨 어때")
    finally:
        context_node.set_weather_client(None)

    assert "참고 자료" in llm.prompts[0]
    assert "서울" in llm.prompts[0]
    assert "22" in llm.prompts[0]


def test_weather_lookup_failure_leads_to_an_honest_reply_not_fabrication(wired):
    """(완료 조건) 조회 실패는 지어내지 않고 솔직히 답하도록 지시한다."""
    app, _client, llm, _player = wired
    context_node.set_weather_client(FakeWeather(error=RuntimeError("기상청 다운")))
    try:
        state = run_user_turn(app, SENIOR, "오늘 서울 날씨 어때")
    finally:
        context_node.set_weather_client(None)

    # 턴이 죽지 않고 끝까지 간다 — 예외가 새어나가 침묵하는 것이 아니라
    # 대체 응답을 말한다.
    assert state["final_utterance"]
    assert llm.calls == 1
    assert "확인이 어렵다" in llm.prompts[0] or "지어내지" in llm.prompts[0]


def test_medical_question_renders_reference_material_through_the_graph(
    wired, monkeypatch,
):
    """(완료 조건) 의료 질문의 프롬프트에도 '참고 자료' 섹션이 실제로 렌더된다.

    이 테스트의 관심사는 조회 문서 전달이므로, 의도 규칙 자체는 대역으로 분리한다.
    """
    app, _client, llm, _player = wired

    monkeypatch.setattr(context_node, "_is_medical", lambda text: True)
    monkeypatch.setattr(
        context_node, "handle_medical_query",
        lambda text: "서울대병원은 종로구에 있습니다.")

    run_user_turn(app, SENIOR, "근처 병원 어디야")

    assert llm.calls == 1, "의료 조회(function-calling)가 있어도 응답 생성은 1회다"
    assert "참고 자료" in llm.prompts[0]
    assert "서울대병원" in llm.prompts[0]


def test_medical_lookup_failure_leads_to_an_honest_reply_not_fabrication(
    wired, monkeypatch,
):
    """(완료 조건) 의료 조회 실패도 예외를 던지지 않고 솔직히 답한다."""
    app, _client, llm, _player = wired

    monkeypatch.setattr(context_node, "_is_medical", lambda text: True)

    def boom(text):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(context_node, "handle_medical_query", boom)

    state = run_user_turn(app, SENIOR, "근처 병원 어디야")

    assert state["final_utterance"]
    assert llm.calls == 1
    assert "확인이 어렵다" in llm.prompts[0] or "지어내지" in llm.prompts[0]
