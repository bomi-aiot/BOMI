"""로컬(노트북)에서 운영 DB 를 초기화한다 — SSH 터널을 직접 열어서.

왜 이 스크립트가 있나
    운영자가 누르는 것은 DB 뷰어(Streamlit)의 버튼이지만, 그건 서버에 배포된 도커
    이미지다. 코드를 고쳐도 재빌드·재배포 전에는 서버의 버튼이 안 바뀐다. 그 사이에도
    리허설은 계속 돌려야 한다 — 그래서 같은 일을 노트북에서 바로 하는 경로를 둔다.

SQL 은 여기 없다 (중요)
    삭제 대상과 조건은 backend/tools/db_viewer/reset_actions.py 에서 **import 한다.**
    복붙하지 않는다. 같은 SQL 이 세 곳(Streamlit·psql 스크립트·여기)에 흩어지면
    반드시 갈라지고, 갈라진 쪽이 시드를 지우는 날 아무도 원인을 못 찾는다.
    reset_actions ↔ scripts/dev/reset-demo-data.sql 의 동기화는 이미 테스트가 잡는다
    (backend/tools/db_viewer/tests/test_reset_actions.py).

사용법
    cd robot/ai_chat
    ./venv/Scripts/python.exe ../../scripts/dev/reset_demo_data.py            # 미리보기만
    ./venv/Scripts/python.exe ../../scripts/dev/reset_demo_data.py --yes      # 실제 삭제
    ./venv/Scripts/python.exe ../../scripts/dev/reset_demo_data.py --yes --state --robot

    (venv 를 activate 했으면 그냥 `python scripts/dev/reset_demo_data.py`)

의존성
    sshtunnel · paramiko · psycopg2 — robot/ai_chat/venv 에 이미 있다.
    로컬에 psql 은 필요 없다.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend" / "tools" / "db_viewer"))

import reset_actions  # noqa: E402  (경로를 먼저 세워야 import 된다)

ENV_FILE = REPO_ROOT / "robot" / "ai_chat" / ".env"


def _read_env_first_wins(path: Path) -> dict[str, str]:
    """.env 를 읽되 **먼저 나온 비어 있지 않은 값**을 채택한다.

    ★ 왜 dotenv 를 안 쓰나
        이 .env 에는 EC2_HOST·SSH_KEY_PATH·REMOTE_DB_HOST 가 두 번씩 정의돼 있고,
        두 번째 블록이 빈 값이다. dotenv 는 나중 값이 이기므로 그대로 읽으면 호스트가
        빈 문자열이 되어 "SSH 연결 실패"로만 보인다 — 원인이 파일 안에 있다는 걸
        알아채기 어렵다.

        고치는 게 맞지만 남의 로컬 설정 파일이라 여기서 조용히 바꾸지 않는다. 대신
        읽는 쪽에서 방어하고, 아래 _resolve 가 어떤 값을 썼는지 화면에 찍는다.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        # 인라인 주석 제거 (`3 #4 : ...` 같은 줄이 실제로 있다)
        value = raw.split(" #", 1)[0].strip().strip('"').strip("'")
        if value and not values.get(key):
            values[key] = value
    return values


def _resolve(env: dict[str, str], key: str, default: str | None = None) -> str:
    """환경변수 > .env(먼저 나온 값) > 기본값. 어디서 왔는지 함께 알린다."""
    if os.environ.get(key):
        print(f"  {key:16s} = {_mask(key, os.environ[key])}  (환경변수)")
        return os.environ[key]
    if env.get(key):
        print(f"  {key:16s} = {_mask(key, env[key])}  ({ENV_FILE.name})")
        return env[key]
    if default is not None:
        print(f"  {key:16s} = {_mask(key, default)}  (기본값)")
        return default
    raise SystemExit(f"설정 없음: {key} — 환경변수나 {ENV_FILE} 에 넣는다")


def _mask(key: str, value: str) -> str:
    if any(s in key for s in ("PASSWORD", "SECRET", "KEY_PATH")):
        return f"<{len(value)}자>" if "PASSWORD" in key or "SECRET" in key else value
    return value


def _counts(cur, tables: list[str]) -> dict[str, int]:
    out = {}
    for table in tables:
        cur.execute(f"SELECT count(*) FROM {table}")
        out[table] = cur.fetchone()[0]
    return out


def _run(cur, statement: str) -> int:
    cur.execute(statement)
    return cur.rowcount


def reset_robot_localstore() -> None:
    """로봇 로컬 SQLite 의 대화 이어붙이기 상태를 끊는다.

    ★ 왜 DB 만 지우면 안 되나
        백엔드 DB 를 비우면 로봇이 들고 있던 conversation_id 가 서버에 없는 값이 된다.
        로봇은 그걸 계속 붙여 보내고, 백엔드는 매번 400 `unknown conversationId` 로
        거절한다. 그 턴의 발화는 어디에도 기록되지 않고, 화면에는 "아무 일도 없었던
        것"으로 보인다 (2026-08-10 실측). 유휴 경계를 넘기기 전까지 매 턴 반복된다.
    """
    db = REPO_ROOT / "robot" / "ai_chat" / "var" / "localstore" / "runtime.sqlite"
    if not db.exists():
        print(f"  로봇 로컬 저장소 없음 (건너뜀): {db}")
        return
    con = sqlite3.connect(db)
    try:
        checkpoints = con.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
        con.execute("UPDATE runtime_state SET conversation_id = NULL")
        con.execute("DELETE FROM checkpoints")
        con.execute("DELETE FROM writes")
        con.commit()
        print(f"  runtime.sqlite — conversation_id 비움, checkpoints {checkpoints}건 삭제")
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="운영 DB 초기화 (SSH 터널). 기본은 미리보기이고, 실제 삭제는 --yes 가 있어야 한다.",
    )
    parser.add_argument("--yes", action="store_true",
                        help="실제로 실행한다. 없으면 지워질 행 수만 세고 끝난다.")
    parser.add_argument("--state", action="store_true",
                        help="시나리오 상태 리셋도 함께 (SAFE_STOP·고착 시나리오·복약 슬롯·지난 T1).")
    parser.add_argument("--robot", action="store_true",
                        help="로봇 로컬 SQLite 의 conversation_id·checkpoint 도 비운다.")
    parser.add_argument("--data", dest="data", action="store_true", default=None,
                        help="잔여 데이터 삭제 (기본 동작).")
    parser.add_argument("--no-data", dest="data", action="store_false",
                        help="DB 는 건드리지 않는다 (--state 나 --robot 만 쓸 때).")
    args = parser.parse_args()
    do_data = True if args.data is None else args.data

    if args.robot and not (do_data or args.state):
        # DB 접속 없이 로봇만 비우는 경로. 터널을 열 이유가 없다.
        print("로봇 로컬 저장소만 초기화한다.")
        if not args.yes:
            print("  (미리보기 — 실제로 지우려면 --yes)")
            return 0
        reset_robot_localstore()
        return 0

    print("접속 설정")
    env = _read_env_first_wins(ENV_FILE)
    ec2_host = _resolve(env, "EC2_HOST")
    ec2_user = _resolve(env, "EC2_SSH_USER", "ubuntu")
    ssh_key = _resolve(env, "SSH_KEY_PATH")
    remote_host = _resolve(env, "REMOTE_DB_HOST", "localhost")
    remote_port = int(_resolve(env, "REMOTE_DB_PORT", "5432"))
    db_name = _resolve(env, "DB_NAME", "bomi")
    db_user = _resolve(env, "DB_USER", "bomi")
    db_password = _resolve(env, "DB_PASSWORD")

    if not Path(ssh_key).exists():
        raise SystemExit(f"SSH 키가 없다: {ssh_key}")

    import psycopg2
    from sshtunnel import SSHTunnelForwarder

    watched = [t for t, _ in reset_actions.RESIDUE_DELETE_TARGETS]

    print(f"\nSSH 터널 여는 중 — {ec2_user}@{ec2_host} → {remote_host}:{remote_port}")
    with SSHTunnelForwarder(
        (ec2_host, 22),
        ssh_username=ec2_user,
        ssh_pkey=ssh_key,
        remote_bind_address=(remote_host, remote_port),
    ) as tunnel:
        conn = psycopg2.connect(
            host="127.0.0.1", port=tunnel.local_bind_port,
            dbname=db_name, user=db_user, password=db_password,
        )
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                before = _counts(cur, watched)

                print("\n지워질 행 (시드는 제외된 숫자다)")
                total = 0
                for table, where in reset_actions.RESIDUE_DELETE_TARGETS:
                    clause = f" WHERE {where}" if where else ""
                    cur.execute(f"SELECT count(*) FROM {table}{clause}")
                    n = cur.fetchone()[0]
                    total += n
                    kept = before[table] - n
                    mark = f"  (시드 {kept}건 보존)" if where and kept else ""
                    print(f"  {n:>7,}  {table}{mark}")
                print(f"  {total:>7,}  합계")

                if not args.yes:
                    print("\n미리보기만 했다. 실제로 지우려면 --yes 를 붙인다.")
                    conn.rollback()
                    return 0

                if do_data:
                    print("\n삭제 중…")
                    for table, where in reset_actions.RESIDUE_DELETE_TARGETS:
                        clause = f" WHERE {where}" if where else ""
                        n = _run(cur, f"DELETE FROM {table}{clause}")
                        print(f"  {n:>7,}  {table}")
                    for label, statement in reset_actions.RESIDUE_RESET_STEPS:
                        n = _run(cur, statement)
                        print(f"  {n:>7,}  {label}")

                if args.state:
                    print("\n시나리오 상태 리셋…")
                    for label, statement in reset_actions.STATE_RESET_STEPS:
                        n = _run(cur, statement)
                        print(f"  {n:>7,}  {label}")

                conn.commit()

                with conn.cursor() as check:
                    after = _counts(check, watched)
                print("\n결과 (남은 행 = 시드)")
                for table in watched:
                    print(f"  {before[table]:>7,} → {after[table]:<7,}  {table}")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    if args.robot:
        print("\n로봇 로컬 저장소")
        reset_robot_localstore()

    print("\n완료. 보호자 화면은 1~2초 안에 따라온다(폴링).")
    print("온습도는 파이가 켜져 있으면 몇 초 뒤 새 값이 다시 들어온다 — 정상이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
