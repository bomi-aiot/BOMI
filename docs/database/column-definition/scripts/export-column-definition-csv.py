"""Export stable UTF-8 BOM CSV snapshots from the human-maintained BOMI workbook."""

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
    "tables.csv": ("01_테이블정의", "테이블명"),
    "columns.csv": ("02_컬럼정의", "테이블명"),
    "constraints.csv": ("03_관계_제약조건", "이름"),
    "indexes.csv": ("04_인덱스정의", "인덱스명"),
    "jsonb-fields.csv": ("05_JSONB정의", "대상 컬럼"),
    "vector-fields.csv": ("06_벡터정의", "대상 컬럼"),
    "code-values.csv": ("07_코드정의", "대상"),
    "interface-mappings.csv": ("08_연계매핑", "계약 필드"),
    "change-history.csv": ("09_변경이력", "변경일"),
}


def render_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def build_snapshots(workbook: Path) -> dict[str, bytes]:
    """Build snapshots in the same meaningful order shown in the workbook."""
    _, sheets = read_workbook(workbook)
    result: dict[str, bytes] = {}
    for filename, (sheet_name, first_header) in SNAPSHOTS.items():
        if sheet_name not in sheets:
            raise ValueError(f"필수 시트가 없습니다: {sheet_name}")
        headers, rows = extract_table(sheets[sheet_name], first_header)
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
