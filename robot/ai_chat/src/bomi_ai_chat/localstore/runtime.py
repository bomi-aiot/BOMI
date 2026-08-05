"""재부팅을 넘어 살아남아야 하는 운영 상태 읽기·쓰기.

무엇이 여기 사는가
    침묵 사다리의 현재 칸, 재실 상태, 마지막으로 말한 시각, 마지막 상호작용 시각,
    현관 하트비트. 전부 "전원이 끊겼다 들어와도 이어져야 하는" 값이다.

무엇이 여기 살지 '않는가'
    사실(fact)은 오지 않는다. 기억·복약·동의는 백엔드 DB 에 있고 ctx 로 들어온다.
    복약 스케줄의 진실이 두 곳에 있는 것은 품질 문제가 아니라 안전 버그다
    (CLAUDE.md §5).

왜 재부팅 복원이 중요한가
    침묵 사다리가 2단계까지 올라간 상태에서 로봇이 재부팅되면, 복원이 없으면
    사다리가 0 으로 돌아간다. 그러면 응답 없는 어르신에 대한 시계가 처음부터
    다시 흐르고, 에스컬레이션이 그만큼 늦어진다. 안전 기기에서 그건 조용한 실패다.

참고
    CLAUDE.md §5 (소유권), §10 (침묵 사다리), §11 (재실)
"""

from __future__ import annotations

from typing import Any

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db

# 콜드 스타트 기본값.
#
# occupancy 가 HOME 이 아니라 UNKNOWN 인 것이 중요하다. 현관 노드로부터 아직 아무
# 소식도 못 들었는데 집에 있다고 가정하면, 어쩌면 빈 집을 상대로 침묵 사다리가
# 돌아가고 결국 보호자에게 오탐 알림이 간다. 보수적 추정이 UNKNOWN 의 존재 이유다.
_DEFAULTS: dict[str, Any] = {
    "silence_level": 0,
    "occupancy": "UNKNOWN",
    "occupancy_observed_at": 0.0,
    "rest_state": "UNKNOWN",
    "last_spoke_at": 0.0,
    "last_user_interaction_at": 0.0,
    "door_heartbeat_at": 0.0,
    # occupancy 가 AWAY 로 전이한 시각. 0 이면 나가 있지 않다.
    # occupancy_observed_at 과 다르다 — schema.py 의 주석 참고.
    "away_since": 0.0,
    "door_open_since": 0.0,
    # 안전 확인 질문의 마감 시각. 0 이면 대기 중인 확인이 없다 (schema.py 참고).
    "safety_check_until": 0.0,
    # 지금 열려 있는 대화의 id. None 이면 열린 대화가 없다. 스케줄러가 그래프
    # checkpoint 없이 "지금 이 대화"를 읽는 자리다 (S15P11E102-306, schema.py 참고).
    "conversation_id": None,
}

# 외부에서 갱신할 수 있는 필드. 오타가 조용히 무시되지 않도록 화이트리스트로 둔다.
_WRITABLE = frozenset(_DEFAULTS)


def _ensure_row(senior_id: str) -> None:
    """이 어르신의 행이 없으면 기본값으로 만든다."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "INSERT OR IGNORE INTO runtime_state (senior_id, updated_at) VALUES (?, ?)",
        (senior_id, clock.now()),
    )


def load(senior_id: str) -> dict[str, Any]:
    """이 어르신의 운영 상태를 읽는다. 없으면 기본값을 만들어 돌려준다.

    누가 호출하는가
        부트스트랩(재부팅 복원), 침묵 틱, 현관 감시 틱.

    반환값
        ConvState 에 그대로 병합할 수 있는 dict. 키 이름을 ConvState 와 일치시켜서
        호출하는 쪽이 매핑 코드를 쓰지 않게 했다.
    """
    _ensure_row(senior_id)
    row = runtime_db().execute(
        "SELECT * FROM runtime_state WHERE senior_id = ?", (senior_id,)
    ).fetchone()

    # row 가 None 일 수 없다(위에서 만들었다). 그래도 방어하는 대신 명확히 실패한다 —
    # 여기서 None 이면 DB 가 이상한 상태이고, 조용히 기본값을 쓰면 사다리가 초기화된다.
    if row is None:
        raise RuntimeError(f"runtime_state row missing after insert: {senior_id}")

    return {key: row[key] for key in _DEFAULTS}


def save(senior_id: str, **fields: Any) -> None:
    """운영 상태의 일부를 갱신한다.

    무엇을 하는가
        넘긴 필드만 UPDATE 한다. 노드가 반환한 부분 dict 를 그대로 흘려보낼 수 있다.

    누가 호출하는가
        그래프 실행 후의 상태 저장, 그리고 틱들.

    주의사항
        - 알 수 없는 필드는 예외다. 조용히 무시하면 오타 하나 때문에 사다리 값이
          저장되지 않는데도 아무도 모른다.
        - 여기 쓰기는 내구성이 완화되어 있다(db.py). 크래시 시 마지막 몇 초를 잃을 수
          있고 그건 의도된 거래다. 잃으면 안 되는 것은 outbox 로 간다.
    """
    unknown = set(fields) - _WRITABLE
    if unknown:
        raise ValueError(f"unknown runtime_state fields: {sorted(unknown)}")
    if not fields:
        return

    _ensure_row(senior_id)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [*fields.values(), clock.now(), senior_id]
    runtime_db().execute(
        f"UPDATE runtime_state SET {assignments}, updated_at = ? WHERE senior_id = ?",
        values,
    )


def reset_silence(senior_id: str) -> None:
    """사다리를 0 으로 되돌리고 마지막 상호작용 시각을 지금으로 찍는다.

    왜 한 함수인가
        이 두 값은 항상 함께 바뀐다. 어르신이 반응했다는 사실 하나에서 나오는
        결과이므로, 따로 부르게 두면 한쪽만 갱신되는 버그가 생긴다.
        끼어들기(barge-in)도 생존 신호이므로 여기로 온다 (CLAUDE.md §13).

    누가 호출하는가
        graph.ingress.note_interaction. 어르신이 말한 모든 턴에서 부른다 —
        맞장구로 끝나는 턴까지 포함한다. 그것도 생존 증거다.
    """
    save(senior_id, silence_level=0, last_user_interaction_at=clock.now())


# ── 현관 알림 중복 방지 ──────────────────────────────────────────────────────


def mark_door_alert(senior_id: str, alert_key: str) -> bool:
    """이 현관 알림을 '처음 보낸다'면 표시하고 True 를 돌려준다.

    무엇을 하는가
        (senior_id, alert_key) 를 door_alert 에 넣고, 이미 있었으면 False.

    왜 필요한가
        door_watch_tick 은 60초마다 돌고, "부재 6시간 초과"는 그 뒤로 계속 참이다.
        중복 방지가 없으면 매 분 T2 가 쌓여 보호자 화면을 도배하고, 그러면 보호자가
        알림을 읽지 않게 된다. 시끄러운 감지기는 짜증이 아니라 안전 실패다.

    누가 호출하는가
        jobs.ticks.door_watch_tick. 알림을 만들기 '전에' 부르고, False 면 만들지 않는다.

    반환값
        True  -> 새 알림이다. 지금 보내라.
        False -> 이미 보냈다. 아무것도 하지 마라.

    주의사항
        alert_key 에 '상태가 시작된 시각'을 넣는다(schema.py 참고). 날짜를 넣으면
        어르신이 돌아왔다 다시 나가도 그날은 다시 알리지 못한다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    cursor = connection.execute(
        "INSERT OR IGNORE INTO door_alert (senior_id, alert_key, created_at) VALUES (?, ?, ?)",
        (senior_id, alert_key, clock.now()),
    )
    return cursor.rowcount > 0
