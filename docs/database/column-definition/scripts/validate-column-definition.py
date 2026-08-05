"""Validate the minimal BOMI column-definition workbook and its CSV snapshots."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import csv
import importlib.util
import io
import json
import re
import sys
from zipfile import BadZipFile, ZipFile

from _xlsx_reader import duplicate_values, extract_table, read_workbook

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_WORKBOOK = ROOT / "BOMI_컬럼정의서.xlsx"
DEFAULT_SNAPSHOT_DIR = ROOT / "snapshots"
DATABASE_DIR = ROOT.parent
DOCS_DIR = DATABASE_DIR.parent

EXPECTED_SHEETS = [
    "00_읽는법",
    "01_테이블정의",
    "02_컬럼정의",
    "03_관계_제약조건",
    "04_인덱스정의",
    "05_JSONB정의",
    "06_벡터정의",
    "07_코드정의",
    "08_연계매핑",
    "09_변경이력",
]
EXPECTED_COLUMNS = {
    "app_user": [
        "id", "user_type", "name", "email", "preferred_name",
        "conversation_preferences", "onboarding_status", "time_zone",
        "personalization_consent_status", "health_data_consent_status",
        "schedule_consent_status", "guardian_sharing_consent_status",
        "status", "created_at", "updated_at",
    ],
    "care_relationship": [
        "id", "senior_id", "guardian_id", "priority", "status", "connected_at",
        "care_management_permission_status",
        "care_management_permission_updated_at",
        "care_management_permission_granted_by_user_id",
    ],
    "robot": [
        "id", "senior_id", "current_mode", "ambient_temperature_c",
        "ambient_humidity_percent", "ambient_observed_at", "is_active",
    ],
    "onboarding_session": [
        "id", "senior_id", "robot_id", "question_set_version",
        "started_channel", "status", "current_question_code", "started_at",
        "completed_at", "ended_at",
    ],
    "onboarding_answer": [
        "id", "session_id", "question_code", "answer_value",
        "answered_channel", "respondent_user_id", "source_conversation_id",
        "source_message_id", "verification_status", "confirmed_by_user_id",
        "answered_at", "confirmed_at", "updated_at",
    ],
    "scenario": [
        "id", "senior_id", "robot_id", "external_event_id", "scenario_type",
        "final_status",
    ],
    "conversation": [
        "id", "senior_id", "scenario_id", "status", "started_at",
        "ended_at", "raw_messages_expires_at",
    ],
    "conversation_message": [
        "id", "conversation_id", "sequence_no", "role", "content",
        "occurred_at", "created_at",
    ],
    "conversation_summary": [
        "id", "senior_id", "conversation_id", "summary_type",
        "period_started_at", "period_ended_at", "content",
        "source_message_count", "generated_at", "superseded_by_id",
        "embedding",
    ],
    "fact_candidate": [
        "id", "senior_id", "source_type", "onboarding_answer_id",
        "conversation_id", "source_message_id", "target_domain", "fact_type",
        "operation", "target_entity_id", "proposed_value", "confirmed_value",
        "missing_fields", "risk_level", "status", "clarification_reason",
        "clarification_count", "initiated_by_user_id", "confirmed_by_user_id",
        "requires_coordination", "coordination_status", "senior_position",
        "primary_guardian_decision", "primary_guardian_id",
        "contact_attempt_count", "last_contact_attempted_at",
        "unreachable_reason", "coordination_deadline_at",
        "coordination_completed_at", "coordination_note",
        "materialized_target_id", "materialized_at", "created_at", "updated_at",
        "confirmed_at", "expires_at",
    ],
    "memory": [
        "id", "senior_id", "source_conversation_id", "superseded_by_id",
        "memory_type", "content", "verification_status", "lifecycle_status",
        "visibility", "embedding", "source_summary_id", "source_candidate_id",
        "keywords", "importance", "first_observed_at", "last_confirmed_at",
        "last_used_at",
    ],
    "care_record": [
        "id", "senior_id", "parent_record_id", "scenario_id",
        "source_conversation_id", "source_message_id", "recipient_guardian_id",
        "created_by_user_id", "record_type", "status", "details", "recurrence",
        "source_candidate_id",
    ],
}
EXPECTED_HEADERS = {
    "01_테이블정의": ["테이블명", "한글명", "한 행의 의미", "왜 필요한가", "주요 관계", "보관·주의사항"],
    "02_컬럼정의": ["테이블명", "순번", "컬럼명", "한글명", "타입", "필수", "키", "참조", "무엇을 저장하는가", "언제 어떻게 쓰는가", "주의할 점", "예시"],
    "03_관계_제약조건": ["이름", "종류", "대상", "규칙", "필요한 이유", "구현 위치"],
    "04_인덱스정의": ["인덱스명", "대상", "컬럼", "고유", "어떤 조회를 위한가", "도입 시점"],
    "05_JSONB정의": ["대상 컬럼", "용도", "기본 구조", "필수 키", "허용 값·예시", "금지 데이터", "변경 규칙"],
    "06_벡터정의": ["대상 컬럼", "검색 목적", "원문", "차원", "생성 시점", "검색 제외 조건", "절대 임베딩하지 않는 정보", "비고"],
    "07_코드정의": ["대상", "코드값", "뜻", "언제 사용", "주의"],
    "08_연계매핑": ["계약 필드", "방향", "의미", "DB 매핑", "저장 여부", "메모"],
    "09_변경이력": ["변경일", "변경 요약", "영향", "결정 이유"],
}
FIRST_HEADERS = {sheet: headers[0] for sheet, headers in EXPECTED_HEADERS.items()}
EXPECTED_SNAPSHOT_NAMES = [
    "tables.csv", "columns.csv", "constraints.csv", "indexes.csv",
    "jsonb-fields.csv", "vector-fields.csv", "code-values.csv",
    "interface-mappings.csv", "change-history.csv",
]
FORBIDDEN_FORMALISM = {
    "Jira", "JIRA", "티켓", "승인자", "검토자", "문서 버전",
    "요구사항 ID", "경고 ID", "오류 링크", "입력목록", "검증결과",
}
FORBIDDEN_STALE_TERMS = {
    "audit_log", "client_event_id", "materialization_key",
    "processing_status", "robot.serial_number", "conversation.messages",
    "CONVERSATION_SUMMARY",
}

_exporter_path = SCRIPT_DIR / "export-column-definition-csv.py"
_exporter_spec = importlib.util.spec_from_file_location("bomi_csv_exporter", _exporter_path)
if _exporter_spec is None or _exporter_spec.loader is None:
    raise RuntimeError(f"CSV exporter를 불러올 수 없습니다: {_exporter_path}")
_exporter = importlib.util.module_from_spec(_exporter_spec)
_exporter_spec.loader.exec_module(_exporter)
build_snapshots = _exporter.build_snapshots


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def parse_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    if not content.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM이 없습니다.")
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV가 비어 있습니다.")
    return rows[0], rows[1:]


def workbook_has_formulas(path: Path) -> bool:
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                if b"<f" in archive.read(name):
                    return True
    return False


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    args = parser.parse_args()

    workbook = args.workbook.resolve()
    snapshot_dir = args.snapshot_dir.resolve()
    errors: list[str] = []

    if not workbook.exists():
        print(f"FAIL: 워크북이 없습니다: {workbook}", file=sys.stderr)
        return 1
    try:
        with ZipFile(workbook) as archive:
            if archive.testzip() is not None:
                fail(errors, "XLSX ZIP 내부 파일이 손상되었습니다.")
    except BadZipFile:
        fail(errors, "유효한 XLSX ZIP 파일이 아닙니다.")

    try:
        sheet_order, sheets = read_workbook(workbook)
    except Exception as exc:
        print(f"FAIL: 워크북을 읽지 못했습니다: {exc}", file=sys.stderr)
        return 1

    if sheet_order != EXPECTED_SHEETS:
        fail(errors, f"시트 순서가 다릅니다: {sheet_order}")

    tables_by_sheet: dict[str, tuple[list[str], list[list[str]]]] = {}
    for sheet_name, expected_headers in EXPECTED_HEADERS.items():
        if sheet_name not in sheets:
            fail(errors, f"필수 시트가 없습니다: {sheet_name}")
            continue
        try:
            headers, rows = extract_table(sheets[sheet_name], FIRST_HEADERS[sheet_name])
        except ValueError as exc:
            fail(errors, str(exc))
            continue
        tables_by_sheet[sheet_name] = (headers, rows)
        if headers != expected_headers:
            fail(errors, f"{sheet_name} 머리글이 다릅니다: {headers}")

    if "01_테이블정의" in tables_by_sheet:
        _, table_rows = tables_by_sheet["01_테이블정의"]
        actual_tables = [row[0] for row in table_rows]
        expected_tables = list(EXPECTED_COLUMNS)
        if actual_tables != expected_tables:
            fail(errors, f"테이블 목록·순서가 다릅니다: {actual_tables}")
        if duplicate_values(actual_tables):
            fail(errors, f"중복 테이블이 있습니다: {sorted(duplicate_values(actual_tables))}")
        for row_index, row in enumerate(table_rows, start=5):
            if any(not row[index].strip() for index in range(1, 6)):
                fail(errors, f"테이블 설명에 빈칸이 있습니다: 01_테이블정의 {row_index}행")

    physical_columns = {
        f"{table}.{column}"
        for table, names in EXPECTED_COLUMNS.items()
        for column in names
    }
    if "02_컬럼정의" in tables_by_sheet:
        headers, column_rows = tables_by_sheet["02_컬럼정의"]
        if len(column_rows) != 151:
            fail(errors, f"컬럼 수가 151이 아닙니다: {len(column_rows)}")
        actual_by_table: dict[str, list[str]] = {name: [] for name in EXPECTED_COLUMNS}
        seen_pairs: list[str] = []
        required_description_indexes = [headers.index(name) for name in ["무엇을 저장하는가", "언제 어떻게 쓰는가", "주의할 점", "예시"]]
        narrative_indexes = [headers.index(name) for name in ["무엇을 저장하는가", "언제 어떻게 쓰는가", "주의할 점"]]
        all_descriptions: dict[str, list[str]] = {headers[i]: [] for i in narrative_indexes}
        current_table = None
        expected_sequence = 0
        for excel_row, row in enumerate(column_rows, start=5):
            table_name, sequence, column_name = row[0], row[1], row[2]
            if table_name not in EXPECTED_COLUMNS:
                fail(errors, f"정의되지 않은 테이블 컬럼입니다: {table_name}.{column_name}")
                continue
            actual_by_table[table_name].append(column_name)
            seen_pairs.append(f"{table_name}.{column_name}")
            if table_name != current_table:
                current_table = table_name
                expected_sequence = 1
            else:
                expected_sequence += 1
            if sequence != str(expected_sequence):
                fail(errors, f"컬럼 순번이 연속되지 않습니다: {table_name}.{column_name}={sequence}")
            for index in required_description_indexes:
                value = row[index].strip()
                if not value:
                    fail(errors, f"설명 칸이 비어 있습니다: {table_name}.{column_name} / {headers[index]}")
                if index in narrative_indexes:
                    all_descriptions[headers[index]].append(value)
            if row[5] not in {"Y", "N", "조건부"}:
                fail(errors, f"필수 값이 잘못되었습니다: {table_name}.{column_name}={row[5]}")
            if row[6] not in {"", "PK", "FK", "SELF FK", "논리 참조"}:
                fail(errors, f"키 값이 잘못되었습니다: {table_name}.{column_name}={row[6]}")
        if duplicate_values(seen_pairs):
            fail(errors, f"중복 컬럼이 있습니다: {sorted(duplicate_values(seen_pairs))}")
        for table_name, expected in EXPECTED_COLUMNS.items():
            if actual_by_table.get(table_name) != expected:
                fail(errors, f"{table_name} 컬럼 목록·순서가 다릅니다: {actual_by_table.get(table_name)}")
        for label, values in all_descriptions.items():
            duplicates = duplicate_values(values)
            if duplicates:
                fail(errors, f"단조로운 동일 문장이 반복됩니다({label}): {sorted(duplicates)}")

    if "03_관계_제약조건" in tables_by_sheet:
        _, constraint_rows = tables_by_sheet["03_관계_제약조건"]
        names = [row[0] for row in constraint_rows]
        if duplicate_values(names):
            fail(errors, f"중복 제약조건 이름이 있습니다: {sorted(duplicate_values(names))}")
        pk_targets = {row[2] for row in constraint_rows if row[1] == "PK"}
        expected_pk_targets = {f"{table}.id" for table in EXPECTED_COLUMNS}
        if pk_targets != expected_pk_targets:
            fail(errors, f"PK 정의가 다릅니다: {sorted(pk_targets)}")

    if "05_JSONB정의" in tables_by_sheet:
        _, rows = tables_by_sheet["05_JSONB정의"]
        targets = {row[0] for row in rows}
        expected = {
            "app_user.conversation_preferences",
            "onboarding_answer.answer_value",
            "fact_candidate.proposed_value",
            "fact_candidate.confirmed_value",
            "care_record.details",
            "care_record.recurrence",
        }
        if targets != expected:
            fail(errors, f"JSONB 대상이 다릅니다: {sorted(targets)}")

    if "06_벡터정의" in tables_by_sheet:
        _, rows = tables_by_sheet["06_벡터정의"]
        expected_vectors = {
            "conversation_summary.embedding": "TBD",
            "memory.embedding": "TBD",
        }
        actual_vectors = {row[0]: row[3] for row in rows}
        if actual_vectors != expected_vectors:
            fail(errors, f"벡터 정의가 다릅니다: {actual_vectors}")

    if "07_코드정의" in tables_by_sheet:
        _, code_rows = tables_by_sheet["07_코드정의"]
        pairs = [f"{row[0]}={row[1]}" for row in code_rows]
        if duplicate_values(pairs):
            fail(errors, f"중복 코드가 있습니다: {sorted(duplicate_values(pairs))}")
        code_map: dict[str, set[str]] = {}
        for target, value, *_ in code_rows:
            code_map.setdefault(target, set()).add(value)
        required_codes = {
            "app_user.user_type": {"SENIOR", "GUARDIAN"},
            "robot.current_mode": {"IDLE", "SCENARIO_ACTIVE", "REST_GUARD", "SAFE_STOP"},
            "scenario.scenario_type": {"HOMECOMING", "FALL_RESPONSE", "MANUAL_INTERACTION"},
            "conversation_message.role": {"SENIOR", "ROBOT"},
            "conversation_summary.summary_type": {"CONVERSATION", "DAILY"},
            "onboarding_session.started_channel": {"APP", "ROBOT"},
            "onboarding_session.status": {
                "IN_PROGRESS", "COMPLETED", "DECLINED", "CANCELLED", "EXPIRED",
            },
            "fact_candidate.status": {
                "CAPTURED", "NEEDS_CLARIFICATION", "NEEDS_CONFIRMATION",
                "COORDINATION_REQUIRED", "CONFIRMED", "MATERIALIZED",
                "REJECTED", "EXPIRED",
            },
            "fact_candidate.source_type": {
                "ONBOARDING_ANSWER", "CONVERSATION_MESSAGE",
            },
            "fact_candidate.target_domain": {
                "PROFILE", "CARE_RELATIONSHIP", "MEMORY", "CARE_RECORD",
            },
            "fact_candidate.operation": {"CREATE", "UPDATE", "CANCEL"},
            "fact_candidate.risk_level": {"NORMAL", "SENSITIVE", "HIGH"},
            "fact_candidate.clarification_reason": {
                "MISSING_REQUIRED_FIELD", "AMBIGUOUS_VALUE",
                "LOW_RECOGNITION_CONFIDENCE", "CONFLICT_WITH_EXISTING_DATA",
                "SENSITIVE_INFORMATION_CONFIRMATION",
            },
            "fact_candidate.coordination_status": {
                "NOT_REQUIRED", "COORDINATION_REQUIRED",
                "WAITING_PRIMARY_GUARDIAN", "WAITING_SENIOR", "AGREED",
                "DISAGREED", "SENIOR_UNREACHABLE",
                "GUARDIAN_OVERRIDE_CONFIRMED", "COMPLETED",
            },
            "fact_candidate.senior_position": {
                "NOT_REQUESTED", "PENDING", "AGREED", "DISAGREED",
                "UNREACHABLE",
            },
            "fact_candidate.primary_guardian_decision": {
                "PENDING", "CONFIRMED_EXISTING_VALUE",
                "CONFIRMED_PROPOSED_VALUE", "REVISED_VALUE",
                "CANCELLED_CHANGE",
            },
            "fact_candidate.unreachable_reason": {
                "NO_RESPONSE", "PHONE_UNAVAILABLE",
                "TEMPORARY_HEALTH_CONDITION", "COMMUNICATION_DIFFICULTY",
                "OTHER",
            },
            "care_relationship.care_management_permission_status": {
                "NOT_ASKED", "GRANTED", "DENIED", "REVOKED",
            },
            "care_record.status": {
                "ACTIVE", "COMPLETED", "CANCELLED", "SUPERSEDED",
            },
        }
        for target, expected in required_codes.items():
            if code_map.get(target) != expected:
                fail(errors, f"코드 목록이 다릅니다: {target}={sorted(code_map.get(target, set()))}")

    if "08_연계매핑" in tables_by_sheet:
        _, rows = tables_by_sheet["08_연계매핑"]
        mapping_text = "\n".join("\t".join(row) for row in rows)
        if "robot.id" not in mapping_text or "scenario.external_event_id" not in mapping_text:
            fail(errors, "robotId와 시작 eventId의 DB 매핑이 없습니다.")
        for stale in [
            "robot.serial_number", "client_event_id", "materialization_key",
            "conversation.messages",
        ]:
            if stale in mapping_text:
                fail(errors, f"삭제된 매핑이 남아 있습니다: {stale}")

    workbook_text = "\n".join(
        "\t".join(row)
        for rows in sheets.values()
        for row in rows
    )
    for term in FORBIDDEN_FORMALISM:
        if term in workbook_text:
            fail(errors, f"컬럼정의서 목적과 먼 형식 메타데이터가 남아 있습니다: {term}")
    for term in FORBIDDEN_STALE_TERMS:
        if term in workbook_text:
            fail(errors, f"이전 10테이블 모델 용어가 남아 있습니다: {term}")
    if workbook_has_formulas(workbook):
        fail(errors, "컬럼정의서에 수식이 있습니다. 이 문서는 설명 원본이며 수식에 의존하지 않습니다.")

    if "02_컬럼정의" in tables_by_sheet:
        _, column_rows = tables_by_sheet["02_컬럼정의"]
        key_by_column = {f"{row[0]}.{row[2]}": row[6] for row in column_rows}
        for logical_column in [
            "fact_candidate.target_entity_id",
            "fact_candidate.materialized_target_id",
        ]:
            if key_by_column.get(logical_column) != "논리 참조":
                fail(errors, f"다형성 대상이 논리 참조가 아닙니다: {logical_column}")
        for message_fk in [
            "onboarding_answer.source_message_id",
            "fact_candidate.source_message_id",
            "care_record.source_message_id",
        ]:
            if key_by_column.get(message_fk) != "FK":
                fail(errors, f"메시지 근거가 물리 FK가 아닙니다: {message_fk}")

    erd_path = DATABASE_DIR / "mvp-erd.md"
    if not erd_path.exists():
        fail(errors, f"ERD 기준 문서가 없습니다: {erd_path}")
    else:
        erd_text = erd_path.read_text(encoding="utf-8")
        diagram = re.search(r"```mermaid\s*\nerDiagram\s*\n(.*?)```", erd_text, re.DOTALL)
        if diagram is None:
            fail(errors, "mvp-erd.md에서 erDiagram 블록을 찾지 못했습니다.")
        else:
            entities: dict[str, list[str]] = {}
            for match in re.finditer(
                r"^\s{4}([A-Z_]+)\s+\{\s*\n(.*?)^\s{4}\}",
                diagram.group(1),
                re.MULTILINE | re.DOTALL,
            ):
                table_name = match.group(1).lower()
                names: list[str] = []
                for line in match.group(2).splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        names.append(parts[1])
                entities[table_name] = names
            if entities != EXPECTED_COLUMNS:
                fail(errors, f"mvp-erd.md의 Mermaid 컬럼이 Excel 기준과 다릅니다: {entities}")

    contract_paths = [
        DOCS_DIR / "architecture" / "system-overview.md",
        DATABASE_DIR / "README.md",
        DATABASE_DIR / "onboarding-rest-environment-design.md",
        DOCS_DIR / "mqtt" / "topic-convention.md",
        DOCS_DIR / "scenario" / "homecoming-welcome.md",
    ]
    contract_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in contract_paths
        if path.exists()
    )
    for stale in [
        "robot.serial_number",
        "`scenario.status`",
        "onboarding_answer.client_event_id",
        "9테이블",
        "9개 테이블",
        "74컬럼",
        "conversation.messages",
    ]:
        if stale in contract_text:
            fail(errors, f"연계 문서에 이전 DB 매핑이 남아 있습니다: {stale}")

    question_set_path = DATABASE_DIR / "onboarding-question-set-v1.json"
    if not question_set_path.exists():
        fail(errors, f"온보딩 질문 계약이 없습니다: {question_set_path}")
    else:
        try:
            question_set = json.loads(question_set_path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(errors, f"온보딩 질문 JSON을 파싱할 수 없습니다: {exc}")
        else:
            if question_set.get("version") != "onboarding-v1":
                fail(errors, "질문 계약 version이 onboarding-v1이 아닙니다.")
            questions = question_set.get("questions") or []
            question_codes = [question.get("code") for question in questions]
            if duplicate_values(question_codes):
                fail(errors, f"중복 질문 코드가 있습니다: {sorted(duplicate_values(question_codes))}")
            required_fields = {
                "code", "required", "channels", "targetDomain", "targetType",
                "requiredFields", "sensitive", "requiresConfirmation",
                "prerequisiteConsent", "appControl", "robotPrompt",
                "clarification", "answerSchema", "materialization",
            }
            for question in questions:
                missing = required_fields - set(question)
                if missing:
                    fail(errors, f"질문 속성 누락: {question.get('code')}: {sorted(missing)}")
                if set(question.get("channels") or []) != {"APP", "ROBOT"}:
                    fail(errors, f"양 채널을 허용하지 않는 질문: {question.get('code')}")
                if question.get("sensitive") and not question.get("requiresConfirmation"):
                    fail(errors, f"민감 질문이 최종 확인을 요구하지 않음: {question.get('code')}")
            required_codes = {
                "PERSONALIZATION_CONSENT", "HEALTH_DATA_CONSENT",
                "SCHEDULE_CONSENT", "GUARDIAN_SHARING_CONSENT",
                "PREFERRED_NAME", "BIRTH_DATE", "DAILY_ROUTINE", "MEDICATION",
                "MEDICATION_SCHEDULE", "APPOINTMENT",
                "PRIMARY_GUARDIAN_CARE_MANAGEMENT_CONSENT",
            }
            if set(question_codes) != required_codes:
                fail(errors, f"질문 코드 목록이 다릅니다: {sorted(question_codes)}")

    policy_tokens = {
        "앱·로봇 채널 전환": ["started_channel", "answered_channel"],
        "질문 세트 버전": ["question_set_version", "onboarding-v1"],
        "PRIMARY 전용 권한": ["care_management_permission_status", "SECONDARY"],
        "충돌 협의": ["GUARDIAN_OVERRIDE_CONFIRMED", "senior_position"],
        "연락 불가": ["unreachable_reason", "contact_attempt_count"],
        "민감정보 확인": ["SENSITIVE_INFORMATION_CONFIRMATION", "confirmed_value"],
        "중복 반영 방지": ["source_candidate_id", "materialized_at"],
        "Raw 삭제 안전": ["ON DELETE SET NULL", "보존기간"],
    }
    policy_text = workbook_text + "\n" + contract_text
    if question_set_path.exists():
        policy_text += "\n" + question_set_path.read_text(encoding="utf-8")
    for policy, tokens in policy_tokens.items():
        missing = [token for token in tokens if token not in policy_text]
        if missing:
            fail(errors, f"정책 추적 근거 부족({policy}): {missing}")

    try:
        expected_snapshots = build_snapshots(workbook)
    except Exception as exc:
        fail(errors, f"스냅샷을 생성할 수 없습니다: {exc}")
        expected_snapshots = {}

    actual_names = sorted(path.name for path in snapshot_dir.glob("*.csv"))
    if actual_names != sorted(EXPECTED_SNAPSHOT_NAMES):
        fail(errors, f"CSV 파일 목록이 다릅니다: {actual_names}")
    for name, expected_content in expected_snapshots.items():
        target = snapshot_dir / name
        if not target.exists():
            fail(errors, f"CSV가 없습니다: {name}")
            continue
        actual_content = target.read_bytes()
        if actual_content != expected_content:
            fail(errors, f"Excel과 CSV가 다릅니다: {name}")
        try:
            headers, rows = parse_csv(actual_content)
        except (UnicodeDecodeError, ValueError) as exc:
            fail(errors, f"CSV 인코딩·형식 오류: {name}: {exc}")
            continue
        expected_sheet = next(
            sheet for filename, (sheet, _) in _exporter.SNAPSHOTS.items()
            if filename == name
        )
        if headers != EXPECTED_HEADERS[expected_sheet]:
            fail(errors, f"CSV 머리글이 다릅니다: {name}: {headers}")
        for row_index, row in enumerate(rows, start=2):
            for value in row:
                if re.match(r"^[=+@]", value):
                    fail(errors, f"CSV 수식 주입 위험 값이 있습니다: {name} {row_index}행")

    if errors:
        print("컬럼정의서 검증 실패", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("컬럼정의서 검증 완료")
    print("- 시트 10개")
    print("- 물리 테이블 12개")
    print("- 컬럼 151개")
    print("- 목적형 CSV 스냅샷 9개")
    print("- Jira·승인·입력목록·검증결과 시트 없음")
    print("- 컬럼별 의미·사용 맥락·주의·예시 누락 및 동일 문장 반복 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
