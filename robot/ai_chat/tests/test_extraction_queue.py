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
