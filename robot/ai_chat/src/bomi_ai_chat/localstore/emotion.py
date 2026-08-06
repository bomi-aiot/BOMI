"""정서 신호 누적과 봉인(T4) 판정 — 발화 원문 없이, 조용히.

어디에 위치하는가
    graph/handlers.handle_emotional 이 매 정서 턴마다 이 모듈에 신호를 남긴다.
    jobs/ticks.consent_tick 이 누적된 신호가 문턱(policy.T3_CONSENT_SIGNAL_THRESHOLD)을
    넘었는지 이 모듈에 물어 T3 동의 질문을 큐에 넣을지 정한다.

왜 발화 원문을 저장하지 않는가
    이 표가 답해야 하는 질문은 "정서 발화가 몇 번 있었는가"와 "이 대화가
    봉인됐는가" 뿐이다. 무슨 말을 했는지는 이 표의 몫이 아니다. 원문을 담으면
    "우리끼리 얘기"라고 말해도 그 약속을 지키는 코드가 없는 상태가 되고,
    T4 는 어르신이 그것을 실제로 믿을 수 있어야 T3 가 작동한다(CLAUDE.md §9).

봉인(sealed)과 신호 소비(consumed)를 왜 구분하는가
    봉인은 "이 대화로는 절대 동의 질문을 만들지 않는다"는 뜻이고, 소비는
    "이 신호는 이미 어떤 동의 질문에 기여했으니 다시 세지 않는다"는 뜻이다.
    봉인된 대화의 신호는 애초에 기록하지 않으므로(record_signal 을 부르지
    않는다, graph/handlers.py 참고) 둘이 겹칠 일은 없지만, 뜻은 다르다.

★ 253 은 최소 형태다
    지금은 "문턱 하나만 넘으면 큐잉"만 한다. 우울·고립 추세를 보는 정교한
    누적(가중치, 감쇠, 대화별 분리 등)은 S15P11E102-255 가 이 모듈을 확장해서
    붙인다. 그래서 함수 이름과 반환값을 명확히 두어 확장 지점을 남긴다.

참고
    CLAUDE.md §8(회피 목록·T4), §9(티어), §19(로컬 SQLite 는 사실이 아니다)
"""

from __future__ import annotations

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db


def record_signal(senior_id: str, conversation_id: str | None) -> None:
    """정서 발화 한 번을 신호로 남긴다. 발화 원문은 받지도, 담지도 않는다.

    누가 호출하는가
        graph/handlers.handle_emotional. 봉인 표지가 없는 정서 턴마다.

    주의사항
        senior_id 가 없으면 조용히 넘어간다. 큐의 키가 어르신 id 이므로, 임의의
        키로 쌓으면 아무도 집어가지 않는 행이 늘어날 뿐이다.
    """
    if not senior_id:
        return
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "INSERT INTO emotional_signal "
        "(senior_id, conversation_id, signal_type, sealed, consumed, created_at) "
        "VALUES (?, ?, 'emotional', 0, 0, ?)",
        (senior_id, conversation_id or "", clock.now()),
    )


def mark_sealed(senior_id: str, conversation_id: str | None) -> None:
    """이 대화를 봉인한다. "우리끼리 얘기" 류 표현이 나왔을 때.

    무엇을 하는가
        (senior_id, conversation_id) 조합에 sealed=1 행을 남긴다. 이후
        is_conversation_sealed 가 이 대화에 대해 항상 True 를 돌려준다.

    왜 conversation_id 가 없으면 아무것도 안 하는가
        봉인은 '이 대화'에 걸리는 표시다. 대화를 특정할 수 없으면 무엇을
        봉인하는지 정의되지 않고, 잘못하면 다음 대화까지 봉인해버릴 수 있다 —
        그건 반대 방향의 실패다(필요한 동의 질문을 영영 못 만든다).
    """
    if not senior_id or not conversation_id:
        return
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "INSERT INTO emotional_signal "
        "(senior_id, conversation_id, signal_type, sealed, consumed, created_at) "
        "VALUES (?, ?, 'seal', 1, 1, ?)",
        (senior_id, conversation_id, clock.now()),
    )


def is_conversation_sealed(senior_id: str, conversation_id: str | None) -> bool:
    """이 대화가 봉인됐는가 — 공개 판정 함수.

    누가 호출하는가
        jobs.ticks.consent_tick(동의 질문을 올리기 전 마지막 확인),
        그리고 나중에 대화→기억 추출 티켓(봉인된 대화를 추출 대상에서 뺀다).

    반환값
        senior_id 나 conversation_id 가 없으면 False. 대화를 특정할 수 없는데
        봉인됐다고 답하면, 그 자체가 조용한 오탐이다.
    """
    if not senior_id or not conversation_id:
        return False
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT 1 FROM emotional_signal "
        "WHERE senior_id = ? AND conversation_id = ? AND sealed = 1 LIMIT 1",
        (senior_id, conversation_id),
    ).fetchone()
    return row is not None


def pending_signal_count(senior_id: str) -> int:
    """아직 어떤 동의 질문에도 쓰이지 않은 정서 신호 개수.

    누가 호출하는가
        jobs.ticks.consent_tick. policy.T3_CONSENT_SIGNAL_THRESHOLD 와 비교한다.
    """
    if not senior_id:
        return 0
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT count(*) AS c FROM emotional_signal "
        "WHERE senior_id = ? AND signal_type = 'emotional' AND consumed = 0",
        (senior_id,),
    ).fetchone()
    return int(row["c"])


def consume_pending_signals(senior_id: str) -> None:
    """대기 중인 정서 신호를 전부 '소비됨'으로 표시한다.

    누가 호출하는가
        jobs.ticks.consent_tick. 문턱을 넘겨 동의 질문을 실제로 큐에 넣은 직후.

    왜 여기서 지우지 않고 표시만 하는가
        지우면 "이 어르신이 그동안 정서 발화를 몇 번 했는가"를 나중에 되짚어볼
        수 없다. 253 은 이 값을 안 쓰지만, 255 의 추세 분석이 원본이 남아 있는
        편을 더 유용하게 쓸 수 있다.
    """
    if not senior_id:
        return
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "UPDATE emotional_signal SET consumed = 1 "
        "WHERE senior_id = ? AND signal_type = 'emotional' AND consumed = 0",
        (senior_id,),
    )


def clear(senior_id: str) -> None:
    """이 어르신의 정서 신호를 전부 지운다. 테스트와 운영자 개입용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute("DELETE FROM emotional_signal WHERE senior_id = ?", (senior_id,))
