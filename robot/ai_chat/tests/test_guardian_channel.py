"""보호자 알림 전달과 대화 적재 — 211 로봇 측 회귀.

이 파일이 검증하는 것
    1. 로봇이 푸시 서버가 아니라 백엔드로 보낸다
    2. 거절(미동의)과 실패(네트워크)를 구분한다 — 거절은 재시도하지 않는다
    3. 대화 이벤트가 어르신·로봇으로 나뉘어 올라간다
    4. 지남력 질문 플래그가 실려 가고, 프롬프트로는 돌아오지 않는다
    5. 대화 적재 실패가 턴을 막지 않는다

가장 중요한 두 가지
    test_a_refusal_is_not_retried
        거절을 실패로 다루면 outbox 가 영원히 재시도하고, 매 재시도가 배터리를
        깎는 라디오 깨우기다. 그리고 그 결정은 재시도로 바뀌지 않는다.

    test_a_failed_conversation_write_does_not_break_the_turn
        통계 때문에 대화를 망치지 않는다.

참고
    CLAUDE.md §9 (티어와 동의), §18 (발신 큐), §8 (지남력 반복은 프롬프트에 닿지 않는다)
"""

import json

import pytest

from bomi_ai_chat.graph import build, context, handlers, output
from bomi_ai_chat.graph.build import build_graph
from bomi_ai_chat.graph.turn import run_user_turn
from bomi_ai_chat.localstore import db, outbox
from bomi_ai_chat.notify import NotifyError
from bomi_ai_chat.notify.backend_notifier import BackendGuardianNotifier

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class FakeResponse:
    def __init__(self, payload, status_code=201):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self._payload


class FakeSession:
    """요청을 기록하고 미리 정한 응답을 돌려준다. 예외도 낼 수 있다."""

    def __init__(self, *, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


def notifier(session, settings_factory):
    return BackendGuardianNotifier(SENIOR, settings=settings_factory(), session=session)


# ── 로봇은 백엔드로 보낸다 ───────────────────────────────────────────────────


def test_the_robot_forwards_to_the_backend_not_a_push_service(settings_factory):
    """★ 자격증명을 로봇에 놓으면 푸시 토큰이 기기마다 내려가고,
    로봇 한 대가 털리면 그 토큰도 함께 털린다."""
    session = FakeSession(response=FakeResponse({"delivered": True}))

    notifier(session, settings_factory).notify_guardian("T1", {"reason": "no_response"})

    assert len(session.requests) == 1
    assert session.requests[0]["url"].endswith("/api/v1/robot/guardian-alerts")
    body = session.requests[0]["json"]
    assert body["seniorId"] == SENIOR
    assert body["tier"] == "T1"


def test_a_network_failure_is_retryable(settings_factory):
    """★ 조용히 성공 처리하면 T1 알림이 사라진다. 하필 그 순간이 가장 중요하다."""
    session = FakeSession(error=OSError("network unreachable"))

    with pytest.raises(NotifyError):
        notifier(session, settings_factory).notify_guardian("T1", {"reason": "no_response"})


def test_a_refusal_is_not_retried(settings_factory):
    """★★ 미동의는 실패가 아니다.

    NotifyError 로 올리면 outbox 가 영원히 재시도하고, 매 재시도가 배터리를 깎는
    라디오 깨우기다. 그리고 그 결정은 재시도로 바뀌지 않는다.
    """
    session = FakeSession(response=FakeResponse(
        {"delivered": False, "reason": "CONSENT_NOT_GRANTED"}))

    # 예외가 나지 않아야 한다 — outbox 가 SENT 로 표시하고 큐에서 내려놓는다.
    notifier(session, settings_factory).notify_guardian("T2", {"reason": "daily_summary"})


def test_an_undeliverable_t1_is_logged_loudly(settings_factory, caplog):
    """T1 이 아무에게도 못 닿는 것은 조용히 지나가서는 안 되는 상태다."""
    session = FakeSession(response=FakeResponse(
        {"delivered": False, "reason": "NO_GUARDIAN"}))

    with caplog.at_level("WARNING"):
        notifier(session, settings_factory).notify_guardian("T1", {"reason": "no_response"})

    assert "will NOT reach anyone" in caplog.text


def test_an_unreadable_body_does_not_resend_an_accepted_alert(settings_factory):
    """서버는 201 로 접수를 확정했다. 본문을 못 읽었다고 다시 보내면 중복이다."""
    session = FakeSession(response=FakeResponse({}, status_code=201))
    session.response.content = b"not json"

    notifier(session, settings_factory).notify_guardian("T2", {"reason": "daily_summary"})


def test_the_outbox_marks_a_refused_alert_as_done(settings_factory, frozen_clock):
    """★ 거절된 알림이 큐에 남으면 매 flush 마다 같은 요청이 나간다."""
    frozen_clock(start=1_700_000_000.0)
    session = FakeSession(response=FakeResponse(
        {"delivered": False, "reason": "CONSENT_NOT_GRANTED"}))
    outbox.enqueue("T2", {"reason": "daily_summary"})

    result = outbox.flush(notifier(session, settings_factory))

    assert result["sent"] == 1
    assert outbox.pending_count() == 0


# ── 대화 적재 ────────────────────────────────────────────────────────────────


def test_the_real_client_returns_a_conversation_and_message_id_pair(settings_factory):
    """(S15P11E102-306) 실제 클라이언트도 (conversationId, messageId) 튜플을 돌려준다.

    graph/build.py 는 이제 단일 값이 아니라 튜플을 기대한다. 여기서는 진짜
    BackendConversationClient 가 백엔드 응답 본문에서 두 필드를 함께 뽑아내는지를
    HTTP 계층까지 내려가 확인한다(RecordingConversationClient 는 대역일 뿐이라
    실제 파싱 로직은 검증하지 못한다).
    """
    from bomi_ai_chat.backend_client.conversation_client import (
        BackendConversationClient,
    )

    session = FakeSession(response=FakeResponse(
        {"conversationId": "conversation-9", "messageId": "message-9"}))
    client = BackendConversationClient(settings=settings_factory(), session=session)

    conversation_id, message_id = client.record_turn(
        SENIOR, role="SENIOR", content="안녕하세요", occurred_at=0.0)

    assert conversation_id == "conversation-9"
    assert message_id == "message-9"


def test_the_real_client_tolerates_a_missing_message_id(settings_factory):
    """★ 255 번(백엔드가 messageId 를 채우기 시작하는 티켓)이 아직 나가지 않았을 수
    있다. 본문에 messageId 가 없어도 조용히 None 이어야지, 예외를 던지면 안 된다.
    """
    from bomi_ai_chat.backend_client.conversation_client import (
        BackendConversationClient,
    )

    session = FakeSession(response=FakeResponse({"conversationId": "conversation-9"}))
    client = BackendConversationClient(settings=settings_factory(), session=session)

    conversation_id, message_id = client.record_turn(
        SENIOR, role="SENIOR", content="안녕하세요", occurred_at=0.0)

    assert conversation_id == "conversation-9"
    assert message_id is None


def test_the_real_client_returns_a_none_pair_on_failure(settings_factory):
    """네트워크 실패는 (None, None) 이다 — 통계 때문에 턴을 막지 않으려고 예외를
    던지지 않는다(모듈 docstring 참고)."""
    from bomi_ai_chat.backend_client.conversation_client import (
        BackendConversationClient,
    )

    session = FakeSession(error=OSError("network unreachable"))
    client = BackendConversationClient(settings=settings_factory(), session=session)

    result = client.record_turn(SENIOR, role="SENIOR", content="안녕하세요", occurred_at=0.0)

    assert result == (None, None)


class RecordingConversationClient:
    """대화 적재 대역 — 서버와 같은 계약(null-in → 새 id 발급, 아니면 에코).

    S15P11E102-306: 예전에는 호출마다 무조건 "conversation-1"을 돌려줘서,
    turn.py 가 매 턴 conversation_id 를 None 으로 덮어쓰는 결함이 있어도 대화가
    이어지는 것처럼 보이는 함정이 있었다. 여기서 같은 함정을 다시 만들지 않는다.
    """

    def __init__(self, *, fail=False):
        self.turns = []
        self.fail = fail
        self._next_conversation_id = 1
        self._next_message_id = 1

    def record_turn(self, senior_id, **fields):
        if self.fail:
            return None, None

        self.turns.append({"seniorId": senior_id, **fields})

        conversation_id = fields.get("conversation_id")
        if conversation_id is None:
            conversation_id = f"conversation-{self._next_conversation_id}"
            self._next_conversation_id += 1

        message_id = f"message-{self._next_message_id}"
        self._next_message_id += 1
        return conversation_id, message_id


class FakeContextClient:
    def fetch_context(self, senior_id, **kwargs):
        from bomi_ai_chat.backend_client import ContextResult

        return ContextResult(ctx={}, is_cached=False)


class FakeLLM:
    def generate(self, prompt):
        return "8월 2일이에요."


class FakeHandle:
    def cancel(self):
        pass

    def remaining_sentences(self):
        return []


class FakePlayer:
    def speak_async(self, sentences):
        return FakeHandle()


@pytest.fixture
def wired(monkeypatch, tmp_path):
    conversations = RecordingConversationClient()
    context.set_client(FakeContextClient())
    handlers.set_llm(FakeLLM())
    output.set_player(FakePlayer())
    build.set_conversation_client(conversations)

    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))
    yield app, conversations

    context.set_client(None)
    handlers.set_llm(None)
    output.set_player(None)
    build.set_conversation_client(None)


def test_a_turn_records_the_senior_and_the_robot_separately(wired):
    """★ 합쳐 세면 로봇이 혼자 떠든 날이 '활발한 날'로 집계된다."""
    app, conversations = wired

    run_user_turn(app, SENIOR, "오늘 며칠이야")

    roles = [turn["role"] for turn in conversations.turns]
    assert roles == ["SENIOR", "ROBOT"]


def test_the_senior_is_recorded_before_the_robot(wired):
    """★ 서버가 올라온 순서로 순번을 매긴다.

    로봇 발화를 먼저 올리면 기록상 로봇이 먼저 말한 것이 된다.
    """
    app, conversations = wired

    run_user_turn(app, SENIOR, "심심해")

    assert conversations.turns[0]["role"] == "SENIOR"
    assert conversations.turns[0]["content"] == "심심해"


def test_an_orientation_question_is_flagged(wired):
    """지남력 질문 반복은 인지 저하의 이른 신호다. 서버가 세려면 표시가 필요하다."""
    app, conversations = wired

    run_user_turn(app, SENIOR, "오늘 며칠이야")

    assert conversations.turns[0]["orientation_question"] is True


def test_ordinary_talk_is_not_flagged_as_orientation(wired):
    app, conversations = wired

    run_user_turn(app, SENIOR, "손자가 놀러 왔어")

    assert conversations.turns[0]["orientation_question"] is False


def test_the_weather_is_not_an_orientation_question():
    """★ "오늘 추워?"는 지남력 질문이 아니라 그냥 정보 질문이다.

    여기서 오탐이 나면 보호자에게 인지 저하가 진행 중이라고 보고하게 된다.
    """
    assert context.is_orientation_question("오늘 며칠이야") is True
    assert context.is_orientation_question("여기가 어디야") is True
    assert context.is_orientation_question("오늘 날씨 어때") is False
    assert context.is_orientation_question("오늘 추워?") is False


def test_a_reactive_turn_carries_no_priority(wired):
    """★ 방금 말을 건 사람에게 대답하는 것은 게이트를 거치지 않는다.

    우선순위를 붙이면 있지도 않았던 판정을 지어내는 것이다.
    """
    app, conversations = wired

    run_user_turn(app, SENIOR, "심심해")

    robot_turn = conversations.turns[1]
    assert robot_turn["trigger_type"] == "USER"
    assert robot_turn.get("priority") is None


def test_the_conversation_id_is_carried_into_the_next_turn(wired):
    """서버가 배정한 id 를 들고 가야 두 턴이 같은 대화에 붙는다."""
    app, conversations = wired

    state = run_user_turn(app, SENIOR, "안녕")
    assert state["conversation_id"] == "conversation-1"

    run_user_turn(app, SENIOR, "잘 잤어")
    assert conversations.turns[-1]["conversation_id"] == "conversation-1"


def test_a_failed_conversation_write_does_not_break_the_turn(monkeypatch, tmp_path):
    """★★ 통계 때문에 대화를 망치지 않는다.

    기록을 남기지 못했다고 어르신에게 대답을 못 하게 만들면 안 된다.
    """
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    context.set_client(FakeContextClient())
    handlers.set_llm(FakeLLM())
    output.set_player(FakePlayer())
    build.set_conversation_client(RecordingConversationClient(fail=True))
    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))

    try:
        state = run_user_turn(app, SENIOR, "심심해")
        assert state["final_utterance"], "적재가 실패해도 로봇은 대답해야 한다"
    finally:
        context.set_client(None)
        handlers.set_llm(None)
        output.set_player(None)
        build.set_conversation_client(None)


def test_conversation_events_do_not_go_through_the_outbox(wired):
    """★ outbox 는 '잃으면 안 되는 것'을 위한 곳이다.

    거기에 통계를 섞으면 T1 알림이 통계 뒤에 줄을 선다.
    """
    app, _conversations = wired

    run_user_turn(app, SENIOR, "심심해")

    assert outbox.pending_count() == 0
