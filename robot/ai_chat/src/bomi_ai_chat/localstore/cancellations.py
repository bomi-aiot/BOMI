# robot/ai_chat/src/bomi_ai_chat/localstore/cancellations.py
""""기억하지 마"의 서버 취소 요청 큐 (S15P11E102-348).

어디에 위치하는가
    ingress._honor_privacy_requests 가 로컬 대기 행을 지우면서(enqueue) 여기에
    적고, jobs/ticks.extraction_flush 가 pending 을 읽어 백엔드의 취소
    엔드포인트로 보낸 뒤 mark_done 한다.

왜 즉시 호출이 아니라 큐인가
    두 가지다. ① 턴 경로(ingress)에서 블로킹 HTTP 를 부르면 지연 예산(§16)을
    깬다. ② 네트워크가 끊긴 순간의 요청을 잃으면 "지웠어요"가 거짓말이 된다 —
    outbox 와 같은 "실패해도 잃으면 안 된다" 방향이다. 서버 쪽 취소가 멱등이라
    재전송은 안전하다.

참고
    CLAUDE.md §8 (정정과 삭제), backend RobotFactIntakeController /cancel
"""

from __future__ import annotations

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db


def enqueue(senior_id: str, conversation_id: str) -> None:
    """이 대화의 서버 취소를 요청한다. 멱등하다.

    같은 대화에 대한 반복 요청은 UNIQUE 로 행 하나에 접힌다. 이미 처리된(done=1)
    대화에 새 요청이 오면 done=0 으로 되돌린다 — 그 사이 새 후보가 제출됐을 수
    있고, 어르신의 새 요청은 그것까지 지우라는 뜻이다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "INSERT OR IGNORE INTO fact_cancel_request "
        "(senior_id, conversation_id, done, created_at) VALUES (?, ?, 0, ?)",
        (senior_id, conversation_id, clock.now()),
    )
    if cursor.rowcount == 0:
        connection.execute(
            "UPDATE fact_cancel_request SET done = 0, created_at = ? "
            "WHERE senior_id = ? AND conversation_id = ?",
            (clock.now(), senior_id, conversation_id),
        )


def pending(senior_id: str, limit: int = 10) -> list[dict]:
    """아직 서버로 못 보낸 취소 요청, 오래된 순."""
    connection = runtime_db()
    schema.init_runtime(connection)
    rows = connection.execute(
        "SELECT id, senior_id, conversation_id FROM fact_cancel_request "
        "WHERE done = 0 AND senior_id = ? ORDER BY created_at ASC LIMIT ?",
        (senior_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_done(row_id: int) -> None:
    """서버 전송이 성공했을 때만 부른다. 실패한 행은 그대로 남아 재시도된다."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE fact_cancel_request SET done = 1 WHERE id = ?", (row_id,)
    )


def pending_count(senior_id: str) -> int:
    """운영 지표이자 테스트용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT count(*) AS c FROM fact_cancel_request WHERE done = 0 AND senior_id = ?",
        (senior_id,),
    ).fetchone()
    return int(row["c"])
