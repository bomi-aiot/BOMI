"""로봇 로컬 상태를 한 눈에 찍는다 — 실기 점검에서 '실제'를 채우는 도구.

어디에 위치하는가
    실기 점검(docs/carebot/FIELD-TEST-233.md)의 매 스텝에서 부른다. 어르신이 한 마디
    하기 '전'에 --save 로 사진을 찍어두고, 말한 '뒤'에 --diff 로 무엇이 바뀌었는지
    본다. 문서가 "DB 가 이렇게 바뀝니다"라고 주장하는 대신, 이 도구가 실제로 바뀐
    것을 보여준다.

왜 존재하는가
    이 도구가 없으면 점검자는 발화 하나마다 창 네 개(로그·SQLite·백엔드 로그·psql)를
    눈으로 훑어야 한다. 그러면 대조가 손으로 이뤄지고, 손으로 하는 대조는 바쁠 때
    가장 먼저 생략된다. 생략된 대조는 '확인했다'로 기록된다.

왜 bomi_ai_chat 을 import 하지 않는가
    이 도구는 런타임이 '망가졌을 때' 가장 필요하다. 패키지를 import 하면 설정 검증
    (config.Settings)이 걸리고, .env 가 잘못됐다는 이유로 진단 도구까지 죽는다.
    그래서 SQLite 파일을 경로로 직접 연다. 대신 표·칼럼 이름이 localstore/schema.py
    와 어긋날 수 있으므로, 없는 표는 조용히 건너뛰지 않고 '표 없음'으로 찍는다.

사용법
    python tests/manual/probe.py                    지금 상태
    python tests/manual/probe.py --save             스냅샷 저장 (말하기 전)
    python tests/manual/probe.py --diff             스냅샷 대비 변화 (말한 뒤)
    python tests/manual/probe.py --diff --step 5-12 제목에 스텝 번호를 붙인다
    python tests/manual/probe.py --reset-ladder     침묵 사다리와 대기 제안만 초기화

참고
    CLAUDE.md §5 (사실은 백엔드 / 운영 상태는 로봇), §15 (시계 주입)
    docs/carebot/FIELD-TEST-233.md
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

# ── 어디를 읽는가 ────────────────────────────────────────────────────────────
#
# 로봇의 운영 상태는 파일 두 개로 나뉘어 있다. 나뉜 이유는 SQLite 의 synchronous
# 설정이 '파일 단위'이기 때문이다. 보호자 알림만 동기 쓰기(한 건도 잃으면 안 됨)로
# 두려면 파일을 분리하는 것 말고는 방법이 없었다 (localstore/db.py 참고).
RUNTIME_DB = "runtime.sqlite"   # 재실·사다리·제안·문맥 캐시 + LangGraph 대화 저장점
OUTBOX_DB = "outbox.sqlite"     # 보호자 알림 발신 큐. 이것만 동기 쓰기다

SNAPSHOT_NAME = "probe-snapshot.json"

# 초 단위 실수(epoch)로 저장된 칼럼들. 사람이 두 값을 비교할 수 있도록 시:분:초로
# 바꿔서 보여준다. 1786412621.0 과 1786412683.0 을 눈으로 비교하는 것은 불가능하다.
_EPOCH_COLUMNS = frozenset({
    "occupancy_observed_at",
    "last_spoke_at",
    "last_user_interaction_at",
    "door_heartbeat_at",
    "away_since",
    "door_open_since",
    "safety_check_until",
    "updated_at",
    "created_at",
    "expires_at",
    "not_before",
})


# ── 출력 폭 맞추기 ───────────────────────────────────────────────────────────


def _width(text: str) -> int:
    """터미널에서 이 문자열이 차지하는 칸 수.

    왜 len() 으로 부족한가
        한글은 터미널에서 두 칸을 차지한다. len() 으로 자리를 맞추면 한글이 섞인
        칼럼만 밀려서 표가 어긋나고, 그러면 '눈으로 비교하라'는 이 도구의 목적이
        무너진다.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    """터미널 표시 폭 기준으로 오른쪽을 공백으로 채운다."""
    return text + " " * max(0, width - _width(text))


# ── 값 읽기와 표시 ───────────────────────────────────────────────────────────


def _fmt(column: str, value: Any) -> str:
    """한 칸의 값을 사람이 읽을 수 있게 바꾼다."""
    if value is None:
        return "(없음)"
    if column in _EPOCH_COLUMNS:
        # 0 은 '아직 그런 일이 없었다'는 뜻이다. 1970년으로 찍으면 오히려 헷갈린다.
        if not value:
            return "0"
        try:
            return time.strftime("%H:%M:%S", time.localtime(float(value)))
        except (TypeError, ValueError, OSError):
            return str(value)
    return str(value)


def _localstore_dir() -> Path:
    """운영 상태가 사는 디렉터리. .env 의 LOCALSTORE_DIR 과 같은 기본값을 쓴다."""
    return Path(os.environ.get("LOCALSTORE_DIR", "var/localstore"))


def _open(path: Path) -> sqlite3.Connection | None:
    """읽기 전용으로 연다. 없으면 None.

    왜 읽기 전용인가
        로봇이 돌고 있는 중에 이 도구를 부르는 것이 정상 사용이다. 진단 도구가
        점검 대상의 상태를 바꾸면, 그때부터 무엇이 로봇이 한 일이고 무엇이 도구가
        한 일인지 구분할 수 없다.
    """
    if not path.exists():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(connection: sqlite3.Connection | None, sql: str) -> list[dict[str, Any]] | None:
    """질의 결과를 dict 목록으로. 표가 없으면 None (빈 목록과 구분한다).

    왜 None 과 [] 를 구분하는가
        '표가 아예 없다'(스키마가 안 만들어졌다)와 '표는 있는데 행이 0개다'는 전혀
        다른 상황이다. 앞은 로봇이 한 번도 안 떴다는 뜻이고, 뒤는 정상이다.
    """
    if connection is None:
        return None
    try:
        return [dict(row) for row in connection.execute(sql)]
    except sqlite3.OperationalError:
        return None


# ── 상태 수집 ────────────────────────────────────────────────────────────────


def collect() -> dict[str, Any]:
    """지금 로컬 상태를 통째로 읽어 온다. 스냅샷과 비교에 같은 함수를 쓴다."""
    base = _localstore_dir()
    runtime = _open(base / RUNTIME_DB)
    outbox = _open(base / OUTBOX_DB)

    state: dict[str, Any] = {
        "taken_at": time.time(),
        "localstore_dir": str(base),
        "runtime_db_exists": runtime is not None,
        "outbox_db_exists": outbox is not None,
        "runtime_state": _rows(runtime, "SELECT * FROM runtime_state"),
        "speech_proposal": _rows(
            runtime, "SELECT * FROM speech_proposal ORDER BY created_at, id"),
        "outbox": _rows(
            outbox,
            "SELECT id, tier, status, attempt_count, delayed, last_error "
            "FROM outbox ORDER BY id DESC LIMIT 10"),
    }

    # 문맥 캐시는 내용이 크므로 '있는지와 얼마나 낡았는지'만 본다. 여기서 캐시가
    # 오래됐다면 백엔드에 못 닿고 있다는 뜻이고, 그러면 로봇의 기억이 얕아진다.
    cache = _rows(runtime, "SELECT senior_id, updated_at FROM context_cache")
    state["context_cache"] = cache

    for connection in (runtime, outbox):
        if connection is not None:
            connection.close()
    return state


def _runtime_row(state: dict[str, Any], senior_id: str | None) -> dict[str, Any]:
    """어르신 한 명의 runtime_state 행. 여러 명이면 지정한 사람, 아니면 첫 행."""
    rows = state.get("runtime_state") or []
    if not rows:
        return {}
    if senior_id:
        for row in rows:
            if row.get("senior_id") == senior_id:
                return row
    return rows[0]


# ── 로그에서 마지막 턴 읽기 ──────────────────────────────────────────────────


def _last_turn_line() -> str | None:
    """로그에서 마지막 `turn latency` 줄을 찾는다.

    왜 로그를 읽는가
        인텐트와 지연은 DB 에 남지 않는다. 남길 이유도 없다(운영 상태가 아니라 그
        턴의 관찰값이다). 그래서 판정에 필요한 이 두 값만 로그에서 꺼내 온다.

    주의사항
        로그 설정이 꺼져 있으면 파일 자체가 없다. 그때 조용히 넘어가면 점검자는
        '인텐트가 안 나온다'를 코드 결함으로 오해한다. 호출부에서 안내를 찍는다.
    """
    log = _localstore_dir() / "logs" / "ai_chat.log"
    if not log.exists():
        return None
    found = None
    # 로그가 20MB 까지 커질 수 있으므로 통째로 읽지 않고 끝부분만 본다.
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "turn latency" in line:
                found = line.rstrip()
    return found


def _recent_warnings(limit: int = 5) -> list[str]:
    """최근 경고·오류 줄. '왜 안 되지'의 답이 대개 여기 있다."""
    log = _localstore_dir() / "logs" / "ai_chat.log"
    if not log.exists():
        return []
    hits: list[str] = []
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if " WARNING " in line or " ERROR " in line:
                hits.append(line.rstrip())
    return hits[-limit:]


# ── 표 그리기 ────────────────────────────────────────────────────────────────

_HEADER = ("표", "칼럼", "이전", "이후", "판정")
_WIDTHS = (16, 27, 13, 13, 6)


def _table(rows: list[tuple[str, str, str, str, str]]) -> str:
    """다섯 칸짜리 표를 문자열로. 문서의 「예상」 표와 칼럼이 같아야 한다."""
    out = [
        "".join(_pad(h, w) for h, w in zip(_HEADER, _WIDTHS)),
        "".join("-" * (w - 1) + " " for w in _WIDTHS),
    ]
    for row in rows:
        out.append("".join(_pad(c, w) for c, w in zip(row, _WIDTHS)))
    return "\n".join(out)


def _verdict(before: str, after: str) -> str:
    return "유지" if before == after else "변함"


def _compare_runtime(
    old: dict[str, Any], new: dict[str, Any]
) -> list[tuple[str, str, str, str, str]]:
    """runtime_state 두 행을 칼럼별로 나란히 놓는다."""
    columns = list(new.keys()) or list(old.keys())
    rows = []
    for column in columns:
        if column == "senior_id":
            continue
        rows.append((
            "runtime_state",
            column,
            _fmt(column, old.get(column)),
            _fmt(column, new.get(column)),
            _verdict(_fmt(column, old.get(column)), _fmt(column, new.get(column))),
        ))
    return rows


def _count_row(
    label: str, old: list | None, new: list | None
) -> tuple[str, str, str, str, str]:
    """행 수만 비교하는 표 한 줄 (제안 큐, 발신 큐)."""
    before = "(표 없음)" if old is None else str(len(old))
    after = "(표 없음)" if new is None else str(len(new))
    return (label, "(행 수)", before, after, _verdict(before, after))


# ── 출력 ─────────────────────────────────────────────────────────────────────


def _print_header(title: str, state: dict[str, Any], senior_id: str | None) -> None:
    line = "=" * 78
    print(line)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["taken_at"]))
    print(f" {title}{' ' * max(1, 60 - _width(title))}{stamp}")
    who = senior_id or (_runtime_row(state, None).get("senior_id") or "(없음)")
    print(f" senior = {who}")
    print(f" LOCALSTORE_DIR = {state['localstore_dir']}")
    print(line)


def _print_lists(state: dict[str, Any], senior_id: str | None) -> None:
    """대기 중인 제안과 발신 큐를 펼쳐서 보여준다."""
    print()
    print("speech_proposal  (대기 중인 제안 — 아직 발화가 아니다)")
    proposals = state.get("speech_proposal")
    if proposals is None:
        print("  (표 없음 — 로봇이 한 번도 안 떴습니다)")
    elif not proposals:
        print("  (없음)")
    else:
        for row in proposals:
            if senior_id and row.get("senior_id") != senior_id:
                continue
            print(f"  intent={row.get('intent')}  priority={row.get('priority')}  "
                  f"seed={row.get('seed')!r}")

    print()
    print("outbox           (보호자 알림 발신 큐 — 여기 쌓이면 알림이 나갑니다)")
    outbox = state.get("outbox")
    if outbox is None:
        print("  (표 없음)")
    elif not outbox:
        print("  (없음)")
    else:
        for row in outbox:
            flag = "  <-- T1 은 포기하지 않아야 합니다" if (
                row.get("tier") == "T1" and row.get("status") == "GAVE_UP") else ""
            print(f"  #{row.get('id')}  tier={row.get('tier')}  "
                  f"status={row.get('status')}  attempts={row.get('attempt_count')}"
                  f"{flag}")
            if row.get("last_error"):
                print(f"        last_error={row.get('last_error')}")


def _print_log_tail() -> None:
    """마지막 턴과 최근 경고. 인텐트·지연은 DB 가 아니라 여기서 온다."""
    print()
    print("마지막 턴  (logs/ai_chat.log)")
    line = _last_turn_line()
    if line is None:
        print("  (로그 파일이 없습니다 — -v 없이 띄웠거나 로깅이 꺼져 있습니다)")
    else:
        print(f"  {line}")

    warnings = _recent_warnings()
    if warnings:
        print()
        print("최근 경고·오류")
        for entry in warnings:
            print(f"  {entry}")


def show_now(senior_id: str | None, step: str | None) -> None:
    """지금 상태만 보여준다 (--diff 없이 부른 경우)."""
    state = collect()
    title = f"BOMI 로봇 로컬 상태{f'  [{step}]' if step else ''}"
    _print_header(title, state, senior_id)
    row = _runtime_row(state, senior_id)
    if not row:
        print()
        print("runtime_state 에 행이 없습니다. 로봇이 아직 한 번도 안 떴거나,")
        print("LOCALSTORE_DIR 이 다른 곳을 가리키고 있습니다.")
    else:
        print()
        rows = [
            ("runtime_state", column, "-", _fmt(column, value), "-")
            for column, value in row.items() if column != "senior_id"
        ]
        print(_table(rows))
    _print_lists(state, senior_id)
    _print_log_tail()


def save(senior_id: str | None) -> None:
    """지금 상태를 스냅샷 파일로 남긴다 (말하기 '전'에 부른다)."""
    state = collect()
    path = _localstore_dir() / SNAPSHOT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    stamp = time.strftime("%H:%M:%S", time.localtime(state["taken_at"]))
    print(f"스냅샷 저장 {stamp}  ->  {path}")
    row = _runtime_row(state, senior_id)
    if row:
        print(f"  occupancy={row.get('occupancy')}  "
              f"silence_level={row.get('silence_level')}  "
              f"safety_check_until={_fmt('safety_check_until', row.get('safety_check_until'))}")
    print("이제 말씀하시고, 끝나면 --diff 를 부르십시오.")


def diff(senior_id: str | None, step: str | None) -> int:
    """스냅샷 이후 무엇이 바뀌었는지 (말한 '뒤'에 부른다)."""
    path = _localstore_dir() / SNAPSHOT_NAME
    if not path.exists():
        print(f"스냅샷이 없습니다: {path}")
        print("먼저 --save 를 부르십시오. 말하기 '전'에 찍어야 비교가 됩니다.")
        return 1

    old = json.loads(path.read_text(encoding="utf-8"))
    new = collect()

    title = f"스냅샷 이후 변화{f'  [{step}]' if step else ''}"
    _print_header(title, new, senior_id)
    before = time.strftime("%H:%M:%S", time.localtime(old["taken_at"]))
    after = time.strftime("%H:%M:%S", time.localtime(new["taken_at"]))
    print(f" 스냅샷 {before}  ->  지금 {after}")
    print("=" * 78)
    print()

    rows = _compare_runtime(_runtime_row(old, senior_id), _runtime_row(new, senior_id))
    rows.append(_count_row(
        "speech_proposal", old.get("speech_proposal"), new.get("speech_proposal")))
    rows.append(_count_row("outbox", old.get("outbox"), new.get("outbox")))
    print(_table(rows))

    changed = sum(1 for row in rows if row[4] == "변함")
    print()
    print(f"바뀐 칸 {changed}개 / 전체 {len(rows)}개")

    _print_lists(new, senior_id)
    _print_log_tail()
    print()
    print("이 출력을 그대로 FIELD-TEST-233-RESULT.md 의 해당 스텝에 붙여넣으십시오.")
    return 0


def reset_ladder(senior_id: str | None) -> int:
    """침묵 사다리와 대기 제안만 초기화한다 (점검 뒤 되돌리기용).

    무엇을 건드리는가
        runtime_state.silence_level -> 0, speech_proposal 의 해당 어르신 행 삭제.
        재실·마지막 발화 시각·발신 큐는 '건드리지 않는다' — 그것까지 지우면 점검이
        남긴 증거가 사라진다.
    """
    if not senior_id:
        print("--reset-ladder 에는 --senior 가 필요합니다 (누구의 상태인지 특정해야 합니다).")
        return 1
    path = _localstore_dir() / RUNTIME_DB
    if not path.exists():
        print(f"{path} 가 없습니다.")
        return 1
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "UPDATE runtime_state SET silence_level = 0 WHERE senior_id = ?", (senior_id,))
        deleted = connection.execute(
            "DELETE FROM speech_proposal WHERE senior_id = ?", (senior_id,)).rowcount
    connection.close()
    print(f"사다리를 0 으로 되돌리고 대기 제안 {deleted}건을 지웠습니다.")
    print("재실·마지막 발화 시각·발신 큐는 그대로 두었습니다.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="로봇 로컬 상태를 찍는다. 실기 점검에서 '실제' 칸을 채우는 도구.")
    parser.add_argument("--save", action="store_true",
                        help="지금 상태를 스냅샷으로 저장한다 (말하기 전).")
    parser.add_argument("--diff", action="store_true",
                        help="스냅샷 이후 바뀐 것을 보여준다 (말한 뒤).")
    parser.add_argument("--step", help="제목에 붙일 스텝 번호 (예: 5-12).")
    parser.add_argument("--senior", default=os.environ.get("SENIOR_ID"),
                        help="어르신 UUID. 기본값은 환경변수 SENIOR_ID.")
    parser.add_argument("--reset-ladder", action="store_true",
                        help="침묵 사다리와 대기 제안만 초기화한다 (점검 뒤 되돌리기).")
    args = parser.parse_args(argv)

    # Windows 콘솔이 cp949 로 열리면 한글 출력에서 죽는다. 진단 도구가 인코딩 때문에
    # 죽으면, 점검하러 가서 점검 도구부터 고쳐야 한다 (233 에서 실제로 겪었다).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.reset_ladder:
        return reset_ladder(args.senior)
    if args.save:
        save(args.senior)
        return 0
    if args.diff:
        return diff(args.senior, args.step)
    show_now(args.senior, args.step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
