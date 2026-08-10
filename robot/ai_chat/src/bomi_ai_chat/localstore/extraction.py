"""사실 추출 대기열 — 대화에서 나온 말이 '기억'이 되는 첫 번째 문. (S15P11E102-255)

어디에 위치하는가
    graph/build.memory_write 가 반응형 턴이 끝날 때마다(스킵 조건을 통과한
    경우에만) enqueue() 로 한 행을 남긴다. jobs/ticks.extraction_flush 가
    턴 밖에서 주기적으로 pending() 을 읽어 LLM 으로 사실을 뽑고,
    backend_client/fact_client 로 제출한 뒤 mark_extracted() 로 지운다.

왜 outbox 와 구조가 비슷한가
    "먼저 쓰고, 나중에(턴 밖에서) 처리한다"는 같은 패턴이다(outbox.py 참고).
    다른 점: outbox 는 '잃으면 안 되는 것'이라 synchronous=FULL 인 별도 DB 를
    쓰지만, 여기는 runtime DB 에 둔다 — 이 큐의 행 하나를 잃어도 어르신이
    다치지 않는다. 잃으면 그저 기억 하나가 안 생긴다. 그리고 이미 그런
    손실을 감수하는 결정이 memory_write 안에 있다(§8 sourceMessageId 요구
    조건 참고).

왜 LLM 호출이 이 모듈에 없는가
    이 모듈은 순수하게 큐 I/O 다. LLM 호출과 백엔드 제출은
    jobs/ticks.extraction_flush 의 책임이다 — 그래야 이 모듈을 테스트할 때
    가짜 LLM 이나 네트워크가 전혀 필요 없다.

참고
    CLAUDE.md §8 (RAG 경계, fact_candidate 쓰기 규칙), §16 (생성 호출 예산),
    §18 (턴 밖에서 도는 백그라운드 작업)
"""

from __future__ import annotations

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db


def enqueue(
    senior_id: str,
    *,
    conversation_id: str | None,
    source_message_id: str | None,
    content: str,
    preceding_robot_utterance: str = "",
) -> int:
    """어르신의 발화 한 번을 추출 대기열에 남긴다. LLM 을 부르지 않는다.

    누가 호출하는가
        graph/build.memory_write. 스킵 조건(킬스위치, 능동/명령 턴, T1,
        계약 주도형 대화 진행 중, 6자 미만 발화, 봉인된 대화, 메시지 id 없음)
        을 전부 통과한 반응형 턴만 여기 온다 — 그 판단은 호출부의 몫이고,
        이 함수는 판단 없이 그대로 적는다.

    반환값
        큐 행 id. 지금은 호출부가 쓰지 않지만, outbox.enqueue 와 같은 모양을
        맞춰 둔다(테스트와 향후 취소 기능을 위해).
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "INSERT INTO extraction_job "
        "(senior_id, conversation_id, source_message_id, content, "
        " preceding_robot_utterance, extracted, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (
            senior_id,
            conversation_id,
            source_message_id,
            content,
            preceding_robot_utterance,
            clock.now(),
        ),
    )
    return int(cursor.lastrowid)


def pending(limit: int | None = None) -> list[dict]:
    """아직 처리되지 않은 행을 실패가 적은 순 → 오래된 순으로 돌려준다.

    누가 호출하는가
        jobs.ticks.extraction_flush. 큐의 순서가 발화의 순서이므로, 오래된
        것부터 처리해야 preceding_robot_utterance 의 맥락이 어긋나지 않는다.

    ★ 왜 attempts 가 첫 번째 정렬 키인가 (S15P11E102-393)
        오래된 순으로만 뽑으면 **한 행의 실패가 큐 전체를 막는다.** 실패한 행은
        일부러 extracted 로 표시하지 않고 남기는데(재시도가 목적이다), 영원히
        성공하지 못하는 행이 batch 크기만큼 모이면 매 flush 가 그 행들만 다시
        시도하고 뒤에 쌓인 새 발화는 차례가 오지 않는다. 실제 경로: 리허설
        사이에 서버 DB 만 초기화하면 로컬 큐에 남은 행의 conversationId 가
        서버에 없어 400 이 돌아오고, 400 은 재시도 대상이 아니라 즉시 실패한다.

        실패 횟수를 먼저 보면 한 번도 시도하지 않은 행이 항상 앞선다. 앞막힘이
        정책이 아니라 **구조적으로** 불가능해진다. 전부 실패 횟수가 같은
        정상 상태에서는 정렬이 예전과 완전히 같다 — 맥락 순서는 그대로다.

    인자
        limit: 최대 건수. None 이면 전부(테스트에서만 쓴다 — 운영 경로는
            항상 policy.EXTRACTION_FLUSH_BATCH_SIZE 를 넘긴다).
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    query = (
        "SELECT * FROM extraction_job WHERE extracted = 0 "
        "ORDER BY attempts, created_at, id"
    )
    params: tuple = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def mark_extracted(row_id: int) -> None:
    """행을 '처리 완료'로 표시한다.

    누가 호출하는가
        jobs.ticks.extraction_flush. LLM 이 뽑을 것이 없다고 답했을 때,
        또는 뽑은 사실을 백엔드에 제출까지 성공했을 때만 부른다.

    주의사항
        백엔드 제출이 실패했으면 이 함수를 부르지 않는다 — 부르면 그 사실은
        다시는 제출 시도되지 않고 조용히 사라진다. fact_client 가 실패 시
        예외를 올리는 이유가 바로 이 호출을 막기 위해서다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE extraction_job SET extracted = 1 WHERE id = ?", (row_id,)
    )


def record_failure(row_id: int) -> None:
    """이 행을 처리하려다 실패했다고 적는다 — attempts 를 1 올린다.

    누가 호출하는가
        jobs.ticks.extraction_flush. LLM 추출이 실패했거나 백엔드 제출이
        실패해서 그 행을 다음 flush 로 넘길 때마다 부른다.

    왜 필요한가
        pending() 의 정렬 키다. 이 값을 올리지 않으면 실패한 행이 계속 큐
        맨 앞에 남아 뒤의 새 발화를 막는다 — 이 함수와 그 정렬이 한 쌍이다
        (S15P11E102-393).

    주의사항
        상한은 없다. 몇 번을 실패해도 행을 버리지 않는다는 뜻이고, 의도한
        것이다 — 백엔드가 한 시간 죽어 있었다는 이유로 어르신의 기억을
        조용히 잃으면 안 된다. 버리는 판단은 mark_given_up 하나만 한다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE extraction_job SET attempts = attempts + 1 WHERE id = ?", (row_id,)
    )


def mark_given_up(row_id: int) -> None:
    """행을 '포기'로 닫는다(extracted=2). 다시는 시도하지 않는다.

    누가 호출하는가
        jobs.ticks.extraction_flush, 서버가 되돌릴 수 없는 실패로 답했을 때만.
        구체적으로는 401/403(인증)과 429/502/503(일시적)을 제외한 4xx 다 —
        "이 요청은 틀렸다"는 답이고, 같은 요청을 다시 보내도 같은 답이 온다.

    왜 mark_extracted 를 쓰지 않는가
        1 은 "처리 완료"다. 서버가 거절한 행을 1 로 닫으면 큐 지표가 "다
        잘 처리됐다"고 거짓말한다. 값을 나눠 두면 나중에 "포기한 행이 몇
        건인가"를 물을 수 있다 — extracted=0 만 보는 조회(pending,
        pending_count, 부분 색인)는 어느 쪽이든 영향이 없다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE extraction_job SET extracted = 2 WHERE id = ?", (row_id,)
    )


def pending_count(senior_id: str | None = None) -> int:
    """아직 처리되지 않은 행 개수. 운영 지표이자 테스트용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    if senior_id is None:
        row = connection.execute(
            "SELECT count(*) AS c FROM extraction_job WHERE extracted = 0"
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT count(*) AS c FROM extraction_job "
            "WHERE extracted = 0 AND senior_id = ?",
            (senior_id,),
        ).fetchone()
    return int(row["c"])


def clear(senior_id: str) -> None:
    """이 어르신의 추출 큐를 전부 지운다. 테스트와 운영자 개입용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute("DELETE FROM extraction_job WHERE senior_id = ?", (senior_id,))


def forget_conversation(senior_id: str, conversation_id: str) -> int:
    """"기억하지 마" — 이 대화에서 아직 처리되지 않은 추출 대기 행을 지운다.

    무엇을 하는가
        (senior_id, conversation_id) 의 extracted=0 행을 삭제하고 지운 개수를
        돌려준다. 이미 extracted=1 인 행은 손대지 않는다 — 그 사실은 이미 서버의
        fact_candidate 로 넘어갔고, 로봇 쪽 행을 지워 봐야 없던 일이 되지 않는다.
        서버 측 취소는 별도 엔드포인트가 필요하다(BE 티켓, 현재 없음).

    누가 호출하는가
        graph/ingress.note_interaction — 어르신이 MEMORY_FORGET_MARKERS 로
        요청했을 때. 봉인(emotion.mark_sealed)과 항상 함께 불린다: 봉인은
        '앞으로'를 막고, 이 함수는 '이미 쌓인 것'을 지운다. 둘 중 하나만 하면
        요청이 절반만 지켜진다.

    왜 extracted=0 만 지우는가
        extracted=1 을 지우면 "지웠다"는 착각만 남는다. 지울 수 없는 것은
        지웠다고 말하지 않는다 — 서버 취소가 생기기 전까지 이 함수의 한계는
        문서(implementation-plan P1-B1)에 그대로 적혀 있다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "DELETE FROM extraction_job "
        "WHERE senior_id = ? AND conversation_id = ? AND extracted = 0",
        (senior_id, conversation_id),
    )
    return cursor.rowcount
