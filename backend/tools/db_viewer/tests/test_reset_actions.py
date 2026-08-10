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


# 보호자 화면이 읽는 테이블. 여기 있는 것은 "전량 삭제"여서는 안 되고, 반드시 시드
# 보존 조건을 달아야 한다 (2026-08-10 사용자 조건: "시드는 건들면 안 된다").
SCREEN_VISIBLE_TABLES = ("care_record", "fact_candidate", "memory", "known_person")


@pytest.mark.parametrize("table", SCREEN_VISIBLE_TABLES)
def test_screen_visible_tables_keep_their_seed_rows(table: str) -> None:
    """시드 행(고정 UUID)은 B 로도 지워지지 않는다.

    이 테스트가 없으면 다음 사람이 WHERE 절을 지우고 "전량 삭제"로 바꾸기 쉽다.
    그 순간 복약 시드가 사라져 복약 알림이 아예 울리지 않고, 회상 재료가 사라져
    보미가 어르신에 대해 아무것도 모르는 상태로 시연에 들어간다.
    """
    where = dict(reset_actions.RESIDUE_DELETE_TARGETS)[table]
    assert where is not None, f"{table} 전량 삭제는 시드를 죽인다"
    assert reset_actions.SEED_ID_LIKE in where, (
        f"{table} 의 WHERE 절이 시드 UUID 패턴을 보존하지 않는다: {where}"
    )
    assert "NOT LIKE" in where.upper(), f"{table} 이 시드'만' 지우고 있다 — 조건이 뒤집혔다"


def test_screen_visible_tables_are_actually_delete_targets() -> None:
    """★ 회귀 방지 — 삭제 버튼이 화면을 못 지우던 상태로 돌아가지 않게 한다.

    2026-08-10 이전에는 memory·fact_candidate 가 PROTECTED_TABLES 에 있었고
    care_record 는 온습도 관찰만 지웠다. 그래서 "② 삭제"를 눌러도 확인할 일 3건·
    기억 31건·복약 2건·일정 2건이 그대로 남았다 — 버튼이 하는 일이 화면에 보이지
    않았다. 지키려던 것은 테이블이 아니라 시드였고, 그 구분은 이제 행 단위다.
    """
    targets = {t for t, _ in reset_actions.RESIDUE_DELETE_TARGETS}
    for table in SCREEN_VISIBLE_TABLES:
        assert table in targets, f"{table} 이 삭제 대상에서 빠지면 화면이 안 지워진다"
        assert table not in reset_actions.PROTECTED_TABLES


def test_seed_pattern_matches_the_seed_scripts() -> None:
    """SEED_ID_LIKE 가 실제 시드 스크립트의 UUID 를 잡는지 본다.

    표지가 시드 스크립트와 어긋나면 조용히 시드를 지운다 — 다음 리허설에서야
    "복약이 안 울린다"로 드러나고, 그때는 원인이 여기라는 걸 아무도 모른다.
    """
    seed_dir = REPO_ROOT / "scripts" / "dev"
    fixed_uuid = re.compile(r"'[0-9a-f]{8}-0000-4000-8000-[0-9a-f]{12}'")
    found = 0
    for path in seed_dir.glob("seed-*.sql"):
        found += len(fixed_uuid.findall(path.read_text(encoding="utf-8")))
    assert found > 0, "시드 스크립트에서 고정 UUID 를 하나도 못 찾았다 — 표지가 낡았다"

    core = reset_actions.SEED_ID_LIKE.strip("%")
    assert core == "-0000-4000-8000-", f"표지가 바뀌었다: {reset_actions.SEED_ID_LIKE}"


def test_residue_reset_clears_the_ambient_reading() -> None:
    """온습도는 지울 '행'이 없다 — robot 컬럼이라 UPDATE 로만 비워진다.

    이것이 빠져 있으면 삭제 후에도 "집 안 온도와 습도" 카드가 그대로 남는다.
    """
    labels = " ".join(label for label, _ in reset_actions.RESIDUE_RESET_STEPS)
    statements = " ".join(sql.lower() for _, sql in reset_actions.RESIDUE_RESET_STEPS)
    assert "온습도" in labels
    assert "ambient_temperature_c" in statements
    assert "delete" not in statements, "이 단계는 상태만 되돌린다"


def test_residue_delete_matches_the_canonical_data_script() -> None:
    """B 버튼이 scripts/dev/reset-demo-data.sql 과 같은 테이블을 같은 조건으로 지우는지.

    reset-demo.sql ↔ STATE_RESET_STEPS 와 같은 이유다 — 같은 SQL 이 두 곳에 있으면
    반드시 갈라진다. 갈라짐을 사람의 규율이 아니라 실패로 만든다.
    """
    script = REPO_ROOT / "scripts" / "dev" / "reset-demo-data.sql"
    assert script.exists(), f"정본 SQL 이 없다: {script}"

    body = script.read_text(encoding="utf-8").split("BEGIN;", 1)[1].split("COMMIT;", 1)[0]
    deletes = re.findall(r"delete\s+from\s+(\w+)([^;]*)", _normalize(body))

    ours = [(t, w or None) for t, w in reset_actions.RESIDUE_DELETE_TARGETS]
    theirs = [(t, _normalize(w) or None) for t, w in deletes]

    assert [t for t, _ in ours] == [t for t, _ in theirs], (
        "삭제 대상 테이블·순서가 어긋났다.\n"
        f"reset_actions: {[t for t, _ in ours]}\n스크립트: {[t for t, _ in theirs]}"
    )
    for (table, mine), (_, script_where) in zip(ours, theirs):
        if mine is None:
            assert script_where is None, f"{table}: 여기는 전량 삭제인데 스크립트엔 조건이 있다"
        else:
            assert script_where is not None, f"{table}: 스크립트가 전량 삭제 중이다 — 시드가 죽는다"
            assert _normalize(mine).lstrip("where ") in script_where, (
                f"{table} 의 조건이 다르다.\n여기: {mine}\n스크립트: {script_where}"
            )


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
