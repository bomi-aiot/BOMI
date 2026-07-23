"""Validate the BOMI workbook structure, source coverage, CSV parity, and encoding."""

from __future__ import annotations

from pathlib import Path
from argparse import ArgumentParser
from tempfile import TemporaryDirectory
import csv
import hashlib
import io
import re
import subprocess
import sys
import importlib.util
from zipfile import BadZipFile, ZipFile

from _xlsx_reader import duplicate_values, extract_table, read_workbook

_exporter_path = Path(__file__).resolve().parent / "export-column-definition-csv.py"
_exporter_spec = importlib.util.spec_from_file_location("bomi_csv_exporter", _exporter_path)
if _exporter_spec is None or _exporter_spec.loader is None:
    raise RuntimeError(f"CSV exporter를 불러올 수 없습니다: {_exporter_path}")
_exporter = importlib.util.module_from_spec(_exporter_spec)
_exporter_spec.loader.exec_module(_exporter)
build_snapshots = _exporter.build_snapshots

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WORKBOOK = ROOT / "BOMI_컬럼정의서.xlsx"
SNAPSHOT_DIR = ROOT / "snapshots"
EXPECTED_SHEETS = [
    "00_유지보수가이드", "01_문서정보", "02_용어집", "03_테이블정의", "04_컬럼정의", "05_관계_제약조건",
    "06_인덱스정의", "07_JSONB정의", "08_벡터정의", "09_코드정의", "10_연계매핑", "11_변경이력", "12_검증결과", "99_입력목록",
]
EXPECTED_TABLES = ["app_user", "care_relationship", "robot", "onboarding_session", "onboarding_answer", "scenario", "conversation", "memory", "care_record", "audit_log"]
EXPECTED_COLUMN_COUNTS = {
    "app_user": 24,
    "care_relationship": 10,
    "robot": 21,
    "onboarding_session": 14,
    "onboarding_answer": 32,
    "scenario": 39,
    "conversation": 27,
    "memory": 27,
    "care_record": 35,
    "audit_log": 9,
}
EXPECTED_COLUMN_TOTAL = sum(EXPECTED_COLUMN_COUNTS.values())
EXPECTED_WARNING_COUNT = 15
SNAPSHOT_NAMES = ["tables.csv", "columns.csv", "constraints.csv", "indexes.csv", "jsonb-fields.csv", "vector-fields.csv", "code-values.csv", "interface-mappings.csv", "change-history.csv"]


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    args = parser.parse_args()
    workbook_path = args.workbook.resolve()
    snapshot_dir = args.snapshot_dir.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        with ZipFile(workbook_path) as archive:
            if archive.testzip() is not None:
                fail("XLSX ZIP 내부 CRC 오류", errors)
    except (FileNotFoundError, BadZipFile) as exc:
        print(f"ERROR: Excel을 열 수 없습니다: {exc}", file=sys.stderr)
        return 1

    sheet_order, sheets = read_workbook(workbook_path)
    if sheet_order != EXPECTED_SHEETS:
        fail(f"시트 순서 불일치: {sheet_order}", errors)

    table_headers, table_rows = extract_table(sheets["03_테이블정의"], "테이블 ID")
    table_name_index = table_headers.index("테이블 물리명")
    actual_tables = [row[table_name_index] for row in table_rows]
    if actual_tables != EXPECTED_TABLES:
        fail(f"기준 테이블 불일치: {actual_tables}", errors)
    if duplicate_values(row[0] for row in table_rows):
        fail("중복 테이블 ID", errors)

    column_headers, column_rows = extract_table(sheets["04_컬럼정의"], "컬럼 ID")
    if len(column_rows) != EXPECTED_COLUMN_TOTAL:
        fail(f"실제 컬럼 수 불일치: {len(column_rows)}", errors)
    if duplicate_values(row[0] for row in column_rows):
        fail("중복 컬럼 ID", errors)

    constraint_headers, constraint_rows = extract_table(sheets["05_관계_제약조건"], "제약조건 ID")
    constraint_ids = {row[0] for row in constraint_rows}
    if duplicate_values(row[0] for row in constraint_rows):
        fail("중복 제약조건 ID", errors)
    json_headers, json_rows = extract_table(sheets["07_JSONB정의"], "JSONB 구조 ID")
    json_ids = {row[0] for row in json_rows}
    code_headers, code_rows = extract_table(sheets["09_코드정의"], "코드 그룹 ID")
    code_ids = {row[0] for row in code_rows}
    vector_headers, vector_rows = extract_table(sheets["08_벡터정의"], "벡터 정의 ID")
    vector_ids = {row[0] for row in vector_rows}
    mapping_headers, mapping_rows = extract_table(sheets["10_연계매핑"], "매핑 ID")
    mapping_ids = {row[0] for row in mapping_rows}
    if duplicate_values(row[0] for row in mapping_rows):
        fail("중복 연계 매핑 ID", errors)

    index = {header: position for position, header in enumerate(column_headers)}
    required = ["컬럼 ID", "테이블 물리명", "컬럼 순번", "컬럼 논리명", "컬럼 물리명", "컬럼 설명", "PostgreSQL 타입", "NULL 허용 여부", "기본값", "PK 여부", "FK 여부", "민감정보 여부", "보존 정책", "객체 상태", "최초 도입 버전", "최종 변경 Jira"]
    per_table: dict[str, list[int]] = {name: [] for name in EXPECTED_TABLES}
    column_ids = {row[index["컬럼 ID"]] for row in column_rows}
    type_by_id = {row[index["컬럼 ID"]]: row[index["PostgreSQL 표현"]] for row in column_rows}
    for row in column_rows:
        for header in required:
            if row[index[header]] == "":
                fail(f"필수값 누락 {row[0]}: {header}", errors)
        table_name = row[index["테이블 물리명"]]
        column_name = row[index["컬럼 물리명"]]
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table_name) or not re.fullmatch(r"[a-z][a-z0-9_]*", column_name):
            fail(f"snake_case 위반: {table_name}.{column_name}", errors)
        per_table.setdefault(table_name, []).append(int(float(row[index["컬럼 순번"]])))
        if row[index["FK 여부"]] == "Y":
            target_id = f"{row[index['참조 테이블']]}.{row[index['참조 컬럼']]}"
            if target_id not in column_ids:
                fail(f"존재하지 않는 FK 대상: {row[0]} -> {target_id}", errors)
            elif type_by_id[target_id] != row[index["PostgreSQL 표현"]]:
                fail(f"FK 타입 불일치: {row[0]} -> {target_id}", errors)
        for header in ("관련 업무 규칙 ID", "FK 제약조건 ID", "복합 제약조건 ID"):
            value = row[index[header]]
            if value != "N/A":
                for reference in (item.strip() for item in value.split(",")):
                    if reference not in constraint_ids:
                        fail(f"존재하지 않는 제약·규칙 ID: {row[0]} {header}={reference}", errors)
        for header, valid_ids in (("코드 그룹 ID", code_ids), ("JSONB 구조 ID", json_ids), ("벡터 정의 ID", vector_ids), ("외부 계약 매핑 ID", mapping_ids)):
            value = row[index[header]]
            if value != "N/A":
                for reference in (item.strip() for item in value.split(",")):
                    if reference not in valid_ids:
                        fail(f"존재하지 않는 {header}: {row[0]} -> {reference}", errors)

    for table_name, expected_count in EXPECTED_COLUMN_COUNTS.items():
        sequences = per_table.get(table_name, [])
        if len(sequences) != expected_count or sorted(sequences) != list(range(1, expected_count + 1)):
            fail(f"{table_name} 컬럼 순번/수 불일치", errors)

    structures = {row[0] for row in json_rows}
    if len(structures) != 8:
        fail(f"JSONB 구조 수 불일치: {len(structures)}", errors)

    if len(vector_rows) != 1 or vector_rows[0][vector_headers.index("벡터 차원")] != "TBD":
        fail("pgvector 차원이 TBD로 유지되지 않음", errors)

    mapping_target_table = mapping_headers.index("대상 테이블")
    mapping_target_column = mapping_headers.index("대상 컬럼")
    for row in mapping_rows:
        table_name = row[mapping_target_table]
        root_column = row[mapping_target_column].split(".", 1)[0].split("[", 1)[0]
        if table_name not in EXPECTED_TABLES:
            fail(f"연계 매핑 대상 테이블 없음: {row[0]} -> {table_name}", errors)
        elif f"{table_name}.{root_column}" not in column_ids:
            fail(f"연계 매핑 대상 컬럼 없음: {row[0]} -> {table_name}.{root_column}", errors)

    built_once = build_snapshots(workbook_path)
    built_twice = build_snapshots(workbook_path)
    for name in SNAPSHOT_NAMES:
        if built_once[name] != built_twice[name]:
            fail(f"비결정적 CSV 생성: {name}", errors)
        if not built_once[name].startswith(b"\xef\xbb\xbf"):
            fail(f"UTF-8 BOM 누락: {name}", errors)
        target = snapshot_dir / name
        if not target.exists() or target.read_bytes() != built_once[name]:
            fail(f"Excel과 CSV 불일치: {name}", errors)
        try:
            list(csv.reader(io.StringIO(built_once[name][3:].decode("utf-8"))))
        except UnicodeDecodeError:
            fail(f"UTF-8 디코딩 실패: {name}", errors)

    validation_headers, validation_rows = extract_table(sheets["12_검증결과"], "검증 ID")
    status_index = validation_headers.index("상태")
    workbook_errors = sum(1 for row in validation_rows if row[status_index] == "ERROR")
    workbook_warnings = sum(1 for row in validation_rows if row[status_index] == "WARNING")
    if workbook_errors:
        fail(f"검증 시트 ERROR {workbook_errors}건", errors)
    if workbook_warnings != EXPECTED_WARNING_COUNT:
        fail(f"검증 시트 WARNING 수 불일치: {workbook_warnings}", errors)
    warnings.append(f"검증 시트 WARNING {workbook_warnings}건은 TBD·문서 충돌·미구현 상태로 명시됨")

    print(f"tables={len(table_rows)} columns={len(column_rows)} jsonb_structures={len(structures)}")
    print(f"validation_errors={len(errors)} validation_warnings={workbook_warnings}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
