"""reset_actions 가 정본(scripts/dev/reset-demo.sql)에서 갈라지지 않도록 붙잡는다.

이 테스트가 존재하는 이유는 하나다 — 같은 SQL 이 두 곳에 있기 때문이다. 도커 빌드
컨텍스트 제약으로 파일을 공유할 수 없으니, 대신 갈라짐을 실패로 만든다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reset_actions  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_SQL = REPO_ROOT / "scripts" / "dev" / "reset-demo.sql"


def _normalize(sql: str) -> str:
    """주석·공백·대소문자 차이를 지우고 문장 알맹이만 남긴다."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"\s+", " ", sql).strip().lower().rstrip(";")


def _canonical_statements() -> list[str]:
    text = CANONICAL_SQL.read_text(encoding="utf-8")
    # BEGIN 과 COMMIT 사이의 본문만 본다. 아래 (선택) DELETE 주석은 대상이 아니다.
    body = text.split("BEGIN;", 1)[1].split("COMMIT;", 1)[0]
    return [_normalize(s) for s in body.split(";") if _normalize(s)]


def test_canonical_script_is_present() -> None:
    assert CANONICAL_SQL.exists(), f"정본 SQL 이 없다: {CANONICAL_SQL}"


def test_state_reset_matches_the_canonical_script() -> None:
    """A 버튼의 네 문장이 reset-demo.sql 과 글자 단위로 같은 일을 하는지 본다."""
    canonical = _canonical_statements()
    ours = [_normalize(sql) for _, sql in reset_actions.STATE_RESET_STEPS]

    assert ours == canonical, (
        "reset_actions.STATE_RESET_STEPS 가 scripts/dev/reset-demo.sql 과 어긋났다.\n"
        f"정본 {len(canonical)}문장 / 여기 {len(ours)}문장\n"
        f"정본: {canonical}\n여기: {ours}"
    )


def test_state_reset_never_deletes() -> None:
    for _, sql in reset_actions.STATE_RESET_STEPS:
        assert "delete" not in sql.lower(), "A 는 상태만 바꾼다 — DELETE 가 있으면 안 된다"
        assert "drop" not in sql.lower()
        assert "truncate" not in sql.lower()


@pytest.mark.parametrize("table", sorted(reset_actions.PROTECTED_TABLES))
def test_protected_tables_are_never_delete_targets(table: str) -> None:
    targets = {t for t, _ in reset_actions.RESIDUE_DELETE_TARGETS}
    assert table not in targets


def test_memory_and_facts_are_protected() -> None:
    """2026-08-10 사용자 승인 조건 — 어르신 기억은 B 로도 지우지 않는다."""
    assert "memory" in reset_actions.PROTECTED_TABLES
    assert "fact_candidate" in reset_actions.PROTECTED_TABLES


def test_medication_seed_rows_survive_residue_delete() -> None:
    """care_record 는 전량 삭제가 아니라 온습도 관찰만 지운다.

    MEDICATION / MEDICATION_SCHEDULE 이 사라지면 복약 알림이 아예 울리지 않는다.
    """
    where = dict(reset_actions.RESIDUE_DELETE_TARGETS)["care_record"]
    assert where is not None, "care_record 전량 삭제는 복약 시드를 죽인다"
    assert "ENVIRONMENT_OBSERVATION" in where


def test_conversation_children_are_deleted_with_their_parent() -> None:
    """FK 가 없으므로 부모만 지우면 고아가 남는다 — 셋이 같이 있어야 한다."""
    targets = {t for t, _ in reset_actions.RESIDUE_DELETE_TARGETS}
    assert {"conversation", "conversation_message", "conversation_summary"} <= targets


def test_assert_targets_are_safe_rejects_a_protected_table(monkeypatch) -> None:
    monkeypatch.setattr(
        reset_actions, "RESIDUE_DELETE_TARGETS", (("app_user", None),), raising=True
    )
    with pytest.raises(AssertionError, match="보호 테이블"):
        reset_actions._assert_targets_are_safe()
