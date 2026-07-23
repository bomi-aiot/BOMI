"""Export stable UTF-8 BOM CSV snapshots from the human-maintained BOMI Excel file."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import csv
import io
import sys

from _xlsx_reader import extract_table, read_workbook

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = SCRIPT_DIR.parent / "BOMI_컬럼정의서.xlsx"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "snapshots"

SNAPSHOTS = {
    "tables.csv": ("03_테이블정의", "테이블 ID"),
    "columns.csv": ("04_컬럼정의", "컬럼 ID"),
    "constraints.csv": ("05_관계_제약조건", "제약조건 ID"),
    "indexes.csv": ("06_인덱스정의", "인덱스 ID"),
    "jsonb-fields.csv": ("07_JSONB정의", "JSONB 구조 ID"),
    "vector-fields.csv": ("08_벡터정의", "벡터 정의 ID"),
    "code-values.csv": ("09_코드정의", "코드 그룹 ID"),
    "interface-mappings.csv": ("10_연계매핑", "매핑 ID"),
    "change-history.csv": ("11_변경이력", "문서 버전"),
}


def _normalized_table(sheet_rows: list[list[str]], first_header: str) -> tuple[list[str], list[list[str]]]:
    headers, rows = extract_table(sheet_rows, first_header)
    keep_indexes = [
        index for index, header in enumerate(headers)
        if header not in {"관련 객체 이동", "가이드 이동", "오류 링크"}
    ]
    clean_headers = [headers[index] for index in keep_indexes]
    clean_rows = [[row[index] for index in keep_indexes] for row in rows]

    if first_header == "컬럼 ID":
        table_order = {
            name: rank
            for rank, name in enumerate(
                (
                    "app_user",
                    "care_relationship",
                    "robot",
                    "onboarding_session",
                    "onboarding_answer",
                    "scenario",
                    "conversation",
                    "memory",
                    "care_record",
                    "audit_log",
                )
            )
        }
        table_index = clean_headers.index("테이블 물리명")
        sequence_index = clean_headers.index("컬럼 순번")
        clean_rows.sort(key=lambda row: (table_order.get(row[table_index], 999), int(float(row[sequence_index]))))
    elif first_header == "테이블 ID":
        clean_rows.sort(key=lambda row: row[0])
    elif first_header == "JSONB 구조 ID":
        path_index = clean_headers.index("JSON 경로")
        clean_rows.sort(key=lambda row: (row[0], row[path_index]))
    elif first_header == "코드 그룹 ID":
        order_index = clean_headers.index("표시 순서")
        clean_rows.sort(key=lambda row: (row[0], int(float(row[order_index]))))
    elif first_header == "문서 버전":
        date_index = clean_headers.index("변경일")
        target_index = clean_headers.index("대상 ID")
        clean_rows.sort(key=lambda row: (row[0], row[date_index], row[target_index]))
    else:
        clean_rows.sort(key=lambda row: tuple(row))
    return clean_headers, clean_rows


def render_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def build_snapshots(workbook: Path) -> dict[str, bytes]:
    _, sheets = read_workbook(workbook)
    result: dict[str, bytes] = {}
    for filename, (sheet_name, first_header) in SNAPSHOTS.items():
        if sheet_name not in sheets:
            raise ValueError(f"필수 시트가 없습니다: {sheet_name}")
        headers, rows = _normalized_table(sheets[sheet_name], first_header)
        result[filename] = render_csv(headers, rows)
    return result


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="기존 CSV와 비교만 하고 쓰지 않습니다.")
    args = parser.parse_args()

    snapshots = build_snapshots(args.workbook.resolve())
    mismatches: list[str] = []
    for filename, content in snapshots.items():
        target = args.output_dir.resolve() / filename
        if args.check:
            if not target.exists() or target.read_bytes() != content:
                mismatches.append(filename)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    if args.check and mismatches:
        print("Excel과 일치하지 않는 CSV: " + ", ".join(mismatches), file=sys.stderr)
        return 1
    action = "검증" if args.check else "생성"
    print(f"CSV 스냅샷 {len(snapshots)}개 {action} 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
