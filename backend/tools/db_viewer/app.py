"""DB 실시간 뷰어 — 모든 테이블의 모든 컬럼을 한 화면에 펼쳐 본다.

읽기 전용이다. 연결마다 `default_transaction_read_only` 를 켜고 스키마는
information_schema 에서 매번 새로 읽으므로, 마이그레이션으로 테이블이 늘어도
이 파일은 손대지 않는다.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass

import psycopg
import streamlit as st
from psycopg import sql

EXCLUDED_SCHEMAS = ["pg_catalog", "information_schema"]
# 마이그레이션 관리 테이블은 화면을 차지할 뿐 시연 중에 볼 일이 없다.
EXCLUDED_TABLES = ["flyway_schema_history"]
# 행 정렬에 쓸 컬럼 후보. 앞에 있는 것이 먼저 선택된다.
ORDER_COLUMN_PREFERENCE = (
    "occurred_at",
    "created_at",
    "started_at",
    "updated_at",
    "id",
)


@dataclass(frozen=True)
class TableData:
    schema: str
    name: str
    columns: list[str]
    rows: list[tuple]
    total: int
    order_by: str | None


def _dsn() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'postgres')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(_dsn(), connect_timeout=5, autocommit=True)
    conn.execute("SET default_transaction_read_only = on")
    conn.execute("SET statement_timeout = '10s'")
    return conn


def _fetch_schema(conn: psycopg.Connection) -> dict[tuple[str, str], list[str]]:
    rows = conn.execute(
        """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema <> ALL(%s) AND table_name <> ALL(%s)
        ORDER BY table_schema, table_name, ordinal_position
        """,
        (EXCLUDED_SCHEMAS, EXCLUDED_TABLES),
    ).fetchall()

    schema: dict[tuple[str, str], list[str]] = {}
    for table_schema, table_name, column_name in rows:
        schema.setdefault((table_schema, table_name), []).append(column_name)
    return schema


def _fetch_table(
    conn: psycopg.Connection,
    table_schema: str,
    table_name: str,
    columns: list[str],
    limit: int,
) -> TableData:
    ident = sql.Identifier(table_schema, table_name)
    total = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(ident)).fetchone()[0]

    order_by = next((c for c in ORDER_COLUMN_PREFERENCE if c in columns), None)
    query = sql.SQL("SELECT * FROM {}").format(ident)
    if order_by is not None:
        query = sql.SQL("{} ORDER BY {} DESC NULLS LAST").format(
            query, sql.Identifier(order_by)
        )
    query = sql.SQL("{} LIMIT {}").format(query, sql.Literal(limit))

    cursor = conn.execute(query)
    return TableData(
        schema=table_schema,
        name=table_name,
        columns=[d.name for d in cursor.description],
        rows=cursor.fetchall(),
        total=total,
        order_by=order_by,
    )


def _cell(value: object, max_chars: int) -> str:
    if value is None:
        return '<span class="null">·</span>'
    text = str(value)
    # 임베딩 벡터처럼 수천 자짜리 값 하나가 표 전체를 밀어내는 것을 막는다.
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return html.escape(text)


def _render_table(table: TableData, max_chars: int) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in table.columns)
    if table.rows:
        body = "".join(
            "<tr>" + "".join(f"<td>{_cell(v, max_chars)}</td>" for v in row) + "</tr>"
            for row in table.rows
        )
    else:
        body = f'<tr><td colspan="{len(table.columns)}" class="empty">(비어 있음)</td></tr>'

    order_note = f" · ↓{table.order_by}" if table.order_by else ""
    caption = (
        f"<div class='cap'><b>{html.escape(table.name)}</b> "
        f"<span class='meta'>{len(table.rows)}/{table.total}행 · "
        f"{len(table.columns)}컬럼{html.escape(order_note)}</span></div>"
    )
    return f"{caption}<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


# ★ `%` 서식이 아니라 문자열 치환을 쓴다. CSS 안에 `width: 100%;` 같은 리터럴 `%` 가
#   있어서 `CSS % {...}` 는 "unsupported format character ';'" 로 죽는다.
CSS = """
<style>
.block-container { padding: 0.6rem 0.8rem 2rem; max-width: 100%; }
.dbv table {
  width: 100%; table-layout: fixed; border-collapse: collapse;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: __FONT__px; line-height: 1.25; margin: 0 0 0.9rem;
}
.dbv th, .dbv td {
  border: 1px solid #d6dbe3; padding: 1px 3px;
  overflow-wrap: anywhere; word-break: break-all; vertical-align: top;
}
.dbv th { background: #eef2f8; font-weight: 600; text-align: left; }
.dbv tbody tr:nth-child(even) td { background: #fafbfd; }
.dbv .null { color: #b6bdc9; }
.dbv .empty { color: #9aa3b0; text-align: center; font-style: italic; }
.dbv .cap { font-size: __CAP__px; margin: 0.5rem 0 0.15rem; }
.dbv .cap .meta { color: #6b7480; font-weight: 400; }
</style>
"""


def main() -> None:
    st.set_page_config(page_title="BOMI DB 실시간 뷰어", layout="wide")

    with st.sidebar:
        st.markdown("### 표시 설정")
        interval = st.select_slider(
            "자동 새로고침", options=[0, 2, 5, 10, 30, 60], value=5,
            format_func=lambda s: "끔" if s == 0 else f"{s}초",
        )
        rows = st.slider("테이블당 행 수", 1, 50, 8)
        font = st.slider("글자 크기(px)", 5, 14, 8)
        max_chars = st.slider("셀 최대 글자 수", 8, 200, 48)
        st.caption("컬럼은 화면 폭에 맞춰 접힌다 — 가로 스크롤 없음.")

    css = CSS.replace("__FONT__", str(font)).replace("__CAP__", str(font + 4))
    st.markdown(css, unsafe_allow_html=True)

    @st.fragment(run_every=interval if interval else None)
    def board() -> None:
        try:
            with _connect() as conn:
                # 조회 시각은 DB 의 now() 를 쓴다. 컨테이너 TZ 에 흔들리지 않고,
                # "화면이 살아 있는지"를 이 값 하나로 판정할 수 있다.
                fetched_at = conn.execute("SELECT now()").fetchone()[0]
                schema = _fetch_schema(conn)
                tables = [
                    _fetch_table(conn, s, t, cols, rows)
                    for (s, t), cols in sorted(schema.items())
                ]
        except psycopg.Error as exc:
            st.error(f"DB 연결/조회 실패: {exc}")
            return

        st.caption(
            f"조회 {fetched_at:%H:%M:%S} · {len(tables)}개 테이블 · "
            f"총 {sum(t.total for t in tables):,}행"
            + (f" · {interval}초마다 갱신" if interval else " · 자동 갱신 꺼짐")
        )
        body = "".join(_render_table(t, max_chars) for t in tables)
        st.markdown(f"<div class='dbv'>{body}</div>", unsafe_allow_html=True)

    board()


if __name__ == "__main__":
    main()
