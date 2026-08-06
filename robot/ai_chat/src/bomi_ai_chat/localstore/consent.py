"""T3 동의 요청의 생애주기 — 질문을 올린 뒤에도 "무엇에 대한 답인가"를 기억한다.

어디에 위치하는가
    jobs/ticks.consent_tick 이 문턱을 넘기면 create() 로 PENDING 행을 만들고,
    그 id 를 SpeechProposal.meta.request_id 에 실어 큐에 넣는다. 어르신이 답하면
    graph/handlers._resolve_consent_answer 가 resolve() 로 GRANTED/DECLINED 를
    확정한다.

왜 speech_proposal 표로 충분하지 않은가
    제안은 게이트가 이기거나 지면 지워진다(CLAUDE.md §7). 동의 요청은 질문이
    '나간 뒤'에도 살아 있어야 한다 — 그래야 다음 턴의 "응"/"아니"가 어느
    요청에 대한 답인지 안다. ConvState.pending_consent 가 그 연결고리를
    턴 사이에 들고 다니고(state.py 참고), 이 표는 그 요청 자체의 상태다.

참고
    CLAUDE.md §9(T1~T4), §12(계약 주도형 대화와 같은 계열의 판정 방식)
"""

from __future__ import annotations

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db

_VALID_STATUSES = {"GRANTED", "DECLINED", "EXPIRED"}


def create_request(senior_id: str, conversation_id: str | None) -> int:
    """PENDING 상태의 동의 요청 행을 만든다.

    누가 호출하는가
        jobs.ticks.consent_tick. 문턱을 넘겨 질문을 큐에 넣기로 확정한 순간.

    반환값
        요청 행 id. SpeechProposal.meta.request_id 로 실어 보낸다 — 질문이
        실제로 나간 턴에서 ConvState.pending_consent 에 이 id 를 담아야
        다음 턴의 답을 이 요청에 연결할 수 있다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "INSERT INTO consent_request "
        "(senior_id, conversation_id, status, created_at) "
        "VALUES (?, ?, 'PENDING', ?)",
        (senior_id, conversation_id, clock.now()),
    )
    return int(cursor.lastrowid)


def resolve(request_id: int, status: str) -> None:
    """PENDING 인 요청을 GRANTED/DECLINED/EXPIRED 로 확정한다.

    누가 호출하는가
        graph.handlers._resolve_consent_answer(GRANTED/DECLINED).

    왜 PENDING 인 것만 갱신하는가
        이미 확정된 요청을 다시 확정하면 resolved_at 이 나중 시각으로 덮이고,
        "언제 답했는가"라는 감사 기록이 흐트러진다. 두 번째 갱신 시도는
        조용히 무시한다 — 애초에 pending_consent 가 한 번 쓰이면 None 으로
        비워지므로(state.py) 정상 경로에서는 일어나지 않는다.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"알 수 없는 동의 요청 상태: {status!r}")
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE consent_request SET status = ?, resolved_at = ? "
        "WHERE id = ? AND status = 'PENDING'",
        (status, clock.now(), request_id),
    )


def get(request_id: int) -> dict | None:
    """요청 하나를 읽는다. 테스트와 사후 확인용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT * FROM consent_request WHERE id = ?", (request_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def clear(senior_id: str) -> None:
    """이 어르신의 동의 요청을 전부 지운다. 테스트와 운영자 개입용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute("DELETE FROM consent_request WHERE senior_id = ?", (senior_id,))
