"""사실 추출 대기열(localstore/extraction.py) 검증 (S15P11E102-255).

이 파일이 검증하는 것
    1. 큐잉은 LLM 을 부르지 않는 순수 DB 쓰기다.
    2. pending() 은 처리 안 된 행만, 오래된 순으로 돌려준다.
    3. mark_extracted() 이후에는 pending() 에서 빠진다.
    4. 재부팅을 넘어 대기 행이 살아남는다.

참고
    CLAUDE.md §8 (사실 쓰기 경로), §16 (생성 호출 예산)
"""

import pytest

from bomi_ai_chat.localstore import db, extraction

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def test_enqueue_returns_a_row_id(frozen_clock):
    frozen_clock(start=1_700_000_000.0)

    row_id = extraction.enqueue(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        content="요즘 손자가 자주 놀러 와요",
        preceding_robot_utterance="요즘 가족들은 잘 지내세요?",
    )

    assert isinstance(row_id, int)
    assert extraction.pending_count(SENIOR) == 1


def test_pending_returns_oldest_first(frozen_clock):
    sim = frozen_clock(start=1_700_000_000.0)
    extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="첫 번째 발화")
    sim.advance(10)
    extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m2", content="두 번째 발화")

    rows = extraction.pending()

    assert [row["content"] for row in rows] == ["첫 번째 발화", "두 번째 발화"]


def test_pending_respects_the_limit(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    for i in range(3):
        extraction.enqueue(
            SENIOR, conversation_id="c", source_message_id=f"m{i}", content=f"발화 {i}")

    rows = extraction.pending(limit=2)

    assert len(rows) == 2


def test_mark_extracted_removes_the_row_from_pending(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    row_id = extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="기억할 만한 이야기")

    extraction.mark_extracted(row_id)

    assert extraction.pending() == []
    assert extraction.pending_count(SENIOR) == 0


def test_nullable_conversation_and_message_id(frozen_clock):
    """표 자체는 conversation_id/source_message_id 없이도 행을 받는다."""
    frozen_clock(start=1_700_000_000.0)

    extraction.enqueue(
        SENIOR, conversation_id=None, source_message_id=None, content="대화 경계 밖 발화")

    rows = extraction.pending()
    assert rows[0]["conversation_id"] is None
    assert rows[0]["source_message_id"] is None


def test_pending_jobs_survive_a_restart(frozen_clock):
    """재부팅을 흉내내도(db.close_all) 대기 행이 살아남는다."""
    frozen_clock(start=1_700_000_000.0)
    extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="재부팅 전 발화")

    db.close_all()

    assert extraction.pending_count(SENIOR) == 1


def test_clear_removes_all_rows_for_a_senior(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="지울 발화")

    extraction.clear(SENIOR)

    assert extraction.pending_count(SENIOR) == 0


# ── 5. 실패한 행이 큐를 막지 않는다 (S15P11E102-393) ─────────────────────────


def test_a_failed_row_falls_behind_the_ones_never_tried(frozen_clock):
    """★ 앞막힘 방지의 핵심.

    오래된 순으로만 뽑으면 영원히 실패하는 행이 큐 맨 앞을 차지하고, 그 뒤의
    새 발화는 배치 크기만큼 밀려 영영 차례가 오지 않는다. 실패를 적으면 그
    행이 뒤로 물러난다 — 지연이 아니라 정지였던 것이 지연으로 돌아온다.
    """
    sim = frozen_clock(start=1_700_000_000.0)
    old = extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="먼저 온, 실패하는 발화")
    sim.advance(10)
    extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m2", content="나중에 온 발화")

    extraction.record_failure(old)

    assert [row["content"] for row in extraction.pending()] == [
        "나중에 온 발화", "먼저 온, 실패하는 발화"
    ]


def test_rows_with_the_same_failure_count_keep_their_order(frozen_clock):
    """실패 횟수가 같으면 정렬은 예전과 완전히 같다 — 맥락 순서가 흐트러지지 않는다."""
    sim = frozen_clock(start=1_700_000_000.0)
    first = extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="첫 번째 발화")
    sim.advance(10)
    second = extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m2", content="두 번째 발화")

    extraction.record_failure(first)
    extraction.record_failure(second)

    assert [row["content"] for row in extraction.pending()] == [
        "첫 번째 발화", "두 번째 발화"
    ]


def test_a_given_up_row_leaves_the_queue_but_is_not_marked_processed(frozen_clock):
    """포기한 행은 대기 목록에서 빠지되 '처리 완료'(1)로 위장하지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    row_id = extraction.enqueue(
        SENIOR, conversation_id="c", source_message_id="m1", content="서버가 거절하는 발화")

    extraction.mark_given_up(row_id)

    assert extraction.pending() == []
    assert extraction.pending_count(SENIOR) == 0
    stored = db.runtime_db().execute(
        "SELECT extracted FROM extraction_job WHERE id = ?", (row_id,)
    ).fetchone()
    assert stored["extracted"] == 2


def test_a_database_without_the_attempts_column_is_migrated(monkeypatch, tmp_path, frozen_clock):
    """★ 이미 돌고 있던 로봇의 DB 로도 시작할 수 있어야 한다.

    CREATE TABLE IF NOT EXISTS 는 기존 표에 컬럼을 더해주지 않는다. 이관이
    없으면 SELECT * 로 읽는 pending() 이 새 정렬 키를 찾지 못해 죽고, 추출이
    통째로 멈춘다 — 그 사실은 로그 한 줄로만 남는다.
    """
    frozen_clock(start=1_700_000_000.0)

    # attempts 없이 만들어진 옛 표를 흉내 낸다.
    connection = db.runtime_db()
    connection.execute("DROP TABLE IF EXISTS extraction_job")
    connection.execute(
        "CREATE TABLE extraction_job ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, senior_id TEXT NOT NULL,"
        " conversation_id TEXT, source_message_id TEXT, content TEXT NOT NULL,"
        " preceding_robot_utterance TEXT NOT NULL DEFAULT '',"
        " extracted INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)"
    )
    connection.execute(
        "INSERT INTO extraction_job (senior_id, content, extracted, created_at)"
        " VALUES (?, ?, 0, ?)",
        (SENIOR, "이관 전에 쌓여 있던 발화", 1_700_000_000.0),
    )

    rows = extraction.pending()

    assert [row["content"] for row in rows] == ["이관 전에 쌓여 있던 발화"]
    assert rows[0]["attempts"] == 0
