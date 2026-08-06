"""발화 표현 이력 — 같은 알림을 사흘 연속 토씨까지 같게 말하지 않기 위한 저장소.

어디에 위치하는가
    graph/build.py 의 memory_write 가 발화가 확정된 직후 record() 를 부르고,
    graph/context.py 의 context_read 가 다음 능동/명령 턴에서 recent() 를 불러
    state["recent_phrasings"] 를 채운다. 그 값은 prompts/builder.py 의
    "표현 반복 피하기" 섹션으로 들어간다(CLAUDE.md §17.8).

왜 로컬 SQLite 인가
    localstore/proposals.py 와 같은 이유다 — 재부팅을 넘어 살아남아야 하고, 매 턴
    서버 왕복을 하나 더 붙이면 지연 예산(§16)이 무너지고 오프라인에서 죽는다(§5).

무엇을 판단하지 않는가
    "이 origin 이 다양화 대상인가"는 graph/phrasing.phrasing_key 가 이미 판단해서
    빈 문자열/실제 키로 넘겨준다. 이 모듈은 그 결과만 저장·조회할 뿐, 침묵 프로브나
    T3 동의 질문을 알아서 걸러내는 로직을 갖지 않는다 — 그 지식을 두 곳에 두면
    언젠가 어긋난다.

참고
    CLAUDE.md §5(무엇이 로컬에 사는가), §17.8, §18(SD카드 쓰기 절감) / graph/phrasing.py
"""

from __future__ import annotations

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db


def record(senior_id: str, key: str, text: str) -> None:
    """이번에 실제로 한 말을 이력에 남긴다.

    무엇을 하는가
        행을 하나 추가하고, 같은 (senior_id, key) 조합에서 보관 기간
        (policy.RECENT_PHRASING_RETENTION_DAYS)이 지났거나 개수 상한
        (policy.RECENT_PHRASING_MAX_ROWS_PER_KEY)을 넘긴 오래된 행을 함께 지운다.

    왜 기록할 때 같이 정리하는가
        정리만을 위한 별도 틱을 하나 더 만들면 §18 이 이미 아끼려는 microSD 쓰기가
        하나 늘어난다. 기록은 어차피 쓰기가 필요하니, 같은 호출 안에서 정리까지
        끝내면 쓰기 횟수가 늘지 않는다.

    누가 호출하는가
        graph/build.py 의 memory_write, response_shaper 다음, 발화가 최종
        확정된(final_utterance 또는 response) 직후.

    인자
        key: graph/phrasing.phrasing_key(origin, intent) 의 결과. 빈 문자열이면
            (다양화 대상이 아니거나 능동/명령 턴이 아니면) 아무것도 하지 않는다 —
            호출자가 매번 조건문을 반복하지 않아도 된다.
        text: 실제로 나간 문장. build_prompt 가 아니라 최종 발화를 넣는다 —
            모델이 실제로 무슨 말을 했는지가 중요하지, 무엇을 요청했는지가
            아니다.

    주의사항
        이 함수는 예외를 삼키지 않는다. 삼키는 결정은 호출자(memory_write)의
        몫이다 — "기록 실패가 발화를 막으면 안 된다"는 완료 조건은 여기가 아니라
        memory_write 의 try/except 로 지킨다(그래야 대화 기록·checkpoint 등
        memory_write 의 다른 책임과 같은 자리에서 한 번에 보인다).
    """
    if not senior_id or not key or not text:
        return

    connection = runtime_db()
    schema.init_runtime(connection)
    now = clock.now()
    connection.execute(
        "INSERT INTO spoken_phrasing (senior_id, phrasing_key, text, spoken_at) "
        "VALUES (?, ?, ?, ?)",
        (senior_id, key, text, now),
    )

    # 보관 기간 만료. 몇 주 전 표현까지 "피해야 할 표현"으로 들이밀면 그때는
    # 사실상 다시 써도 되는 문구를 억지로 걸러내는 셈이라 오히려 부자연스럽다.
    cutoff = now - policy.RECENT_PHRASING_RETENTION_DAYS * 86400
    connection.execute(
        "DELETE FROM spoken_phrasing WHERE senior_id = ? AND phrasing_key = ? "
        "AND spoken_at < ?",
        (senior_id, key, cutoff),
    )

    # 개수 상한. 보관 기간 안이어도 매일 같은 알림이 나가면 무한정 쌓인다.
    # 가장 최근 N개만 남기고 나머지를 지운다.
    connection.execute(
        "DELETE FROM spoken_phrasing WHERE senior_id = ? AND phrasing_key = ? "
        "AND id NOT IN ("
        "  SELECT id FROM spoken_phrasing WHERE senior_id = ? AND phrasing_key = ? "
        "  ORDER BY spoken_at DESC, id DESC LIMIT ?"
        ")",
        (senior_id, key, senior_id, key, policy.RECENT_PHRASING_MAX_ROWS_PER_KEY),
    )


def recent(senior_id: str, key: str, limit: int | None = None) -> list[str]:
    """이 (어르신, 알림 종류)에서 최근에 쓴 표현을, 오래된 것부터 최신 순으로.

    무엇을 하는가
        같은 key 로 기록된 표현 중 최신 `limit`개를 읽어 시간순으로 뒤집어
        돌려준다. limit 을 안 주면 policy.RECENT_PHRASING_LOOKBACK 을 쓴다.

    왜 오래된 것부터 순서를 뒤집는가
        prompts/builder.py._format_recent_phrasings 는 이 리스트를 그대로 줄줄이
        나열한다. 사람이 "최근 순"보다 "시간 순"으로 나열된 목록을 더 자연스럽게
        읽고, 목록의 마지막 항목(가장 최근 표현)이 모델에게 조금 더 강하게 남는
        효과도 있다.

    누가 호출하는가
        graph/context.py 의 context_read. 능동/명령 턴(trigger_type in
        "proactive"/"backend_command")에서만 부른다 — 반응형 턴에서 이 함수를
        부르면 지난 능동 턴의 speech_origin 이 checkpoint 에 남아 있는 채로 새어
        들어갈 수 있으므로, 그 가드는 이 함수가 아니라 호출하는 쪽(context.py)의
        책임이다.

    인자
        key: graph/phrasing.phrasing_key 의 결과. 비어 있으면 조회할 것이 없다는
            뜻이므로 곧바로 빈 리스트를 돌려준다.

    반환값
        표현 문자열 목록. key 가 비었거나 이력이 없으면 빈 리스트.
    """
    if not senior_id or not key:
        return []

    connection = runtime_db()
    schema.init_runtime(connection)
    n = limit if limit is not None else policy.RECENT_PHRASING_LOOKBACK
    rows = connection.execute(
        "SELECT text FROM spoken_phrasing WHERE senior_id = ? AND phrasing_key = ? "
        "ORDER BY spoken_at DESC, id DESC LIMIT ?",
        (senior_id, key, n),
    ).fetchall()
    return [row["text"] for row in reversed(rows)]


def clear(senior_id: str) -> None:
    """이 어르신의 발화 이력을 전부 지운다. 테스트와 운영자 개입용."""
    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute("DELETE FROM spoken_phrasing WHERE senior_id = ?", (senior_id,))
