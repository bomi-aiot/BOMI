"""발화 제안 큐 — 게이트가 심판할 대기 목록.

어디에 위치하는가
    스케줄러, 침묵 사다리, 현관 이벤트, 재질의 흐름이 여기에 제안을 넣는다.
    게이트(graph/gate.py)가 여기서 꺼내 최대 하나만 통과시킨다.

왜 메모리가 아니라 DB 인가
    재부팅을 넘어 살아남아야 한다. 09:00 복약 알림이 큐에 들어간 뒤 08:59 에 로봇이
    재시작되면, 메모리 큐였다면 그 알림은 사라진다. 복약 알림이 조용히 사라지는 것은
    품질 문제가 아니라 안전 문제다.

용어 주의
    'candidate' 가 아니라 'proposal' 이다. 서버 DB 가 candidate 를 fact_candidate
    (미확정 사실)로 이미 소유하고 있다 (CLAUDE.md §4).

참고
    CLAUDE.md §7 (게이트와 우선순위), §11 (인사 TTL)
"""

from __future__ import annotations

import json

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db
from bomi_ai_chat.state import SpeechProposal


def enqueue(senior_id: str, proposal: SpeechProposal) -> int:
    """제안을 큐에 넣는다. 아직 말한 것이 '아니다'.

    누가 호출하는가
        jobs.ticks(스케줄·침묵 사다리), graph.ingress.door_event, 재질의 흐름.

    반환값
        큐 행 id. 테스트와 로깅에 쓴다.

    주의사항
        expires_at 은 clock 기준 절대 시각이다. 상대 초를 넣으면 안 된다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "INSERT INTO speech_proposal "
        "(senior_id, intent, priority, seed, expires_at, origin, meta, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            senior_id,
            proposal["intent"],
            proposal["priority"],
            proposal.get("seed", ""),
            proposal.get("expires_at"),
            proposal.get("origin", ""),
            json.dumps(proposal.get("meta", {}), ensure_ascii=False),
            clock.now(),
        ),
    )
    return int(cursor.lastrowid)


def pending(senior_id: str) -> list[SpeechProposal]:
    """대기 중인 제안을 전부 읽는다. 만료 여부는 걸러내지 '않는다'.

    왜 만료된 것도 돌려주는가
        폐기(discard)와 연기(defer)의 구분은 게이트의 판단이고, 그 판단은 우선순위
        정책을 봐야 한다. 저장소가 미리 지워버리면 "인사는 버리고 복약은 남긴다"를
        게이트가 표현할 수 없다. 저장소는 사실만, 판단은 게이트가 한다.

    누가 호출하는가
        graph.gate.proactive_gate, 그리고 부트스트랩(재부팅 복원).

    반환값
        큐에 든 순서(created_at)대로. 각 dict 에 저장소 행 id 가 meta 가 아니라
        별도 키 "_row_id" 로 붙는다. discard 할 때 필요하다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    rows = connection.execute(
        "SELECT * FROM speech_proposal WHERE senior_id = ? ORDER BY created_at, id",
        (senior_id,),
    ).fetchall()

    result: list[SpeechProposal] = []
    for row in rows:
        proposal: SpeechProposal = {
            "intent": row["intent"],
            "priority": row["priority"],
            "seed": row["seed"],
            "expires_at": row["expires_at"],
            "origin": row["origin"],
            "meta": json.loads(row["meta"]),
        }
        # 저장소 행 id. 게이트가 이긴 제안과 만료된 제안을 지울 때 쓴다.
        proposal["meta"]["_row_id"] = row["id"]
        result.append(proposal)
    return result


def discard(row_id: int) -> None:
    """제안 하나를 큐에서 지운다.

    누가 호출하는가
        게이트. 두 경우에 부른다 — 이겨서 말했거나, TTL 이 만료돼 폐기할 때.
        둘 다 "다시 오지 않는다"는 뜻이므로 같은 연산이다. 연기는 지우지 않는 것이다.
    """
    runtime_db().execute("DELETE FROM speech_proposal WHERE id = ?", (row_id,))


def discard_expired(senior_id: str) -> int:
    """만료된 제안을 한 번에 정리한다.

    왜 필요한가
        게이트를 한 번도 통과하지 못한 채 쌓이는 경우가 있다. 예를 들어 어르신이
        오래 외출하면 인사 제안이 만료된 채 남는다. 큐가 무한히 자라면 게이트가 매
        틱마다 쓸모없는 행을 읽는다.

    반환값
        지운 개수. 로그로 남겨서 "왜 이렇게 많이 버려졌나"를 추적할 수 있게 한다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "DELETE FROM speech_proposal "
        "WHERE senior_id = ? AND expires_at IS NOT NULL AND expires_at < ?",
        (senior_id, clock.now()),
    )
    return cursor.rowcount


def clear(senior_id: str) -> None:
    """이 어르신의 대기 제안을 전부 지운다. 테스트와 운영자 개입용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute("DELETE FROM speech_proposal WHERE senior_id = ?", (senior_id,))


# ─────────────────────────────────────────────────────────────────────────────
# 완료된 슬롯
#
# "9시 복약"처럼 하루 한 번 일어나야 하는 일이 이미 처리됐는지 기록한다.
# 게이트 1(is_still_valid)이 이걸 보고 이미 먹은 약의 알림을 폐기한다.
#
# 왜 백엔드가 아니라 로컬인가
#   사실(복약 기록)은 백엔드 care_record 가 권위다. 여기 있는 것은 '오늘 이 알림을
#   이미 처리했는가'라는 운영 상태이고, 게이트가 매 틱마다 읽는 값이다. 매 틱
#   네트워크를 타면 지연 예산이 무너지고 오프라인에서 죽는다 (CLAUDE.md §5).
# ─────────────────────────────────────────────────────────────────────────────


def mark_slot_completed(senior_id: str, slot_key: str) -> None:
    """이 슬롯이 처리됐다고 표시한다.

    누가 호출하는가
        handlers.handle_schedule. 어르신이 "약 먹었어"라고 말했을 때.

    인자
        slot_key: 하루 안에서 유일한 키. 예: "2026-08-01:med:morning".
            날짜를 포함하는 이유는 어제 완료가 오늘 알림을 막으면 안 되기 때문이다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "INSERT OR REPLACE INTO completed_slot (senior_id, slot_key, completed_at) "
        "VALUES (?, ?, ?)",
        (senior_id, slot_key, clock.now()),
    )


def is_slot_completed(senior_id: str, slot_key: str) -> bool:
    """이 슬롯이 이미 처리됐는가. 게이트 1 이 매 틱 부른다."""
    if not senior_id or not slot_key:
        return False
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT 1 FROM completed_slot WHERE senior_id = ? AND slot_key = ?",
        (senior_id, slot_key),
    ).fetchone()
    return row is not None
