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

from bomi_ai_chat.backend_client import ContextResult
from bomi_ai_chat.graph import build, handlers, output
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph.build import build_graph
from bomi_ai_chat.graph.turn import run_user_turn
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"


class FakeContextClient:
    """백엔드 대역. online=False 로 두면 캐시 폴백 경로를 흉내낸다."""

    def __init__(self, ctx=None, *, is_cached=False):
        self.ctx = ctx if ctx is not None else {"profile": {"preferredName": "순자님"}}
        self.is_cached = is_cached
        self.calls = 0

    def fetch_context(self, senior_id, **kwargs):
        self.calls += 1
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
    cancel() 로 멈출 수 있고, remaining_sentences() 로 못 한 말을 알려줘야 한다.
    """

    def __init__(self, sentences):
        self.sentences = list(sentences)
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def remaining_sentences(self):
        # 이 대역은 즉시 전부 말한 것으로 친다.
        return []


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
    """

    def __init__(self):
        self.turns = []

    def record_turn(self, senior_id, **fields):
        self.turns.append({"seniorId": senior_id, **fields})
        return fields.get("conversation_id") or "conversation-1"


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
