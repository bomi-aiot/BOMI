"""백엔드 공유 시크릿 인증 헤더 배선 검증 (S15P11E102-307).

배경
    로봇 쪽은 로봇을 만들지 않는다 — 백엔드(be-develop, 별도 워크트리)가
    `/api/v1/robot/**` 와 `/api/v1/seniors/**` 를 지키는 서블릿 필터를 만든다.
    이 파일은 그 필터가 아직 없어도 검증 가능한, 로봇 쪽 배선만 확인한다:
    네 클라이언트가 헤더를 실어 보내는가, 그리고 401 이 조용한 실패와
    구분되는 경고로 남는가.

이 파일이 검증하는 완료 조건
    - 로봇 네 클라이언트(문맥 조회, 계약 API, 대화 이벤트, 현관 이벤트)가 모두
      공유 시크릿 헤더를 실어 보낸다 — backend_client/session.py 한 곳에서 얹는다.
    - 시크릿이 설정된 상태에서 헤더 없이/틀리게 호출해 401 을 맞으면, 그 사실이
      캐시 폴백이나 "통계 한 칸 빠짐" 같은 조용한 문구와 구분되는 "AUTH FAILURE"
      경고로 남는다.
    - 401/403 이 아닌 실패(네트워크 끊김 등)는 기존 문구 그대로 남고, 새 경고와
      섞이지 않는다 — 모든 실패를 시끄럽게 만들 필요는 없다는 티켓의 요구사항.

참고
    CLAUDE.md §5 (API 이음새), §18 (오프라인은 안전 문제다), §26 (배포 검증)
"""

from __future__ import annotations

from bomi_ai_chat.backend_client.context_client import BackendContextClient
from bomi_ai_chat.backend_client.contract_client import (
    BackendClarificationClient,
    BackendUnavailable,
)
from bomi_ai_chat.backend_client.conversation_client import BackendConversationClient
from bomi_ai_chat.backend_client.door_client import BackendDoorClient
from bomi_ai_chat.backend_client.session import (
    SHARED_SECRET_HEADER,
    build_backend_session,
)
from bomi_ai_chat.contracts.door import DoorEvent

SENIOR = "senior-1"


class FakeResponse:
    """상태코드를 자유롭게 지정할 수 있는 대역 응답 — mock 백엔드 대역."""

    def __init__(self, payload=None, *, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._payload


class FakeSession:
    """모든 요청에 고정된 상태코드로 답하는 대역 세션.

    왜 필요한가
        401 을 재현하려면 실제 백엔드 필터가 아니라, 그 필터가 401 을 돌려줬을
        때와 똑같은 모양의 응답을 만드는 대역이면 충분하다(mock 백엔드).
    """

    def __init__(self, *, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        return FakeResponse(self.payload, status_code=self.status_code)


class OfflineSession:
    """네트워크가 끊긴 것을 흉내내는 대역 — 인증 실패와 구분하기 위한 대조군."""

    def request(self, method, url, **kwargs):
        raise ConnectionError("backend unreachable")


def _door_event() -> DoorEvent:
    return DoorEvent(
        type="DOOR_OPENED",
        received_at=0.0,
        reported_at=0.0,
        source_id="snzb04p-1",
        event_id="evt-1",
    )


# ── 완료 조건 1: 네 클라이언트가 모두 헤더를 실어 보낸다 ─────────────────────


def test_build_backend_session_attaches_header_when_secret_set(settings_factory):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")

    session = build_backend_session(settings)

    assert session.headers[SHARED_SECRET_HEADER] == "s3cr3t"


def test_build_backend_session_omits_header_when_secret_unset(settings_factory):
    """시크릿 미설정은 로컬 개발의 기본값이다 — 헤더를 안 실어도 정상이다."""
    settings = settings_factory()

    session = build_backend_session(settings)

    assert SHARED_SECRET_HEADER not in session.headers


def test_context_client_default_session_carries_the_header(settings_factory):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")

    client = BackendContextClient(settings=settings)

    assert client._session.headers[SHARED_SECRET_HEADER] == "s3cr3t"


def test_clarification_client_default_session_carries_the_header(settings_factory):
    """온보딩/재질의(contract_client.py)도 같은 배선을 쓴다."""
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")

    client = BackendClarificationClient(settings=settings)

    assert client._session.headers[SHARED_SECRET_HEADER] == "s3cr3t"


def test_conversation_client_default_session_carries_the_header(settings_factory):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")

    client = BackendConversationClient(settings=settings)

    assert client._session.headers[SHARED_SECRET_HEADER] == "s3cr3t"


def test_door_client_default_session_carries_the_header(settings_factory):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")

    client = BackendDoorClient(settings=settings)

    assert client._session.headers[SHARED_SECRET_HEADER] == "s3cr3t"


def test_explicit_session_is_not_overridden(settings_factory):
    """호출부가 세션을 직접 주면(테스트 대역 등) 그대로 쓴다 — 강제로 덮지 않는다."""
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    fake = FakeSession()

    client = BackendContextClient(settings=settings, session=fake)

    assert client._session is fake


# ── 완료 조건 2: 401 이 캐시 폴백/조용한 실패와 구분되는 경고로 드러난다 ─────


def test_context_client_401_logs_a_distinct_auth_warning(settings_factory, caplog):
    """(완료 조건) 시크릿 설정 상태에서 헤더 없이 부르면 401, 그리고 경고 로그."""
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    client = BackendContextClient(settings=settings, session=FakeSession(status_code=401))

    with caplog.at_level("WARNING"):
        result = client.fetch_context(SENIOR, query="안녕")

    # context_client 의 계약(예외를 던지지 않는다)은 바뀌지 않는다 — 캐시 폴백은
    # 그대로 일어나되, "그냥 오프라인" 문구가 아니라 인증 실패 문구가 남는다.
    assert result.is_cached is True
    assert "AUTH FAILURE" in caplog.text
    assert "status=401" in caplog.text
    # "falling back to cache" 자체는 AUTH FAILURE 문구 안에 설명으로 남아도 된다.
    # 막아야 하는 것은 일반 오프라인 문구("context fetch failed")로 뭉뚱그려지는
    # 것이다 — 그러면 배포 때 시크릿을 안 맞춘 실수가 "그냥 오프라인이었나 보다"에
    # 묻힌다(S15P11E102-307).
    assert "context fetch failed" not in caplog.text


def test_clarification_client_401_logs_before_raising(settings_factory, caplog):
    """(완료 조건) 계약 API 는 여전히 예외를 올리지만, 그 전에 경고를 남긴다."""
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    client = BackendClarificationClient(
        settings=settings, session=FakeSession(status_code=401))

    raised = False
    with caplog.at_level("WARNING"):
        try:
            client.active(SENIOR)
        except BackendUnavailable:
            raised = True

    assert raised is True
    assert "AUTH FAILURE" in caplog.text


def test_conversation_client_401_logs_a_distinct_auth_warning(settings_factory, caplog):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    client = BackendConversationClient(
        settings=settings, session=FakeSession(status_code=401))

    with caplog.at_level("WARNING"):
        result = client.record_turn(
            SENIOR, role="ROBOT", content="안녕하세요", occurred_at=0.0)

    # record_turn 은 (conversationId, messageId) 튜플 계약(S15P11E102-306)을 쓴다.
    assert result == (None, None)
    assert "AUTH FAILURE" in caplog.text
    assert "short by one" not in caplog.text


def test_door_client_401_logs_a_distinct_auth_warning(settings_factory, caplog):
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    client = BackendDoorClient(settings=settings, session=FakeSession(status_code=401))

    with caplog.at_level("WARNING"):
        forwarded = client.forward_event(SENIOR, _door_event())

    assert forwarded is False
    assert "AUTH FAILURE" in caplog.text
    assert "TTL-driven drop" in caplog.text


def test_network_failure_does_not_trigger_the_auth_warning(settings_factory, caplog):
    """(완료 조건) 다른 실패 사유(네트워크 끊김)까지 전부 시끄럽게 만들지 않는다."""
    settings = settings_factory(BACKEND_SHARED_SECRET="s3cr3t")
    client = BackendContextClient(settings=settings, session=OfflineSession())

    with caplog.at_level("WARNING"):
        result = client.fetch_context(SENIOR, query="안녕")

    assert result.is_cached is True
    assert "AUTH FAILURE" not in caplog.text
    assert "falling back to cache" in caplog.text
