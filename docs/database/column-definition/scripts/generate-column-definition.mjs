import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..", "..");
const erdPath = path.join(repoRoot, "docs", "database", "mvp-erd.md");
const outputArg = process.argv.find((arg) => arg.startsWith("--output="));
const outputPath = outputArg
  ? path.resolve(outputArg.slice("--output=".length))
  : path.join(repoRoot, "docs", "database", "column-definition", "BOMI_컬럼정의서.xlsx");

try {
  await fs.access(outputPath);
  throw new Error(`기존 Excel을 보호하기 위해 생성하지 않았습니다: ${outputPath}`);
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

const { SpreadsheetFile, Workbook } = await import("@oai/artifact-tool");

const erdText = await fs.readFile(erdPath, "utf8");
const lines = erdText.replace(/\r/g, "").split("\n");
const today = "2026-07-23";
const documentVersion = "0.3.0";
const jira = "S15P11E102-84";
let sourceCommit = execFileSync("git", ["log", "-1", "--format=%H", "--", "docs/database/mvp-erd.md"], { cwd: repoRoot, encoding: "utf8" }).trim();
try {
  execFileSync("git", ["diff", "--quiet", "--", "docs/database/mvp-erd.md"], { cwd: repoRoot });
} catch {
  sourceCommit = `${sourceCommit} + WORKTREE`;
}
const branch = execFileSync("git", ["branch", "--show-current"], { cwd: repoRoot, encoding: "utf8" }).trim() || "DETACHED";

function clean(value) {
  return String(value ?? "")
    .trim()
    .replace(/^`|`$/g, "")
    .replace(/\*\*/g, "")
    .replace(/<br\s*\/?>/gi, " / ")
    .replace(/—/g, "N/A");
}

function splitMarkdownRow(line) {
  return line.split("|").slice(1, -1).map(clean);
}

function headingIndex(tableName) {
  return lines.findIndex((line) => line.trim() === `### \`${tableName}\``);
}

function sectionForTable(tableName) {
  const start = headingIndex(tableName);
  const endOffset = lines.slice(start + 1).findIndex((line) => /^### /.test(line));
  return lines.slice(start, endOffset < 0 ? lines.length : start + 1 + endOffset);
}

function parseSourceTable(tableName) {
  const section = sectionForTable(tableName);
  const purpose = clean((section.find((line) => line.startsWith("목적:")) || "목적: TBD").replace(/^목적:\s*/, ""));
  const deletion = clean((section.find((line) => line.startsWith("삭제 정책:") || line.startsWith("삭제·보존 정책:")) || "삭제 정책: 원본 정책에 따름").replace(/^[^:]+:\s*/, ""));
  const headerIndex = section.findIndex((line) => line.startsWith("| 컬럼 | PostgreSQL 타입"));
  const rows = [];
  for (let i = headerIndex + 2; i < section.length && section[i].startsWith("|"); i += 1) {
    const cells = splitMarkdownRow(section[i]);
    if (cells.length === 8) rows.push(cells);
  }
  return { tableName, purpose, deletion, rows };
}

function parseNamedMarkdownTable(sectionHeading, headerPrefix) {
  const start = lines.findIndex((line) => line.trim() === sectionHeading);
  const section = lines.slice(start);
  const headerIndex = section.findIndex((line) => line.startsWith(headerPrefix));
  const header = splitMarkdownRow(section[headerIndex]);
  const rows = [];
  for (let i = headerIndex + 2; i < section.length && section[i].startsWith("|"); i += 1) {
    rows.push(splitMarkdownRow(section[i]));
  }
  return { header, rows };
}

const tableOrder = ["app_user", "care_relationship", "robot", "onboarding_session", "onboarding_answer", "scenario", "conversation", "memory", "care_record", "audit_log"];
const sourceTables = tableOrder.map(parseSourceTable);
const sourceColumnCount = sourceTables.reduce((sum, table) => sum + table.rows.length, 0);
if (sourceColumnCount !== 238) throw new Error(`원본 데이터 사전 행 수가 예상과 다릅니다: ${sourceColumnCount}`);

const domainByTable = {
  app_user: "사용자·개인정보",
  care_relationship: "돌봄 관계·권한",
  robot: "로봇·배정",
  onboarding_session: "온보딩·동의",
  onboarding_answer: "온보딩·AI 처리",
  scenario: "시나리오·AIoT",
  conversation: "대화·생성 AI",
  memory: "개인화 기억·AI",
  care_record: "돌봄·건강·알림",
  audit_log: "감사·보안",
};

const logicalTableNames = {
  app_user: "사용자",
  care_relationship: "돌봄 관계",
  robot: "로봇",
  onboarding_session: "온보딩 세션",
  onboarding_answer: "온보딩 답변",
  scenario: "시나리오",
  conversation: "대화",
  memory: "기억",
  care_record: "돌봄 기록",
  audit_log: "감사 로그",
};

const rowUnit = {
  app_user: "어르신 또는 보호자 한 명",
  care_relationship: "어르신과 보호자 사이의 한 연결",
  robot: "등록된 물리 로봇 한 대의 현재 상태",
  onboarding_session: "한 어르신이 현재 배정 로봇으로 진행한 한 번의 초기 설문",
  onboarding_answer: "한 세션·문항의 한 답변 또는 수정 revision",
  scenario: "하나의 외부 트리거로 시작된 업무 흐름",
  conversation: "어르신과 로봇 사이의 한 대화 세션",
  memory: "검증·공개·생명주기를 독립 관리하는 기억 한 건",
  care_record: "계획·실행·관찰·알림 중 하나의 돌봄 업무 기록",
  audit_log: "민감 변경 행위 한 건의 비본문 감사 흔적",
};

const creatorByTable = {
  app_user: "Spring Backend / 관리자 흐름",
  care_relationship: "Spring Backend / 사용자 요청",
  robot: "Spring Backend / 장치 등록",
  onboarding_session: "Spring Backend / Robot 온보딩 흐름",
  onboarding_answer: "Spring Backend / Robot·Voice AI 이벤트",
  scenario: "Spring Backend / IoT·Robot 이벤트",
  conversation: "Spring Backend / Robot·Voice AI",
  memory: "Spring Backend / 사용자·AI 추출",
  care_record: "Spring Backend / 사용자·보호자·Robot·AI",
  audit_log: "Spring Backend",
};

const serviceByTable = {
  app_user: "Backend, 대화·개인화 서비스",
  care_relationship: "Backend 권한 검사, 보호자 대시보드",
  robot: "Backend, Robot MQTT Bridge",
  onboarding_session: "Backend, Robot MQTT Bridge",
  onboarding_answer: "Backend, Robot, Voice AI, 대화·개인화 서비스",
  scenario: "Backend, Robot, Vision AI, MQTT",
  conversation: "Backend, Voice AI, Robot",
  memory: "Backend, 개인화 검색, 보호자 대시보드",
  care_record: "Backend, 보호자 대시보드, Robot·AI",
  audit_log: "Backend, 보안·운영 검토",
};

const retentionByTable = {
  app_user: "사용자 서비스 이용 기간; 삭제 요청 시 법적 보존 제외 후 삭제·비식별화",
  care_relationship: "연결 기간과 승인된 관계 변경 감사 기간",
  robot: "장치 운용 기간; 사용자 삭제 시 배정·주거 참조 제거",
  onboarding_session: "세션 상태·정책 버전·완료 시각은 감사·업무 정책 기간",
  onboarding_answer: "처리·검증·반영 원장은 감사 정책; 원문 7일, 후보·신뢰도 기본 30일",
  scenario: "일반 90일; 안전 기록은 보안·법무 정책 TBD",
  conversation: "원문 7일, 요약 기본 90일; 명시 삭제 시 파생정보 검토",
  memory: "만료 또는 명시 삭제까지; 확인된 안정 기억의 최종 정책 TBD",
  care_record: "유형별 정책; 일반 결과 90일, 관찰 30/90일, 안전 정책 TBD",
  audit_log: "보안·법무 보존기간 TBD; 임의 영구 보존 금지",
};

const sensitiveByTable = { app_user: "Y", care_relationship: "Y", robot: "Y", onboarding_session: "Y", onboarding_answer: "Y", scenario: "Y", conversation: "Y", memory: "Y", care_record: "Y", audit_log: "간접" };

const logicalOverrides = {
  id: "내부 식별자", senior_id: "대상 어르신 ID", guardian_id: "보호자 ID", robot_id: "수행 로봇 ID",
  session_id: "온보딩 세션 ID", scenario_id: "연계 시나리오 ID", source_conversation_id: "출처 대화 ID", source_message_id: "출처 메시지 ID",
  parent_record_id: "상위 돌봄 기록 ID", recipient_guardian_id: "알림 수신 보호자 ID", created_by_user_id: "사람 생성자 ID",
  actor_user_id: "행위자 사용자 ID", external_event_id: "외부 이벤트 멱등 ID", request_id: "요청 상관관계 ID",
  created_at: "생성 시각", updated_at: "최종 수정 시각", occurred_at: "사건 발생 시각", received_at: "백엔드 수신 시각",
  started_at: "처리 시작 시각", completed_at: "처리 완료 시각", ended_at: "종료 시각", status: "업무 상태",
  version: "낙관적 잠금 버전", schema_version: "구조 스키마 버전", is_active: "현재 활성 여부",
};

const codeGroupByColumn = {
  "app_user.user_type": "CODE_USER_TYPE", "app_user.status": "CODE_USER_STATUS", "app_user.onboarding_status": "CODE_ONBOARDING_STATUS",
  "app_user.personalization_consent_status": "CODE_CONSENT_STATUS", "app_user.health_data_consent_status": "CODE_CONSENT_STATUS",
  "app_user.schedule_consent_status": "CODE_CONSENT_STATUS", "app_user.guardian_sharing_consent_status": "CODE_CONSENT_STATUS",
  "care_relationship.priority": "CODE_RELATIONSHIP_PRIORITY", "care_relationship.status": "CODE_RELATIONSHIP_STATUS",
  "onboarding_session.status": "CODE_ONBOARDING_SESSION_STATUS",
  "onboarding_answer.processing_status": "CODE_ONBOARDING_PROCESSING_STATUS",
  "onboarding_answer.verification_status": "CODE_ONBOARDING_VERIFICATION_STATUS",
  "robot.status": "CODE_ROBOT_STATUS", "robot.current_mode": "CODE_ROBOT_MODE", "scenario.scenario_type": "CODE_SCENARIO_TYPE", "scenario.status": "CODE_SCENARIO_STATUS",
  "scenario.navigation_status": "CODE_NAVIGATION_STATUS", "scenario.vision_status": "CODE_VISION_STATUS", "scenario.return_status": "CODE_RETURN_STATUS",
  "conversation.status": "CODE_CONVERSATION_STATUS", "conversation.execution_location": "CODE_EXECUTION_LOCATION",
  "conversation.generation_status": "CODE_GENERATION_STATUS", "memory.memory_type": "CODE_MEMORY_TYPE",
  "memory.verification_status": "CODE_MEMORY_VERIFICATION", "memory.lifecycle_status": "CODE_MEMORY_LIFECYCLE",
  "memory.visibility": "CODE_MEMORY_VISIBILITY", "memory.embedding_generation_status": "CODE_EMBEDDING_STATUS",
  "care_record.record_type": "CODE_CARE_RECORD_TYPE", "care_record.source_type": "CODE_CARE_SOURCE_TYPE",
  "care_record.verification_status": "CODE_CARE_VERIFICATION",
  "audit_log.actor_type": "CODE_AUDIT_ACTOR_TYPE",
  "audit_log.action_type": "CODE_AUDIT_ACTION_TYPE",
};

const jsonStructureByColumn = {
  "app_user.conversation_preferences": "JSON_APP_USER_PREFERENCES_V2",
  "care_relationship.permissions": "JSON_RELATIONSHIP_PERMISSIONS_V1",
  "onboarding_answer.extraction_jsonb": "JSON_ONBOARDING_EXTRACTION_V1",
  "onboarding_answer.target_refs": "JSON_ONBOARDING_TARGET_REFS_V1",
  "scenario.timeline": "JSON_SCENARIO_TIMELINE_V1",
  "conversation.messages": "JSON_CONVERSATION_MESSAGES_V1",
  "care_record.details": "JSON_CARE_RECORD_DETAILS_V1",
  "care_record.recurrence": "JSON_CARE_RECORD_RECURRENCE_V1",
};

const externalMappingByColumn = {
  "robot.serial_number": "MAP-ROBOT-EXTERNAL-ID",
  "scenario.id": "MAP-VISION-SCENARIO-ID",
  "scenario.scenario_type": "MAP-VISION-SCENARIO-TYPE",
  "scenario.external_event_id": "MAP-SCENARIO-EXTERNAL-EVENT-ID",
  "scenario.trigger_device_code": "MAP-SCENARIO-TRIGGER-DEVICE",
  "scenario.occurred_at": "MAP-SCENARIO-OCCURRED-AT",
  "scenario.navigation_command_id": "MAP-NAVIGATION-COMMAND-ID",
  "scenario.destination_waypoint": "MAP-NAVIGATION-WAYPOINT",
  "scenario.vision_status": "MAP-VISION-RESULT-TYPE",
  "scenario.person_count": "MAP-VISION-PERSON-COUNT",
  "scenario.vision_confidence": "MAP-VISION-CONFIDENCE",
  "scenario.vision_model_name": "MAP-VISION-MODEL-NAME",
  "scenario.vision_model_version": "MAP-VISION-MODEL-VERSION",
  "scenario.vision_request_id": "MAP-VISION-REQUEST-ID",
  "scenario.return_destination": "MAP-RETURN-DESTINATION",
  "scenario.return_command_id": "MAP-RETURN-COMMAND-ID",
  "scenario.timeline": "MAP-VISION-CALLBACK-EVENT-ID",
  "conversation.scenario_id": "MAP-VOICE-SCENARIO-ID",
  "conversation.messages": "MAP-VOICE-TEXT, MAP-SPEAK-COMMAND-ID",
  "conversation.generation_request_id": "MAP-VOICE-REQUEST-ID",
  "conversation.generation_completed_at": "MAP-VOICE-GENERATED-AT",
  "robot.ambient_temperature_c": "MAP-AMBIENT-TEMPERATURE",
  "robot.ambient_humidity_percent": "MAP-AMBIENT-HUMIDITY",
  "robot.ambient_observed_at": "MAP-AMBIENT-OCCURRED-AT",
  "robot.ambient_sensor_code": "MAP-AMBIENT-SOURCE",
  "robot.current_mode": "MAP-REST-ROBOT-MODE",
  "care_record.external_event_id": "MAP-REST-EVENT-ID, MAP-AMBIENT-EVENT-ID",
  "onboarding_answer.client_event_id": "MAP-ONBOARDING-EVENT-ID",
  "onboarding_answer.session_id": "MAP-ONBOARDING-SESSION-ID",
  "onboarding_answer.question_code": "MAP-ONBOARDING-QUESTION-CODE",
  "onboarding_answer.revision": "MAP-ONBOARDING-REVISION",
  "onboarding_answer.answered_at": "MAP-ONBOARDING-OCCURRED-AT",
  "onboarding_answer.transcript_excerpt": "MAP-ONBOARDING-TRANSCRIPT",
  "onboarding_answer.stt_confidence": "MAP-ONBOARDING-STT-CONFIDENCE",
  "onboarding_answer.stt_model_name": "MAP-ONBOARDING-STT-MODEL-NAME",
  "onboarding_answer.stt_model_version": "MAP-ONBOARDING-STT-MODEL-VERSION",
  "onboarding_answer.processing_policy_version": "MAP-ONBOARDING-POLICY-VERSION",
};

const businessRuleByColumn = {
  "care_relationship.senior_id": "RULE_RELATION_DISTINCT_USERS, RULE_RELATION_USER_TYPES",
  "care_relationship.guardian_id": "RULE_RELATION_DISTINCT_USERS, RULE_RELATION_USER_TYPES",
  "care_relationship.permissions": "RULE_PRIMARY_MANAGES_RELATIONSHIPS",
  "robot.senior_id": "RULE_ROBOT_ACTIVE_ASSIGNMENT",
  "robot.assigned_at": "RULE_ROBOT_ACTIVE_ASSIGNMENT",
  "robot.unassigned_at": "RULE_ROBOT_ACTIVE_ASSIGNMENT",
  "robot.is_active": "RULE_ROBOT_ACTIVE_ASSIGNMENT",
  "robot.current_mode": "RULE_REST_GUARD_ALLOWLIST",
  "robot.ambient_temperature_c": "RULE_AMBIENT_LATEST_WINS",
  "robot.ambient_humidity_percent": "RULE_AMBIENT_LATEST_WINS",
  "robot.ambient_observed_at": "RULE_AMBIENT_LATEST_WINS",
  "onboarding_session.senior_id": "RULE_ONBOARDING_SESSION_ACTIVE_ROBOT, RULE_ONBOARDING_PROJECTION",
  "onboarding_session.robot_id": "RULE_ONBOARDING_SESSION_ACTIVE_ROBOT",
  "onboarding_session.status": "RULE_ONBOARDING_PROJECTION, RULE_ONBOARDING_SESSION_TERMINAL",
  "onboarding_session.version": "RULE_ONBOARDING_SESSION_TERMINAL",
  "onboarding_answer.session_id": "RULE_ONBOARDING_ANSWER_SESSION, RULE_ONBOARDING_REVISION",
  "onboarding_answer.question_code": "RULE_ONBOARDING_ANSWER_SESSION, RULE_ONBOARDING_REVISION",
  "onboarding_answer.revision": "RULE_ONBOARDING_REVISION",
  "onboarding_answer.client_event_id": "RULE_ONBOARDING_EVENT_IDEMPOTENCY",
  "onboarding_answer.processing_status": "RULE_ONBOARDING_STATUS_COMBINATION",
  "onboarding_answer.verification_status": "RULE_ONBOARDING_STATUS_COMBINATION",
  "onboarding_answer.source_conversation_id": "RULE_ONBOARDING_SOURCE_MATCH",
  "onboarding_answer.source_message_id": "RULE_ONBOARDING_SOURCE_MATCH",
  "onboarding_answer.materialization_key": "RULE_ONBOARDING_MATERIALIZATION",
  "onboarding_answer.materialized_at": "RULE_ONBOARDING_MATERIALIZATION",
  "onboarding_answer.target_refs": "RULE_ONBOARDING_MATERIALIZATION",
  "scenario.senior_id": "RULE_SCENARIO_ROBOT_ASSIGNMENT",
  "scenario.robot_id": "RULE_SCENARIO_ROBOT_ASSIGNMENT",
  "scenario.external_event_id": "RULE_EVENT_IDEMPOTENCY",
  "scenario.status": "RULE_TERMINAL_STATE",
  "scenario.vision_request_id": "RULE_VISION_REQUEST_IDEMPOTENCY",
  "scenario.version": "RULE_TERMINAL_STATE",
  "scenario.completed_at": "RULE_TIME_ORDER",
  "conversation.senior_id": "RULE_CONVERSATION_SENIOR_MATCH",
  "conversation.scenario_id": "RULE_CONVERSATION_SENIOR_MATCH",
  "memory.senior_id": "RULE_MEMORY_SOURCE_MATCH",
  "memory.source_conversation_id": "RULE_MEMORY_SOURCE_MATCH",
  "memory.source_message_id": "RULE_MEMORY_SOURCE_MATCH",
  "memory.content": "RULE_MEMORY_DELETE_TOMBSTONE",
  "memory.lifecycle_status": "RULE_MEMORY_DELETE_TOMBSTONE",
  "memory.embedding": "RULE_MEMORY_DELETE_TOMBSTONE",
  "memory.superseded_by_id": "RULE_MEMORY_NO_SELF_SUPERSEDE",
  "memory.purged_at": "RULE_MEMORY_DELETE_TOMBSTONE",
  "care_record.senior_id": "RULE_CARE_PARENT_MATCH, RULE_CARE_SCENARIO_MATCH",
  "care_record.parent_record_id": "RULE_CARE_PARENT_MATCH, RULE_CARE_NO_SELF_PARENT",
  "care_record.scenario_id": "RULE_CARE_SCENARIO_MATCH",
  "care_record.source_conversation_id": "RULE_CARE_SOURCE_MATCH, RULE_CONSENT_GATE",
  "care_record.source_message_id": "RULE_CARE_SOURCE_MATCH, RULE_CONSENT_GATE",
  "care_record.recipient_guardian_id": "RULE_NOTIFICATION_RELATION",
  "care_record.external_event_id": "RULE_CARE_EVENT_IDEMPOTENCY",
  "app_user.onboarding_status": "RULE_ONBOARDING_COMPLETION",
  "app_user.onboarding_version": "RULE_ONBOARDING_COMPLETION",
  "app_user.onboarding_completed_at": "RULE_ONBOARDING_COMPLETION",
  "app_user.health_data_consent_status": "RULE_CONSENT_GATE",
  "app_user.schedule_consent_status": "RULE_CONSENT_GATE",
  "app_user.guardian_sharing_consent_status": "RULE_CONSENT_GATE",
};

const uniqueConstraintByColumn = {
  "app_user.email": "CONSTRAINT_UQ_APP_USER_ACTIVE_GUARDIAN_EMAIL",
  "robot.senior_id": "CONSTRAINT_UQ_ROBOT_ACTIVE_SENIOR",
  "robot.serial_number": "CONSTRAINT_UQ_ROBOT_SERIAL_NUMBER",
  "onboarding_session.senior_id": "CONSTRAINT_UQ_ONBOARDING_SESSION_SENIOR_IN_PROGRESS",
  "onboarding_answer.client_event_id": "CONSTRAINT_UQ_ONBOARDING_ANSWER_CLIENT_EVENT",
  "onboarding_answer.revision": "CONSTRAINT_UQ_ONBOARDING_ANSWER_REVISION",
  "onboarding_answer.materialization_key": "CONSTRAINT_UQ_ONBOARDING_ANSWER_MATERIALIZATION",
  "scenario.external_event_id": "CONSTRAINT_UQ_SCENARIO_EXTERNAL_EVENT",
  "scenario.navigation_command_id": "CONSTRAINT_UQ_SCENARIO_NAVIGATION_COMMAND",
  "scenario.return_command_id": "CONSTRAINT_UQ_SCENARIO_RETURN_COMMAND",
  "scenario.vision_request_id": "CONSTRAINT_UQ_SCENARIO_VISION_REQUEST",
  "conversation.scenario_id": "CONSTRAINT_UQ_CONVERSATION_SCENARIO",
  "memory.embedding_request_id": "CONSTRAINT_UQ_MEMORY_EMBEDDING_REQUEST",
  "care_record.external_event_id": "CONSTRAINT_UQ_CARE_RECORD_EXTERNAL_EVENT",
  "care_record.ai_request_id": "CONSTRAINT_UQ_CARE_RECORD_AI_REQUEST",
};

function parseType(typeExpression) {
  const varchar = typeExpression.match(/^varchar\((\d+)\)$/i);
  const numeric = typeExpression.match(/^numeric\((\d+),(\d+)\)$/i);
  const vector = typeExpression.match(/^vector\((.+)\)$/i);
  return {
    base: varchar ? "varchar" : numeric ? "numeric" : vector ? "vector" : typeExpression,
    length: varchar ? varchar[1] : "N/A",
    precision: numeric ? numeric[1] : "N/A",
    scale: numeric ? numeric[2] : "N/A",
    vectorDimension: vector ? (vector[1].includes("EMBEDDING_DIM") ? "TBD" : vector[1]) : "N/A",
  };
}

function inferLogicalName(columnName, description) {
  if (logicalOverrides[columnName]) return logicalOverrides[columnName];
  const first = description.split(/[.;]/)[0].trim();
  return first.length <= 28 ? first : first.slice(0, 27) + "…";
}

function exampleFor(tableName, columnName, typeExpression, sensitive) {
  if (columnName === "id" || columnName.endsWith("_id") && typeExpression === "uuid") return "00000000-0000-4000-8000-000000000001";
  if (columnName.endsWith("_at")) return "2026-01-15T00:00:00Z";
  if (typeExpression === "date") return "1950-01-01";
  if (typeExpression === "boolean") return "false";
  if (/integer|smallint|bigint|numeric/.test(typeExpression)) return "0";
  if (typeExpression.startsWith("jsonb")) return "구조 ID 참조";
  if (typeExpression.startsWith("vector")) return "비식별 본문에서 재생성되는 벡터";
  if (sensitive === "Y" || sensitive === "인증") return "비식별 가상 값";
  return columnName.toUpperCase().slice(0, 24);
}

function fkInfo(keyText) {
  const match = keyText.match(/FK→([^,;\s]+)/);
  if (!match) return null;
  const [table, column] = clean(match[1]).split(".");
  return { table, column };
}

const columnHeaders = [
  "컬럼 ID", "도메인", "테이블 논리명", "테이블 물리명", "컬럼 순번", "컬럼 논리명", "컬럼 물리명",
  "컬럼 설명", "업무 사용 목적", "값의 의미", "값 형식", "단위", "시간대", "비식별 예시 값", "관련 업무 규칙 ID",
  "PostgreSQL 타입", "PostgreSQL 표현", "길이", "정밀도", "스케일", "NULL 허용 여부", "기본값", "자동 생성 여부", "생성 방식",
  "PK 여부", "PK 순번", "FK 여부", "FK 제약조건 ID", "참조 테이블", "참조 컬럼", "단일 컬럼 UNIQUE 여부", "복합 제약조건 ID",
  "코드 그룹 ID", "JSONB 구조 ID", "벡터 정의 ID", "데이터 생성 주체", "데이터 변경 주체", "주요 사용 서비스", "외부 계약 매핑 ID",
  "민감정보 여부", "민감정보 상세 분류", "마스킹 필요 여부", "암호화 필요 여부", "보존 정책", "삭제 또는 익명화 방식", "감사 대상 여부",
  "객체 상태", "최초 도입 버전", "변경 버전", "폐기 예정 버전", "최종 변경 Jira", "최종 수정일", "비고", "관련 객체 이동",
];

const tableHeaders = ["테이블 ID", "도메인", "테이블 논리명", "테이블 물리명", "테이블 목적", "한 행이 의미하는 업무 단위", "주요 책임", "대표 PK", "주요 상위·참조 테이블", "데이터 생성 주체", "주요 사용 서비스", "데이터 소유 주체", "민감정보 포함 여부", "기본 보존 정책", "기본 삭제 정책", "예상 데이터 증가 특성", "담당 영역", "객체 상태", "최초 도입 버전", "폐기 버전", "최종 변경 Jira", "비고"];

const referencedTables = {
  app_user: "N/A", care_relationship: "app_user", robot: "app_user",
  onboarding_session: "app_user, robot", onboarding_answer: "onboarding_session, conversation",
  scenario: "app_user, robot", conversation: "app_user, scenario",
  memory: "app_user, conversation, memory", care_record: "app_user, scenario, care_record", audit_log: "app_user(선택 FK), 논리 대상",
};

const growth = {
  app_user: "LOW", care_relationship: "LOW", robot: "LOW", onboarding_session: "LOW-MEDIUM", onboarding_answer: "MEDIUM",
  scenario: "MEDIUM-HIGH", conversation: "MEDIUM-HIGH",
  memory: "MEDIUM", care_record: "HIGH", audit_log: "HIGH / append-only",
};

const tableRows = sourceTables.map((table, index) => [
  `TBL-${String(index + 1).padStart(2, "0")}`, domainByTable[table.tableName], logicalTableNames[table.tableName], table.tableName,
  table.purpose, rowUnit[table.tableName], table.purpose, `${table.tableName}.id`, referencedTables[table.tableName], creatorByTable[table.tableName],
  serviceByTable[table.tableName], "BOMI Spring Backend", sensitiveByTable[table.tableName], retentionByTable[table.tableName], table.deletion,
  growth[table.tableName], domainByTable[table.tableName], "ACTIVE", documentVersion, "N/A", jira, "docs/database/mvp-erd.md E절 기준",
]);

const columnRows = [];
for (const table of sourceTables) {
  table.rows.forEach(([columnName, typeExpression, nullable, defaultValue, keyText, description, sensitive, retention], index) => {
    const columnId = `${table.tableName}.${columnName}`;
    const type = parseType(typeExpression);
    const fk = fkInfo(keyText);
    const isTime = typeExpression === "timestamptz";
    const isPk = /(^|\s)PK(\s|$)/.test(keyText);
    const isFk = Boolean(fk) || /self FK/.test(keyText);
    const fkTarget = fk || (/self FK/.test(keyText) ? { table: table.tableName, column: "id" } : null);
    const auto = defaultValue !== "N/A" && (/gen_random_uuid|now\(\)/.test(defaultValue));
    const externalMapping = externalMappingByColumn[columnId] || "N/A";
    const businessRule = businessRuleByColumn[columnId] || "N/A";
    let compoundConstraint = uniqueConstraintByColumn[columnId] || "N/A";
    if (keyText.includes("CHECK")) compoundConstraint = `CHK_${table.tableName}_${columnName}`.toUpperCase();
    if (columnId === "memory.superseded_by_id") compoundConstraint = "RULE_MEMORY_NO_SELF_SUPERSEDE";
    if (columnId === "care_record.parent_record_id") compoundConstraint = "RULE_CARE_NO_SELF_PARENT";
    if (columnId === "care_relationship.senior_id" || columnId === "care_relationship.guardian_id") compoundConstraint = "RULE_RELATION_DISTINCT_USERS";
    const sensitiveClass = sensitive === "N" ? "N/A" : sensitive === "인증" ? "인증정보" : sensitive === "파생" || sensitive === "민감 파생" ? "민감 파생정보" : sensitive === "간접" ? "간접식별정보" : "개인정보 또는 건강·생활정보";
    const deletion = sensitive === "N" ? "행/업무 정책에 따라 삭제" : table.deletion;
    columnRows.push([
      columnId, domainByTable[table.tableName], logicalTableNames[table.tableName], table.tableName, index + 1,
      inferLogicalName(columnName, description), columnName, description, `${table.purpose}에서 ${description}을(를) 관리`, description,
      typeExpression === "jsonb" ? "JSON object; 구조 ID 참조" : typeExpression.startsWith("vector") ? "pgvector; 차원 TBD" : typeExpression,
      /latency_ms|duration_ms/.test(columnName) ? "ms" : /ambient_temperature_c/.test(columnName) ? "°C" : /battery_level|humidity_percent/.test(columnName) ? "%" : "N/A",
      isTime ? "UTC" : "N/A", exampleFor(table.tableName, columnName, typeExpression, sensitive), businessRule,
      type.base, typeExpression, type.length, type.precision, type.scale, nullable, defaultValue, auto ? "Y" : "N", auto ? "PostgreSQL DEFAULT" : "애플리케이션 또는 사용자 입력",
      isPk ? "Y" : "N", isPk ? "1" : "N/A", isFk ? "Y" : "N", isFk ? `FK_${table.tableName}_${columnName}`.toUpperCase() : "N/A",
      fkTarget?.table || "N/A", fkTarget?.column || "N/A", /UNIQUE/.test(keyText) && !/\(/.test(keyText) ? "Y" : "N",
      compoundConstraint,
      codeGroupByColumn[columnId] || "N/A", jsonStructureByColumn[columnId] || "N/A", columnId === "memory.embedding" ? "VEC_MEMORY_EMBEDDING" : "N/A",
      creatorByTable[table.tableName], "Spring Backend 서비스", serviceByTable[table.tableName], externalMapping,
      sensitive === "인증" ? "Y" : sensitive, sensitiveClass, sensitive === "N" ? "N" : "Y", sensitive === "N" ? "N" : sensitive === "인증" ? "Y" : "TBD",
      retention, deletion, sensitive === "N" ? (/status|priority|permission|visibility/.test(columnName) ? "Y" : "N") : "Y",
      "ACTIVE", documentVersion, documentVersion, "N/A", jira, today, keyText === "N/A" ? "원본에 별도 키·제약 없음" : `원본 키/제약: ${keyText}`, "",
    ]);
  });
}

const indexSource = parseNamedMarkdownTable("## G. 핵심 인덱스", "| 인덱스 | 키/조건 |");
function tableFromIndex(name) {
  return tableOrder.find((table) => name.includes(`_${table.replace("care_relationship", "care_relationship").replace("care_record", "care_record")}_`))
    || tableOrder.find((table) => name.startsWith(`ix_${table}_`) || name.startsWith(`uq_${table}_`)) || "TBD";
}

function parseIndexKey(raw) {
  const unique = raw.startsWith("UNIQUE ");
  const normalized = raw.replace(/^UNIQUE\s+/, "");
  const whereIndex = normalized.indexOf(" WHERE ");
  return {
    unique,
    key: whereIndex >= 0 ? normalized.slice(0, whereIndex) : normalized,
    predicate: whereIndex >= 0 ? normalized.slice(whereIndex + 7) : "N/A",
  };
}

const indexHeaders = ["인덱스 ID", "인덱스명", "테이블명", "인덱스 유형", "UNIQUE 여부", "대상 컬럼 또는 표현식", "컬럼 순서", "정렬 방향", "NULL 정렬", "부분 인덱스 조건", "PostgreSQL operator class", "pgvector 거리 연산", "INCLUDE 컬럼", "대응 제약조건 ID", "사용 목적", "대표 조회 패턴", "필요성 근거", "예상 쓰기 비용", "객체 상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const indexRows = indexSource.rows.map(([name, keyCondition, purpose]) => {
  const parsed = parseIndexKey(keyCondition);
  const includeMatch = parsed.key.match(/\s+INCLUDE\s+(.+)$/);
  const key = includeMatch ? parsed.key.replace(/\s+INCLUDE\s+.+$/, "") : parsed.key;
  return [
    `IDX_${name.toUpperCase()}`, name, tableFromIndex(name), "BTREE", parsed.unique ? "Y" : "N", key,
    key.replace(/[()]/g, "").split(",").map((v, i) => `${i + 1}:${v.trim()}`).join("; "), /DESC/.test(key) ? "혼합/명시" : "ASC(기본)",
    "PostgreSQL 기본", parsed.predicate, "N/A", "N/A", includeMatch ? includeMatch[1] : "N/A", parsed.unique ? `CONSTRAINT_${name.toUpperCase()}` : "N/A",
    purpose, purpose, "mvp-erd.md G절에 명시", parsed.unique ? "MEDIUM" : "LOW-MEDIUM", "ACTIVE", documentVersion, jira, "pgvector 인덱스는 모델·차원·측정 전까지 생성하지 않음",
  ];
});

const constraintHeaders = ["제약조건 ID", "제약조건명", "제약 유형", "테이블명", "대상 컬럼", "컬럼 순서", "참조 테이블", "참조 컬럼", "ON DELETE", "ON UPDATE", "조건식", "부분 적용 조건", "DB 구현 여부", "구현 계층", "업무 설명", "위반 시 의미", "관련 시나리오", "객체 상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const constraintRows = [];
for (const table of sourceTables) {
  constraintRows.push([`PK_${table.tableName}`.toUpperCase(), `pk_${table.tableName}`, "PK", table.tableName, "id", "1", "N/A", "N/A", "N/A", "N/A", "PRIMARY KEY", "N/A", "Y", "PostgreSQL", `${logicalTableNames[table.tableName]} 내부 식별자`, "행을 안정적으로 식별할 수 없음", "전체", "ACTIVE", documentVersion, jira, "원본 데이터 사전"]);
}
for (const row of columnRows) {
  const tableName = row[columnHeaders.indexOf("테이블 물리명")];
  const columnName = row[columnHeaders.indexOf("컬럼 물리명")];
  const fk = row[columnHeaders.indexOf("FK 여부")] === "Y";
  const keyNote = row[columnHeaders.indexOf("비고")];
  if (fk) {
    const onDeleteMap = {
      "robot.senior_id": "SET NULL", "conversation.scenario_id": "SET NULL", "care_record.scenario_id": "SET NULL",
      "onboarding_answer.source_conversation_id": "SET NULL", "memory.source_conversation_id": "SET NULL", "care_record.source_conversation_id": "SET NULL", "care_record.recipient_guardian_id": "SET NULL", "care_record.created_by_user_id": "SET NULL",
      "audit_log.actor_user_id": "SET NULL",
    };
    const id = `FK_${tableName}_${columnName}`.toUpperCase();
    constraintRows.push([id, id.toLowerCase(), "FK", tableName, columnName, "1", row[columnHeaders.indexOf("참조 테이블")], row[columnHeaders.indexOf("참조 컬럼")], onDeleteMap[`${tableName}.${columnName}`] || "RESTRICT", "NO ACTION", `${columnName} 참조 무결성`, "N/A", "Y", "PostgreSQL", row[columnHeaders.indexOf("컬럼 설명")], "고아 참조 또는 잘못된 업무 연결", "전체", "ACTIVE", documentVersion, jira, "FK action은 개인정보·안전 보존 정책 확정 후 Flyway에 반영"]);
  }
  if (keyNote.includes("CHECK")) {
    const id = `CHK_${tableName}_${columnName}`.toUpperCase();
    constraintRows.push([id, id.toLowerCase(), "CHECK", tableName, columnName, "1", "N/A", "N/A", "N/A", "N/A", keyNote.replace(/^원본 키\/제약:\s*/, ""), "N/A", "Y", "PostgreSQL", row[columnHeaders.indexOf("컬럼 설명")], "허용 범위 밖의 값 저장", "전체", "ACTIVE", documentVersion, jira, "정확한 SQL 표현은 Flyway 작성 시 승인"]);
  }
}
for (const idx of indexRows.filter((row) => row[4] === "Y")) {
  constraintRows.push([`CONSTRAINT_${idx[1].toUpperCase()}`, idx[1], "UNIQUE", idx[2], idx[5], idx[6], "N/A", "N/A", "N/A", "N/A", `UNIQUE ${idx[5]}`, idx[9], "Y", "PostgreSQL", idx[14], "중복 업무 객체 또는 멱등 부수효과 발생", "전체", "ACTIVE", documentVersion, jira, "동일 객체가 인덱스정의 시트에도 물리 구현으로 존재"]);
}
const serviceRules = [
  ["RULE_RELATION_DISTINCT_USERS", "care_relationship", "senior_id, guardian_id", "어르신과 보호자는 같은 사용자일 수 없음"],
  ["RULE_RELATION_USER_TYPES", "care_relationship", "senior_id, guardian_id", "senior_id는 SENIOR, guardian_id는 GUARDIAN이어야 함"],
  ["RULE_PRIMARY_MANAGES_RELATIONSHIPS", "care_relationship", "priority, permissions, status", "manageRelationships=true는 활성 PRIMARY에게만 허용"],
  ["RULE_ROBOT_ACTIVE_ASSIGNMENT", "robot", "senior_id, is_active, assigned_at, unassigned_at", "활성 배정의 필수 컬럼 조합과 사용자 유형을 검증"],
  ["RULE_AMBIENT_LATEST_WINS", "robot", "ambient_temperature_c, ambient_humidity_percent, ambient_observed_at, ambient_sensor_code", "온습도 값은 관측시각·센서 코드와 함께 저장하고 오래된 관측이 최신값을 덮어쓰지 못함"],
  ["RULE_ONBOARDING_SESSION_ACTIVE_ROBOT", "onboarding_session", "senior_id, robot_id", "세션 시작 시 현재 활성 배정 로봇과 대상 어르신이 일치하고 세션 도중 로봇을 바꾸지 않음"],
  ["RULE_ONBOARDING_PROJECTION", "onboarding_session", "senior_id, status, question_set_version, completed_at", "세션 원본 전이와 app_user onboarding projection을 한 트랜잭션에서 갱신"],
  ["RULE_ONBOARDING_SESSION_TERMINAL", "onboarding_session", "status, completed_at, ended_at, version", "종료 상태의 필수 시각을 검증하고 늦은 이벤트가 상태를 되돌리지 못함"],
  ["RULE_ONBOARDING_ANSWER_SESSION", "onboarding_answer", "session_id, question_code", "진행 중 세션과 해당 question set의 허용 문항만 답변을 캡처"],
  ["RULE_ONBOARDING_REVISION", "onboarding_answer", "session_id, question_code, revision", "새 수정본은 이전 최신 revision보다 1 증가하고 과거 답변을 덮지 않음"],
  ["RULE_ONBOARDING_EVENT_IDEMPOTENCY", "onboarding_answer", "client_event_id", "같은 로봇 답변 재전송은 기존 answer를 반환하고 추출을 다시 수행하지 않음"],
  ["RULE_ONBOARDING_STATUS_COMBINATION", "onboarding_answer", "processing_status, verification_status, confirmed_at", "처리·검증 상태의 허용 조합과 확인 시각을 검증"],
  ["RULE_ONBOARDING_SOURCE_MATCH", "onboarding_answer", "session_id, source_conversation_id, source_message_id", "답변 세션과 출처 대화의 어르신 및 원문 보존 중 messageId가 일치"],
  ["RULE_ONBOARDING_MATERIALIZATION", "onboarding_answer", "materialization_key, materialized_at, target_refs, processing_status", "확인된 최종 테이블 반영과 제한 대상 참조를 한 트랜잭션에서 한 번만 기록"],
  ["RULE_SCENARIO_ROBOT_ASSIGNMENT", "scenario", "senior_id, robot_id", "시나리오 생성 시 로봇의 당시 활성 어르신 배정과 일치"],
  ["RULE_CONVERSATION_SENIOR_MATCH", "conversation", "senior_id, scenario_id", "대화와 시나리오의 대상 어르신 일치"],
  ["RULE_MEMORY_SOURCE_MATCH", "memory", "senior_id, source_conversation_id, source_message_id", "기억과 출처 대화의 어르신 및 원문 보존 중 messageId 일치"],
  ["RULE_CARE_SOURCE_MATCH", "care_record", "senior_id, source_conversation_id, source_message_id", "돌봄 후보와 출처 대화의 어르신 및 원문 보존 중 messageId 일치"],
  ["RULE_CONSENT_GATE", "care_record", "senior_id, record_type, source_conversation_id, source_message_id", "건강·일정·공유 저장 전에 app_user 동의와 관계 권한을 재검증"],
  ["RULE_ONBOARDING_COMPLETION", "app_user", "onboarding_status, onboarding_version, onboarding_completed_at", "세션 원본의 현재 상태를 projection하고 COMPLETED는 질문 버전과 완료 시각을 동반"],
  ["RULE_MEMORY_NO_SELF_SUPERSEDE", "memory", "id, superseded_by_id", "기억은 자기 자신을 대체 대상으로 참조할 수 없음"],
  ["RULE_CARE_PARENT_MATCH", "care_record", "senior_id, parent_record_id, record_type", "부모·자식 어르신 일치와 허용 record_type 연결"],
  ["RULE_CARE_NO_SELF_PARENT", "care_record", "id, parent_record_id", "돌봄 기록은 자기 자신을 부모로 참조할 수 없음"],
  ["RULE_CARE_SCENARIO_MATCH", "care_record", "senior_id, scenario_id", "돌봄 기록과 시나리오의 대상 어르신 일치"],
  ["RULE_NOTIFICATION_RELATION", "care_record", "senior_id, recipient_guardian_id", "알림 생성 시 수신 보호자가 대상 어르신과 활성 관계"],
  ["RULE_TERMINAL_STATE", "scenario", "status, version", "종료 상태는 늦은 MQTT·HTTP 결과로 되돌리지 않음"],
  ["RULE_EVENT_IDEMPOTENCY", "scenario", "external_event_id", "동일 eventId의 최종 업무 부수효과는 한 번만 적용"],
  ["RULE_VISION_REQUEST_IDEMPOTENCY", "scenario", "vision_request_id", "하나의 Vision requestId에는 하나의 최종 결과만 적용"],
  ["RULE_CARE_EVENT_IDEMPOTENCY", "care_record", "external_event_id", "동일 오프라인 돌봄 결과를 한 번만 반영"],
  ["RULE_REST_GUARD_ALLOWLIST", "robot", "current_mode", "REST_GUARD 중 일반 능동 기능은 억제하고 호출·안전·긴급 기능만 허용"],
  ["RULE_TIME_ORDER", "scenario", "occurred_at, started_at, completed_at", "완료 시각은 시작·발생 시각보다 빠를 수 없음"],
  ["RULE_MEMORY_DELETE_TOMBSTONE", "memory", "lifecycle_status, content, embedding, purged_at", "DELETED 상태는 본문·임베딩 제거와 purged_at 기록을 동반"],
];
for (const [id, table, columns, description] of serviceRules) {
  constraintRows.push([id, id.toLowerCase(), id.includes("STATE") ? "STATE_TRANSITION" : "SERVICE_RULE", table, columns, columns.split(",").map((_, i) => i + 1).join(","), "N/A", "N/A", "N/A", "N/A", description, "N/A", "N", "Spring 서비스", description, "권한 누출, 중복 부수효과 또는 업무 정합성 훼손", "귀가·대화·돌봄", "ACTIVE", documentVersion, jira, "mvp-erd.md K절 교차행 규칙"]);
}

const jsonHeaders = ["JSONB 구조 ID", "테이블명", "컬럼명", "스키마 버전", "JSON 경로", "부모 경로", "키 이름", "데이터 타입", "필수 여부", "NULL 허용 여부", "배열 여부", "배열 항목 타입", "허용 코드 그룹", "설명", "값 형식", "비식별 예시 값", "민감정보 여부", "금지 정보", "보존 정책", "하위 호환성 규칙", "객체 상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const jsonDefinitions = [];
function addJson(structure, table, column, pathValue, type, required, description, example, sensitive = "N", code = "N/A", forbidden = "인증정보·생체정보·원시 센서·전체 요청/응답 금지", retention = "컬럼 보존 정책과 동일") {
  const parts = pathValue.replace(/^\$\.?/, "").split(".");
  const key = parts.at(-1) || "$";
  const parent = parts.length <= 1 ? "$" : `$.${parts.slice(0, -1).join(".")}`;
  const isArray = /\[\]$/.test(pathValue) || type.startsWith("array<");
  const structureVersion = structure.match(/_V(\d+)$/)?.[1] || "1";
  jsonDefinitions.push([structure, table, column, structureVersion, pathValue, parent, key.replace(/\[\]$/, ""), type, required ? "Y" : "N", type.includes("null") ? "Y" : "N", isArray ? "Y" : "N", isArray ? type.replace(/^array<|>$/g, "") : "N/A", code, description, type, example, sensitive, forbidden, retention, "알 수 없는 최상위 키는 기본 거부; schemaVersion 변경 시 이전 reader 유지", "ACTIVE", documentVersion, jira, "Spring DTO validator 적용"]);
}

const jsonSpecs = [
  ["JSON_ONBOARDING_EXTRACTION_V1", "onboarding_answer", "extraction_jsonb", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"],
    ["$.candidates[]", "array<object>", true, "확인 전 원자 사실 후보 목록", "축약 예시 참조", "Y"],
    ["$.candidates[].candidateId", "opaque string(64)", true, "한 답변 안의 후보 식별자", "candidate-1", "간접"],
    ["$.candidates[].targetType", "enum string", true, "최종 반영 후보 도메인", "MEMORY", "Y", "CODE_ONBOARDING_TARGET_TYPE"],
    ["$.candidates[].factType", "enum string", true, "대상 도메인의 원자 사실 유형", "HOBBY", "Y"],
    ["$.candidates[].value", "scalar or object", true, "사용자 확인 전 최소 후보 값", "화초 가꾸기", "Y"],
  ]],
  ["JSON_ONBOARDING_TARGET_REFS_V1", "onboarding_answer", "target_refs", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"],
    ["$.items[]", "array<object>", true, "최종 반영 대상 참조 목록", "축약 예시 참조", "Y"],
    ["$.items[].targetType", "enum string", true, "반영된 최종 도메인", "MEMORY", "Y", "CODE_ONBOARDING_TARGET_TYPE"],
    ["$.items[].targetId", "uuid string", true, "반영된 app_user/memory/care_record ID", "00000000-0000-4000-8000-000000000301", "간접"],
    ["$.items[].fieldNames[]", "array<string>", false, "APP_USER에서 변경한 허용 필드명", "preferred_name", "간접"],
  ]],
  ["JSON_APP_USER_PREFERENCES_V2", "app_user", "conversation_preferences", [
    ["$.schemaVersion", "integer", true, "구조 버전", "2"], ["$.responseLength", "enum string", false, "응답 길이 선호", "SHORT", "N/A", "CODE_RESPONSE_LENGTH"],
    ["$.speechRate", "enum string", false, "말하기 속도 선호", "SLOW"], ["$.speechVolume", "enum string", false, "말하기 음량 선호", "LOUD"],
    ["$.proactiveSpeechLevel", "integer", false, "능동 발화 수준", "2"], ["$.reminiscenceEnabled", "boolean", false, "추억 회상 대화 사용 여부", "true"],
    ["$.humorLevel", "integer", false, "유머 수준", "1"], ["$.healthSuggestionSensitivity", "enum string", false, "건강 제안 민감도", "CAUTIOUS"],
    ["$.needsRepeatedExplanation", "boolean", false, "반복 설명 선호 여부", "false"], ["$.preferredConversationWindows[]", "array<string>", false, "선호 대화 시간대", "09:00-11:00", "Y"],
    ["$.defaultReminderLeadMinutes", "integer", false, "기본 알림 사전 시간(분)", "60"], ["$.avoidedTopics[]", "array<string>", false, "피하고 싶은 대화 주제", "정치", "Y"],
  ]],
  ["JSON_RELATIONSHIP_PERMISSIONS_V1", "care_relationship", "permissions", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"], ["$.viewDashboard", "boolean", true, "대시보드 조회 권한", "true"],
    ["$.manageSeniorProfile", "boolean", true, "어르신 프로필 관리 권한", "false"], ["$.manageMedication", "boolean", true, "복약 관리 권한", "true"],
    ["$.manageSchedule", "boolean", true, "일정 관리 권한", "true"], ["$.verifyMemory", "boolean", true, "기억 검증 권한", "false"],
    ["$.receiveEmergencyAlert", "boolean", true, "긴급 알림 수신 권한", "true"], ["$.manageRelationships", "boolean", true, "보호 관계 관리 권한; 활성 PRIMARY만 true", "false"],
  ]],
  ["JSON_SCENARIO_TIMELINE_V1", "scenario", "timeline", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"], ["$.events[]", "array<object>", true, "주요 상태 변화만 담는 작은 이벤트 목록", "축약 예시 참조", "Y"],
    ["$.events[].eventId", "opaque string(64)", true, "타임라인 이벤트 멱등 ID", "01K0EXAMPLE000000000000000", "간접"],
    ["$.events[].type", "enum string", true, "업무 단계 유형", "NAVIGATION"], ["$.events[].status", "enum string", true, "해당 단계 상태", "SUCCEEDED"],
    ["$.events[].occurredAt", "ISO-8601 string", true, "단계 발생 시각", "2026-01-15T00:00:00Z"], ["$.events[].commandId", "opaque string(64)", false, "Robot 명령 ID", "01K0COMMAND00000000000000", "간접"],
    ["$.events[].requestId", "opaque string(64)", false, "AI 작업 요청 ID", "01K0REQUEST00000000000000", "간접"], ["$.events[].reasonCode", "enum string", false, "실패·안전 정지 사유 코드", "OBSTACLE_STATE_UNCERTAIN"],
  ]],
  ["JSON_CONVERSATION_MESSAGES_V1", "conversation", "messages", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"], ["$.items[]", "array<object>", true, "최근 최대 12턴, 24개 메시지", "축약 예시 참조", "Y"],
    ["$.items[].messageId", "uuid string", true, "논리 메시지 ID", "00000000-0000-4000-8000-000000000101", "간접"],
    ["$.items[].role", "enum string", true, "발화 주체", "SENIOR", "N/A", "CODE_MESSAGE_ROLE"], ["$.items[].text", "string", true, "텍스트 발화 본문", "오늘 산책이 즐거웠어요.", "Y"],
    ["$.items[].occurredAt", "ISO-8601 string", true, "발화 발생 시각", "2026-01-15T00:00:00Z"], ["$.items[].generationRequestId", "opaque string(64)", false, "생성 요청 추적 ID", "01K0REQUEST00000000000000", "간접"],
    ["$.items[].fallbackUsed", "boolean", false, "fallback 사용 여부", "false"], ["$.items[].speechCommandId", "opaque string(64)", false, "음성 재생 명령 ID", "01K0COMMAND00000000000000", "간접"],
    ["$.items[].speechStatus", "enum string", false, "음성 재생 상태", "REQUESTED"],
  ]],
  ["JSON_CARE_RECORD_DETAILS_V1", "care_record", "details", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"], ["$.recordType", "enum string", true, "행의 record_type과 일치", "MEDICATION_SCHEDULE", "Y", "CODE_CARE_RECORD_TYPE"],
    ["$.medicationName", "string", false, "약물명", "가상 약 A", "Y"], ["$.dose", "object", false, "복용량 구조", "축약 예시 참조", "Y"],
    ["$.dose.amount", "number", false, "복용량 수치", "1", "Y"], ["$.dose.unit", "enum string", false, "복용량 단위", "TABLET", "Y"],
    ["$.instructions", "string", false, "복용 지침", "식후 복용", "Y"], ["$.confirmationRequired", "boolean", false, "확인 필요 여부", "true", "Y"],
    ["$.indicatorName", "enum string", false, "인지 참고 지표명", "RECENT_MEMORY_CHANGE", "Y"], ["$.score", "number", false, "참고 점수", "0.42", "파생"],
    ["$.interpretation", "enum string", false, "참고 해석", "REVIEW_RECOMMENDED", "Y"], ["$.medicalDiagnosis", "boolean", false, "의료 진단 아님을 표시", "false", "Y"],
    ["$.notificationKind", "enum string", false, "보호자 알림 종류", "FALL_SUSPECTED", "Y"], ["$.channel", "enum string", false, "알림 채널", "PUSH", "Y"],
    ["$.deliveryResultCode", "enum string", false, "공급자 전달 결과 코드", "ACCEPTED_BY_PROVIDER", "간접"], ["$.escalationLevel", "integer", false, "단계 알림 수준", "1", "간접"],
    ["$.restState", "enum string", false, "휴식 최종 상태", "RESTING", "Y", "CODE_REST_STATE"], ["$.detectionMethod", "enum string", false, "휴식 판정 방식", "VISION_POSTURE_DURATION"],
    ["$.posture", "enum string", false, "휴식 판정 자세", "LYING", "Y"], ["$.detectionDurationSeconds", "integer", false, "임계값을 충족한 실제 지속시간", "600", "Y"],
    ["$.policyVersion", "string", false, "휴식·환경 판정 정책 버전", "rest-policy-v1"], ["$.endedAt", "ISO-8601 date-time or null", false, "휴식 종료 시각", null, "Y"],
    ["$.backgroundCapabilities[]", "array<enum string>", false, "휴식 중 허용된 백그라운드 기능", "CALL_DETECTION", "Y"],
    ["$.temperatureC", "number", false, "환경 관찰 온도(°C)", "29.2", "Y"], ["$.humidityPercent", "number", false, "환경 관찰 상대습도(%RH)", "72.0", "Y"],
    ["$.comfortAssessment", "enum string", false, "환경 쾌적도 판정", "TOO_HOT", "Y", "CODE_ENVIRONMENT_COMFORT"],
    ["$.thresholdReason", "enum string", false, "환경 임계 사건 사유", "TEMPERATURE_HIGH"], ["$.userResponse", "string", false, "사용자의 짧은 주관적 응답", "조금 더워", "Y"],
  ]],
  ["JSON_CARE_RECORD_RECURRENCE_V1", "care_record", "recurrence", [
    ["$.schemaVersion", "integer", true, "구조 버전", "1"], ["$.frequency", "enum string", true, "반복 빈도", "DAILY", "Y", "CODE_RECURRENCE_FREQUENCY"],
    ["$.interval", "integer", true, "반복 간격; 양의 정수", "1", "Y"], ["$.timeZone", "IANA timezone string", true, "현지 반복 계산 시간대", "Asia/Seoul", "Y"],
    ["$.byDay[]", "array<enum string>", false, "요일 목록", "MON", "Y"], ["$.localTimes[]", "array<HH:mm string>", false, "현지 실행 시각 목록", "08:00", "Y"],
    ["$.until", "ISO-8601 date-time or null", false, "반복 종료 시각", "2026-12-31T14:59:59Z", "Y"],
  ]],
];
for (const [structure, table, column, specs] of jsonSpecs) {
  for (const [p, type, required, description, example, sensitive = "N", code = "N/A"] of specs) {
    addJson(structure, table, column, p, type, required, description, example, sensitive, code,
      structure === "JSON_CARE_RECORD_DETAILS_V1" ? "비밀번호·토큰·연락처 복제·대화 원문·생체정보·전체 모델/HTTP body 금지"
        : structure.startsWith("JSON_ONBOARDING_") ? "전체 대화·프롬프트·모델 응답·원본 음성·인증정보·생체정보·원시 센서 금지"
          : "인증정보·생체정보·원시 센서·전체 요청/응답 금지",
      structure === "JSON_CONVERSATION_MESSAGES_V1" ? "원문 7일"
        : structure === "JSON_ONBOARDING_EXTRACTION_V1" ? "확인 완료 또는 만료까지 단기"
          : structure === "JSON_ONBOARDING_TARGET_REFS_V1" ? "온보딩 원장 정책"
            : "컬럼 보존 정책과 동일");
  }
}

const vectorHeaders = ["벡터 정의 ID", "테이블명", "컬럼명", "PostgreSQL 타입", "벡터 차원", "차원 확정 여부", "임베딩 대상", "임베딩 모델명", "모델 버전", "거리 함수", "정규화 여부", "인덱스 유형", "operator class", "재생성 가능 여부", "원본 데이터 참조", "민감정보 여부", "보존 정책", "삭제 연계 정책", "객체 상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const vectorRows = [["VEC_MEMORY_EMBEDDING", "memory", "embedding", "vector(<EMBEDDING_DIM>)", "TBD", "N", "memory.content의 허용된 자연어 기억", "TBD", "TBD", "TBD", "TBD", "NONE(정확 검색)", "N/A", "Y", "memory.id 및 content", "Y", "기억 정책", "기억 삭제 시 벡터를 NULL 처리하고 purged_at 기록", "PLANNED", documentVersion, jira, "주소·전화·약 복용량·인증정보·로봇 좌표·생체정보 임베딩 금지"]];

const codeHeaders = ["코드 그룹 ID", "코드 그룹명", "사용 테이블", "사용 컬럼", "코드값", "코드 논리명", "설명", "표시 순서", "시작 상태 여부", "종료 상태 여부", "허용 이전 상태", "허용 다음 상태", "활성 여부", "최초 도입 버전", "폐기 버전", "최종 변경 Jira", "비고"];
const codeGroups = [
  ["CODE_USER_TYPE", "사용자 유형", "app_user", "user_type", ["SENIOR", "GUARDIAN"]],
  ["CODE_USER_STATUS", "사용자 상태", "app_user", "status", ["ACTIVE", "SUSPENDED", "WITHDRAWN"]],
  ["CODE_ONBOARDING_STATUS", "온보딩 projection 상태", "app_user", "onboarding_status", ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "DECLINED", "CANCELLED", "EXPIRED"]],
  ["CODE_CONSENT_STATUS", "동의 상태", "app_user", "personalization_consent_status, health_data_consent_status, schedule_consent_status, guardian_sharing_consent_status", ["NOT_ASKED", "GRANTED", "DENIED", "REVOKED"]],
  ["CODE_RELATIONSHIP_PRIORITY", "보호자 우선순위", "care_relationship", "priority", ["PRIMARY", "SECONDARY"]],
  ["CODE_RELATIONSHIP_STATUS", "돌봄 관계 상태", "care_relationship", "status", ["PENDING", "ACTIVE", "DISCONNECT_REQUESTED", "ENDED", "REVOKED"]],
  ["CODE_ROBOT_STATUS", "로봇 수명 상태", "robot", "status", ["REGISTERED", "ACTIVE", "MAINTENANCE", "RETIRED"]],
  ["CODE_ROBOT_MODE", "로봇 업무 모드", "robot", "current_mode", ["IDLE", "SCENARIO_ACTIVE", "REST_GUARD", "SAFE_STOP"]],
  ["CODE_ONBOARDING_SESSION_STATUS", "온보딩 세션 상태", "onboarding_session", "status", ["IN_PROGRESS", "COMPLETED", "DECLINED", "CANCELLED", "EXPIRED"]],
  ["CODE_ONBOARDING_PROCESSING_STATUS", "온보딩 답변 처리 상태", "onboarding_answer", "processing_status", ["CAPTURED", "NEEDS_CLARIFICATION", "NEEDS_CONFIRMATION", "PROCESSED", "SKIPPED", "REJECTED"]],
  ["CODE_ONBOARDING_VERIFICATION_STATUS", "온보딩 답변 검증 상태", "onboarding_answer", "verification_status", ["UNVERIFIED", "USER_CONFIRMED", "GUARDIAN_CONFIRMED", "DOCUMENT_VERIFIED", "REJECTED"]],
  ["CODE_ONBOARDING_TARGET_TYPE", "온보딩 반영 대상 유형", "onboarding_answer", "extraction_jsonb, target_refs", ["APP_USER", "MEMORY", "CARE_RECORD"]],
  ["CODE_SCENARIO_TYPE", "시나리오 유형", "scenario", "scenario_type", ["HOMECOMING", "FALL_RESPONSE", "MANUAL_INTERACTION"]],
  ["CODE_SCENARIO_STATUS", "시나리오 굵은 상태", "scenario", "status", ["RECEIVED", "MOVING_TO_ENTRANCE", "CHECKING_INTERACTION", "CONVERSING", "RETURN_DECISION", "RETURNING_TO_DEFAULT", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]],
  ["CODE_NAVIGATION_STATUS", "현관 이동 상태", "scenario", "navigation_status", ["REQUESTED", "IN_PROGRESS", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"]],
  ["CODE_VISION_STATUS", "Vision 상태", "scenario", "vision_status", ["REQUESTED", "IN_PROGRESS", "SUCCEEDED", "NO_PERSON", "NOT_ALLOWED", "FAILED", "TIMED_OUT"]],
  ["CODE_RETURN_STATUS", "기본 위치 복귀 상태", "scenario", "return_status", ["NOT_EVALUATED", "READY", "REQUESTED", "IN_PROGRESS", "SUCCEEDED", "SAFE_STOP"]],
  ["CODE_CONVERSATION_STATUS", "대화 상태", "conversation", "status", ["OPEN", "COMPLETED", "FAILED", "CANCELLED"]],
  ["CODE_EXECUTION_LOCATION", "AI 실행 위치", "conversation", "execution_location", ["LOCAL", "CLOUD"]],
  ["CODE_GENERATION_STATUS", "대화 생성 상태", "conversation", "generation_status", ["NOT_STARTED", "RUNNING", "SUCCEEDED", "FAILED"]],
  ["CODE_MEMORY_TYPE", "기억 유형", "memory", "memory_type", ["PERSONAL_RELATIONSHIP", "PREFERENCE", "HOBBY", "DAILY_ROUTINE", "LIFE_EVENT", "FAMILY_MEMORY", "EMOTIONAL_EVENT", "CONVERSATION_SUMMARY", "OTHER"]],
  ["CODE_MEMORY_VERIFICATION", "기억 검증 상태", "memory", "verification_status", ["UNVERIFIED", "AUTO_ACCEPTED", "USER_CONFIRMED", "GUARDIAN_CONFIRMED", "REJECTED"]],
  ["CODE_MEMORY_LIFECYCLE", "기억 생명주기", "memory", "lifecycle_status", ["ACTIVE", "DISPUTED", "SUPERSEDED", "EXPIRED", "DELETED"]],
  ["CODE_MEMORY_VISIBILITY", "기억 공개 범위", "memory", "visibility", ["PRIVATE", "SHARED_WITH_PRIMARY", "SHARED_WITH_GUARDIANS"]],
  ["CODE_EMBEDDING_STATUS", "임베딩 생성 상태", "memory", "embedding_generation_status", ["NOT_REQUESTED", "REQUESTED", "GENERATED", "FAILED", "REGENERATION_REQUIRED"]],
  ["CODE_CARE_RECORD_TYPE", "돌봄 기록 유형", "care_record", "record_type", ["HEALTH_CONDITION", "ALLERGY", "PHYSICAL_LIMITATION", "MEDICATION", "MEDICATION_SCHEDULE", "MEDICATION_REMINDER", "MEDICATION_TAKEN", "APPOINTMENT", "PERSONAL_SCHEDULE", "HEALTH_OBSERVATION", "REST_OBSERVATION", "ENVIRONMENT_OBSERVATION", "COGNITIVE_ASSESSMENT", "GUARDIAN_NOTIFICATION"]],
  ["CODE_CARE_SOURCE_TYPE", "돌봄 정보 출처", "care_record", "source_type", ["USER", "GUARDIAN", "ROBOT", "AI", "SYSTEM"]],
  ["CODE_CARE_VERIFICATION", "돌봄 검증 상태", "care_record", "verification_status", ["UNVERIFIED", "USER_CONFIRMED", "GUARDIAN_CONFIRMED", "DOCUMENT_VERIFIED", "REJECTED"]],
  ["CODE_REST_STATE", "휴식 상태", "care_record", "details.restState", ["RESTING", "AWAKE"]],
  ["CODE_ENVIRONMENT_COMFORT", "환경 쾌적도", "care_record", "details.comfortAssessment", ["TOO_HOT", "TOO_COLD", "TOO_HUMID", "TOO_DRY", "COMFORTABLE"]],
  ["CODE_AUDIT_ACTOR_TYPE", "감사 행위자 유형", "audit_log", "actor_type", ["SENIOR", "GUARDIAN", "SYSTEM", "ROBOT"]],
  ["CODE_AUDIT_ACTION_TYPE", "감사 행위 유형", "audit_log", "action_type", ["CREATE", "UPDATE", "VERIFY", "REJECT", "DELETE", "CHANGE_VISIBILITY", "LINK", "UNLINK"]],
  ["CODE_MESSAGE_ROLE", "대화 메시지 역할", "conversation", "messages", ["SENIOR", "ROBOT"]],
  ["CODE_RECURRENCE_FREQUENCY", "반복 빈도", "care_record", "recurrence", ["DAILY", "WEEKLY"]],
];

const transitions = {
  CODE_ONBOARDING_STATUS: { NOT_STARTED: ["IN_PROGRESS"], IN_PROGRESS: ["COMPLETED", "DECLINED", "CANCELLED", "EXPIRED"], COMPLETED: [], DECLINED: ["IN_PROGRESS"], CANCELLED: ["IN_PROGRESS"], EXPIRED: ["IN_PROGRESS"] },
  CODE_ONBOARDING_SESSION_STATUS: { IN_PROGRESS: ["COMPLETED", "DECLINED", "CANCELLED", "EXPIRED"], COMPLETED: [], DECLINED: [], CANCELLED: [], EXPIRED: [] },
  CODE_ONBOARDING_PROCESSING_STATUS: { CAPTURED: ["NEEDS_CLARIFICATION", "NEEDS_CONFIRMATION", "PROCESSED", "SKIPPED", "REJECTED"], NEEDS_CLARIFICATION: ["NEEDS_CONFIRMATION", "PROCESSED", "REJECTED"], NEEDS_CONFIRMATION: ["PROCESSED", "REJECTED"], PROCESSED: [], SKIPPED: [], REJECTED: [] },
  CODE_ONBOARDING_VERIFICATION_STATUS: { UNVERIFIED: ["USER_CONFIRMED", "GUARDIAN_CONFIRMED", "DOCUMENT_VERIFIED", "REJECTED"], USER_CONFIRMED: [], GUARDIAN_CONFIRMED: [], DOCUMENT_VERIFIED: [], REJECTED: [] },
  CODE_CONSENT_STATUS: { NOT_ASKED: ["GRANTED", "DENIED"], GRANTED: ["REVOKED"], DENIED: ["GRANTED"], REVOKED: ["GRANTED"] },
  CODE_RELATIONSHIP_STATUS: { PENDING: ["ACTIVE"], ACTIVE: ["DISCONNECT_REQUESTED", "REVOKED"], DISCONNECT_REQUESTED: ["ENDED"], ENDED: ["PENDING"], REVOKED: ["PENDING"] },
  CODE_SCENARIO_STATUS: { RECEIVED: ["MOVING_TO_ENTRANCE", "CANCELLED"], MOVING_TO_ENTRANCE: ["CHECKING_INTERACTION", "FAILED", "CANCELLED", "TIMED_OUT"], CHECKING_INTERACTION: ["CONVERSING", "RETURN_DECISION", "CANCELLED", "TIMED_OUT"], CONVERSING: ["RETURN_DECISION", "FAILED", "CANCELLED"], RETURN_DECISION: ["RETURNING_TO_DEFAULT", "COMPLETED"], RETURNING_TO_DEFAULT: ["COMPLETED", "CANCELLED", "TIMED_OUT"], COMPLETED: [], FAILED: [], CANCELLED: [], TIMED_OUT: [] },
  CODE_CONVERSATION_STATUS: { OPEN: ["COMPLETED", "FAILED", "CANCELLED"], COMPLETED: [], FAILED: [], CANCELLED: [] },
  CODE_MEMORY_VERIFICATION: { UNVERIFIED: ["AUTO_ACCEPTED", "USER_CONFIRMED", "GUARDIAN_CONFIRMED", "REJECTED"] },
  CODE_MEMORY_LIFECYCLE: { ACTIVE: ["DISPUTED", "EXPIRED", "DELETED"], DISPUTED: ["SUPERSEDED", "DELETED"], SUPERSEDED: ["DELETED"], EXPIRED: ["DELETED"] },
};
const codeRows = [];
for (const [groupId, groupName, table, column, values] of codeGroups) {
  values.forEach((value, index) => {
    const map = transitions[groupId] || {};
    const next = map[value] || [];
    const previous = Object.entries(map).filter(([, allowed]) => allowed.includes(value)).map(([from]) => from);
    const start = index === 0 && Object.keys(map).length > 0 ? "Y" : "N";
    const terminal = Object.keys(map).length > 0 && next.length === 0 ? "Y" : "N";
    codeRows.push([groupId, groupName, table, column, value, value.replace(/_/g, " "), `${groupName}의 ${value} 값`, index + 1, start, terminal, previous.length ? previous.join(", ") : "N/A", next.length ? next.join(", ") : "N/A", "Y", documentVersion, "N/A", jira, "원본 상태·코드 목록 기준"]);
  });
}

const mappingHeaders = ["매핑 ID", "도메인", "인터페이스 유형", "인터페이스명", "엔드포인트, 토픽 또는 메시지명", "방향", "외부 필드 경로", "외부 타입", "필수 여부", "대상 테이블", "대상 컬럼", "변환 규칙", "ID 형식", "시간 형식", "멱등성 키 여부", "민감정보 여부", "관련 OpenAPI 또는 문서 경로", "객체 상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const mappingRows = [
  ["MAP-SCENARIO-EXTERNAL-EVENT-ID", "AIoT", "MQTT", "IoT 센서 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "eventId", "string(<=64)", "Y", "scenario", "external_event_id", "원문 보존; 동일 이벤트 재전송은 같은 값", "불투명 문자열(UUIDv4/v7 또는 ULID 후보)", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "PRESENCE_DETECTED INBOUND만 귀가 트리거"],
  ["MAP-SCENARIO-OCCURRED-AT", "AIoT", "MQTT", "IoT 센서 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "occurredAt", "ISO-8601 date-time", "Y", "scenario", "occurred_at", "타임존 포함 문자열을 UTC timestamptz로 변환", "N/A", "ISO-8601→UTC", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "received_at과 별도 관리"],
  ["MAP-SCENARIO-TRIGGER-DEVICE", "AIoT", "MQTT", "IoT 센서 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "sourceId", "string", "Y", "scenario", "trigger_device_code", "토픽 deviceId와 일치 검증 후 원문 저장", "등록 장치 코드", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "device FK 없음"],
  ["MAP-NAVIGATION-COMMAND-ID", "Robot", "MQTT", "NAVIGATE 명령", "bomi/v1/robot/{robotId}/commands", "OUT", "commandId", "string(<=64)", "Y", "scenario", "navigation_command_id", "DB에 먼저 저장한 뒤 같은 ID로 발행·재발행", "불투명 문자열", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "부분 UNIQUE 권장"],
  ["MAP-NAVIGATION-WAYPOINT", "Robot", "MQTT", "NAVIGATE 명령", "bomi/v1/robot/{robotId}/commands", "OUT", "payload.waypointId", "enum string", "Y", "scenario", "destination_waypoint", "현관 이동은 ENTRANCE", "논리 waypoint", "N/A", "N", "Y", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "좌표·Nav2 파라미터는 저장·전송하지 않음"],
  ["MAP-RETURN-COMMAND-ID", "Robot", "MQTT", "기본 위치 NAVIGATE", "bomi/v1/robot/{robotId}/commands", "OUT", "commandId", "string(<=64)", "Y", "scenario", "return_command_id", "안전 조건 확인 후 DB에 먼저 저장", "불투명 문자열", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "DEFAULT_POSITION 전용"],
  ["MAP-RETURN-DESTINATION", "Robot", "MQTT", "기본 위치 NAVIGATE", "bomi/v1/robot/{robotId}/commands", "OUT", "payload.waypointId", "enum string", "Y", "scenario", "return_destination", "DEFAULT_POSITION만 허용", "논리 waypoint", "N/A", "N", "Y", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "충전소 복귀 금지"],
  ["MAP-ROBOT-EXTERNAL-ID", "Robot", "MQTT", "Robot 공통 메시지", "bomi/v1/robot/{robotId}/*", "BIDIRECTIONAL", "robotId", "string(<=64)", "Y", "robot", "serial_number", "토픽 robotId와 payload를 일치 검증하고 등록 시리얼로 조회", "외부 등록 코드", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "내부 robot.id UUID와 구분"],
  ["MAP-ONBOARDING-EVENT-ID", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "eventId", "string(<=64)", "Y", "onboarding_answer", "client_event_id", "전역 UNIQUE 원문 저장; 같은 답변 재전송은 같은 ID", "불투명 문자열(UUIDv4/v7 또는 ULID 후보)", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "답변 저장 멱등 키"],
  ["MAP-ONBOARDING-SESSION-ID", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.sessionId", "uuid string", "Y", "onboarding_answer", "session_id", "UUID 변환 후 세션의 robot/status 검증", "UUID", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "IN_PROGRESS 세션만 허용"],
  ["MAP-ONBOARDING-QUESTION-CODE", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.questionCode", "string(<=50)", "Y", "onboarding_answer", "question_code", "세션 question_set_version의 allowlist 검증", "질문 코드", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "질문 문구는 DB에 저장하지 않음"],
  ["MAP-ONBOARDING-REVISION", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.revision", "integer>=1", "Y", "onboarding_answer", "revision", "smallint 변환; 이전 최신 revision+1 검증", "N/A", "N/A", "N", "N", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "세션·문항·revision UNIQUE"],
  ["MAP-ONBOARDING-OCCURRED-AT", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "occurredAt", "ISO-8601 date-time", "Y", "onboarding_answer", "answered_at", "UTC timestamptz로 변환", "N/A", "ISO-8601→UTC", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "수신 시각과 구분"],
  ["MAP-ONBOARDING-TRANSCRIPT", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.transcriptExcerpt", "short string", "N", "onboarding_answer", "transcript_excerpt", "길이·민감정보 검증 후 최소 발췌만 저장; 기본 7일 파기", "N/A", "N/A", "N", "Y", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "전체 STT·음성 금지"],
  ["MAP-ONBOARDING-STT-CONFIDENCE", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.sttConfidence", "number[0,1]", "N", "onboarding_answer", "stt_confidence", "numeric(5,4); 모델명·버전 동반", "N/A", "N/A", "N", "민감 파생", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "기본 30일 단기"],
  ["MAP-ONBOARDING-STT-MODEL-NAME", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.sttModelName", "string(<=200)", "조건부", "onboarding_answer", "stt_model_name", "confidence가 있으면 필수", "N/A", "N/A", "N", "N", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "기본 30일 단기"],
  ["MAP-ONBOARDING-STT-MODEL-VERSION", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.sttModelVersion", "string(<=100)", "조건부", "onboarding_answer", "stt_model_version", "confidence가 있으면 필수", "N/A", "N/A", "N", "N", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "기본 30일 단기"],
  ["MAP-ONBOARDING-POLICY-VERSION", "온보딩", "MQTT", "온보딩 답변 캡처", "bomi/v1/robot/{robotId}/events", "IN", "payload.processingPolicyVersion", "string(<=50)", "Y", "onboarding_answer", "processing_policy_version", "원문 정책 버전 저장", "정책 버전", "N/A", "N", "N", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "신뢰도 해석 기준"],
  ["MAP-VISION-REQUEST-ID", "Vision AI", "REST", "Vision 인식 시작", "POST /api/v1/recognitions", "OUT", "requestId", "string(<=64)", "Y", "scenario", "vision_request_id", "API 호출 전에 requestId와 상태를 저장", "불투명 문자열", "N/A", "Y", "간접", "backend/src/main/resources/static/openapi/vision-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "Callback이 202보다 먼저 올 수 있음"],
  ["MAP-VISION-SCENARIO-ID", "Vision AI", "REST", "Vision 인식 시작/결과", "POST /api/v1/recognitions; callback", "BIDIRECTIONAL", "scenarioId", "uuid string", "Y", "scenario", "id", "내부 UUID의 표준 문자열 직렬화", "UUID", "N/A", "N", "간접", "backend/src/main/resources/static/openapi/vision-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "내부 엔티티 ID는 UUID"],
  ["MAP-VISION-SCENARIO-TYPE", "Vision AI", "REST", "Vision 인식 시작", "POST /api/v1/recognitions", "OUT", "scenarioType", "enum string", "Y", "scenario", "scenario_type", "HOMECOMING_WELCOME ↔ HOMECOMING 변환은 팀 승인 필요", "N/A", "N/A", "N", "간접", "backend/src/main/resources/static/openapi/vision-ai.openapi.yaml", "PLANNED", documentVersion, jira, "VAL-030 계약 enum 불일치 참조"],
  ["MAP-VISION-CALLBACK-EVENT-ID", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "eventId", "string(<=64)", "Y", "scenario", "timeline.events[].eventId", "전달 이벤트 ID를 제한된 timeline에 기록 가능하나 DB UNIQUE는 없음", "불투명 문자열", "N/A", "Y", "간접", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "PLANNED", documentVersion, jira, "VAL-031 전달 중복과 최종 request 중복 분리 결정 필요"],
  ["MAP-VISION-RESULT-TYPE", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "type", "enum string", "Y", "scenario", "vision_status", "PERSON_DETECTED→SUCCEEDED, PERSON_NOT_FOUND→NO_PERSON, INFERENCE_FAILED→FAILED; 최종 승인 필요", "N/A", "N/A", "N", "간접", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "PLANNED", documentVersion, jira, "VAL-026 상태 매핑 결정에 포함"],
  ["MAP-VISION-PERSON-COUNT", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "personCount", "integer>=1", "조건부", "scenario", "person_count", "최종 업무 판정만 저장", "N/A", "N/A", "N", "간접", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "ACTIVE", documentVersion, jira, "PERSON_DETECTED에서 필수"],
  ["MAP-VISION-CONFIDENCE", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "detectionConfidence", "number[0,1]", "조건부", "scenario", "vision_confidence", "numeric(5,4)로 저장", "N/A", "N/A", "N", "민감 파생", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "ACTIVE", documentVersion, jira, "식별 신뢰도와 혼동하지 않음"],
  ["MAP-VISION-MODEL-NAME", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "model.name", "string", "조건부", "scenario", "vision_model_name", "원문 모델명", "N/A", "N/A", "N", "N", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "ACTIVE", documentVersion, jira, "PERSON_DETECTED model이 선택 필드라서 NULL 가능"],
  ["MAP-VISION-MODEL-VERSION", "Vision AI", "REST", "Vision 결과 Callback", "Vision callback", "IN", "model.version", "string", "조건부", "scenario", "vision_model_version", "원문 버전", "N/A", "N/A", "N", "N", "backend/src/main/resources/static/openapi/vision-callback.openapi.yaml", "ACTIVE", documentVersion, jira, "PERSON_DETECTED model이 선택 필드라서 NULL 가능"],
  ["MAP-VOICE-REQUEST-ID", "Voice AI", "REST", "대화·음성 생성", "POST /api/v1/conversations/generate", "BIDIRECTIONAL", "requestId", "string(<=64)", "Y", "conversation", "generation_request_id", "호출 전에 DB 저장; 재시도 시 동일 값", "불투명 문자열", "N/A", "Y", "간접", "backend/src/main/resources/static/openapi/voice-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "응답 requestId와 동일"],
  ["MAP-VOICE-SCENARIO-ID", "Voice AI", "REST", "대화·음성 생성", "POST /api/v1/conversations/generate", "BIDIRECTIONAL", "scenarioId", "uuid string", "Y", "conversation", "scenario_id", "scenario.id UUID 직렬화", "UUID", "N/A", "N", "간접", "backend/src/main/resources/static/openapi/voice-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "대화와 시나리오 senior 일치 검증"],
  ["MAP-VOICE-TEXT", "Voice AI", "REST", "대화·음성 생성", "POST /api/v1/conversations/generate", "IN", "text", "string(1..500)", "Y", "conversation", "messages.items[].text", "ROBOT 역할 메시지로 append", "N/A", "N/A", "N", "Y", "backend/src/main/resources/static/openapi/voice-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "원문 7일; 음성 바이너리는 DB·MQTT에 저장하지 않음"],
  ["MAP-VOICE-GENERATED-AT", "Voice AI", "REST", "대화·음성 생성", "POST /api/v1/conversations/generate", "IN", "generatedAt", "ISO-8601 date-time", "Y", "conversation", "generation_completed_at", "UTC timestamptz로 변환", "N/A", "ISO-8601→UTC", "N", "N", "backend/src/main/resources/static/openapi/voice-ai.openapi.yaml", "ACTIVE", documentVersion, jira, "AI 단기 30일"],
  ["MAP-SPEAK-COMMAND-ID", "Robot", "MQTT", "SPEAK 명령", "bomi/v1/robot/{robotId}/commands", "OUT", "commandId", "string(<=64)", "Y", "conversation", "messages.items[].speechCommandId", "대화 메시지에 저장 후 같은 ID로 발행·재발행", "불투명 문자열", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "별도 컬럼이 아닌 제한된 JSONB 키"],
  ["MAP-AMBIENT-EVENT-ID", "AIoT", "MQTT", "온습도 관측 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "eventId", "string(<=64)", "Y", "care_record", "external_event_id", "임계 사건을 만들 때 원문 보존; 재전송 중복 생성 금지", "불투명 문자열", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "PERIODIC 최신값만 갱신할 때는 care_record를 만들지 않음"],
  ["MAP-AMBIENT-TEMPERATURE", "AIoT", "MQTT", "온습도 관측 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "payload.temperatureC", "number", "Y", "robot", "ambient_temperature_c", "numeric(5,2), 단위 °C", "N/A", "N/A", "N", "민감 파생", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "최신 관측시각일 때만 갱신"],
  ["MAP-AMBIENT-HUMIDITY", "AIoT", "MQTT", "온습도 관측 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "payload.humidityPercent", "number[0,100]", "Y", "robot", "ambient_humidity_percent", "numeric(5,2), 단위 %RH", "N/A", "N/A", "N", "민감 파생", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "최신 관측시각일 때만 갱신"],
  ["MAP-AMBIENT-OCCURRED-AT", "AIoT", "MQTT", "온습도 관측 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "occurredAt", "ISO-8601 date-time", "Y", "robot", "ambient_observed_at", "UTC timestamptz로 변환; latest-wins 기준", "N/A", "ISO-8601→UTC", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "수신시각과 구분"],
  ["MAP-AMBIENT-SOURCE", "AIoT", "MQTT", "온습도 관측 이벤트", "bomi/v1/iot/{deviceId}/events", "IN", "sourceId", "string", "Y", "robot", "ambient_sensor_code", "토픽 deviceId와 일치 검증 후 원문 저장", "등록 장치 코드", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "device FK 없음"],
  ["MAP-REST-EVENT-ID", "Robot Vision", "MQTT", "휴식 상태 전이", "bomi/v1/robot/{robotId}/status", "IN", "eventId", "string(<=64)", "Y", "care_record", "external_event_id", "휴식 시작·종료 전이의 멱등 키 원문", "불투명 문자열", "N/A", "Y", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "프레임별 후보는 발행하지 않음"],
  ["MAP-REST-STATE", "Robot Vision", "MQTT", "휴식 상태 전이", "bomi/v1/robot/{robotId}/status", "IN", "payload.restState", "enum string", "Y", "care_record", "details.restState", "RESTING은 ACTIVE 관찰 생성, AWAKE는 해당 관찰 완료", "N/A", "N/A", "N", "Y", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "카메라 프레임·자세 좌표·track ID 금지"],
  ["MAP-REST-ROBOT-MODE", "Robot Vision", "MQTT", "휴식 상태 전이", "bomi/v1/robot/{robotId}/status", "IN", "payload.robotMode", "enum string", "Y", "robot", "current_mode", "RESTING→REST_GUARD, AWAKE→IDLE 또는 허용 모드", "N/A", "N/A", "N", "간접", "docs/mqtt/topic-convention.md", "ACTIVE", documentVersion, jira, "호출·안전·긴급 기능 allowlist 유지"],
];

const glossaryHeaders = ["용어 ID", "도메인", "한글 업무 용어", "영문 또는 물리 용어", "정의", "동의어", "사용을 피해야 하는 모호한 표현", "관련 테이블", "관련 컬럼", "관리 담당 영역", "상태", "최초 도입 버전", "최종 변경 Jira", "비고"];
const glossaryRows = [
  ["TERM-001", "사용자", "어르신", "SENIOR / app_user", "BOMI 돌봄·대화·시나리오의 직접 대상이며 자신의 기억과 연결 관계에 대한 통제권을 가진 사용자", "대상 사용자", "환자, 피보호자", "app_user", "user_type", "Backend·기획", "ACTIVE", documentVersion, jira, "의료 진단 시스템의 환자 개념이 아님"],
  ["TERM-002", "사용자", "보호자", "GUARDIAN / app_user", "활성 돌봄 관계와 관계별 권한을 통과한 범위에서 어르신 데이터를 조회·관리하는 로그인 사용자", "가족 관리자", "전역 관리자", "app_user, care_relationship", "guardian_id, permissions", "Backend·기획", "ACTIVE", documentVersion, jira, "역할만으로 접근 권한이 생기지 않음"],
  ["TERM-003", "권한", "돌봄 관계", "care_relationship", "특정 어르신과 특정 보호자를 연결하고 우선순위·권한·연결 상태를 함께 관리하는 업무 관계", "보호 관계", "가족 여부", "care_relationship", "senior_id, guardian_id", "Backend", "ACTIVE", documentVersion, jira, "N:M 관계"],
  ["TERM-004", "Robot", "로봇", "robot", "등록 시리얼과 현재 어르신 배정, 최신 운영 상태 및 waypoint 참조를 가진 물리 장치", "BOMI Robot", "사용자 ID", "robot", "id, serial_number, senior_id", "Robot·Backend", "ACTIVE", documentVersion, jira, "실시간 pose 원본은 아님"],
  ["TERM-005", "시나리오", "시나리오", "scenario", "하나의 외부 트리거에서 시작해 주행·Vision·대화·복귀의 굵은 상태와 최종 결과를 잇는 업무 원장", "업무 흐름", "메시지 한 건", "scenario", "id, external_event_id, status", "Backend", "ACTIVE", documentVersion, jira, "상세 체크포인트와 DB 상태는 매핑 필요"],
  ["TERM-006", "대화", "대화", "conversation", "최근 텍스트 메시지, 요약, 생성 메타데이터와 보존 기한을 함께 관리하는 한 세션", "대화 세션", "음성 원본", "conversation", "messages, summary", "Backend·Voice AI", "ACTIVE", documentVersion, jira, "원본 음성은 저장하지 않음"],
  ["TERM-007", "개인화", "기억", "memory", "대화 등에서 얻은 장기 개인화 정보로 검증·공개·생명주기와 임베딩을 독립적으로 관리하는 업무 객체", "개인화 기억", "대화 원문 복사", "memory", "content, verification_status, lifecycle_status", "Backend·AI", "ACTIVE", documentVersion, jira, "구조화 건강 사실과 구분"],
  ["TERM-008", "돌봄", "돌봄 기록", "care_record", "건강·복약·일정·관찰·인지 참고·알림을 record_type으로 구분해 계획과 결과를 별도 행으로 남기는 기록", "care record", "계획 덮어쓰기", "care_record", "record_type, parent_record_id", "Backend·기획", "ACTIVE", documentVersion, jira, "넓은 MVP 테이블"],
  ["TERM-009", "감사", "감사 로그", "audit_log", "민감값 본문을 복제하지 않고 누가 어떤 대상의 어떤 필드를 어떤 행위로 변경했는지 남기는 append-only 흔적", "audit trail", "운영 로그 전체", "audit_log", "changed_fields, action_type", "Backend·보안", "ACTIVE", documentVersion, jira, "변경 전후 값 저장 금지"],
  ["TERM-010", "시나리오", "귀가 환영", "HOMECOMING", "INBOUND 존재 감지에서 시작해 현관 이동, 상호작용 판정, 맞춤 대화와 안전한 기본 위치 복귀로 끝나는 MVP 흐름", "homecoming welcome", "문 열림 이벤트", "scenario, conversation", "scenario_type", "전체", "ACTIVE", documentVersion, jira, "DOOR_OPENED만으로 시작하지 않음"],
  ["TERM-011", "돌봄", "복약 계획", "MEDICATION_SCHEDULE", "언제 어떤 복약 알림·실행을 생성할지 정의하는 계획 행으로 실행 결과에 의해 덮어쓰지 않는 원본", "복약 일정", "복용 완료 행", "care_record", "record_type, recurrence", "Backend·기획", "ACTIVE", documentVersion, jira, "실행은 자식 행"],
  ["TERM-012", "업무", "실행 결과", "execution result", "명령·AI 작업·복약·알림이 실제로 수행된 결과를 계획과 구분해 남긴 최종 업무 사실", "result", "현재 상태만", "scenario, care_record", "status, parent_record_id", "Backend", "ACTIVE", documentVersion, jira, "재시도 식별자와 함께 관리"],
  ["TERM-013", "안전", "낙상 대응", "FALL_RESPONSE", "낙상 의심을 검증하고 긴급 단계에서 보호자별 알림 결과를 남긴 뒤 해결 또는 오탐으로 종료하는 안전 흐름", "fall response", "의료 진단", "scenario, care_record", "scenario_type, recipient_guardian_id", "Backend·Robot", "ACTIVE", documentVersion, jira, "안전 기록 보존기간 TBD"],
  ["TERM-014", "정합성", "멱등성", "idempotency", "같은 논리 이벤트·요청·명령을 재전송해도 새 업무 객체나 부수효과가 중복 생성되지 않는 성질", "중복 방지", "단순 로그 중복 제거", "scenario, care_record", "external_event_id, request_id, command_id", "전체", "ACTIVE", documentVersion, jira, "전달 중복과 최종 작업 중복을 별도 식별"],
  ["TERM-015", "데이터 관리", "보존", "retention", "업무·법적 필요 동안 데이터 또는 최소 tombstone을 유지하는 기간과 형태의 정책", "retention policy", "영구 저장", "전체", "각 보존 컬럼", "Backend·보안·법무", "ACTIVE", documentVersion, jira, "미확정 기간은 TBD"],
  ["TERM-016", "데이터 관리", "삭제", "deletion / anonymization", "사용자 요청·만료·정책에 따라 본문·식별자·파생정보를 물리 제거하거나 비식별화하는 통제된 절차", "purge", "행만 숨기기", "전체", "purged_at, lifecycle_status", "Backend·보안", "ACTIVE", documentVersion, jira, "연쇄 삭제 전 보존 판정"],
  ["TERM-017", "데이터 관리", "tombstone", "tombstone", "본문과 민감 파생정보는 제거하되 과거 객체의 존재·삭제 사실·계보를 설명하기 위해 남기는 최소 행", "삭제 표식", "백업 복사본", "memory", "lifecycle_status, purged_at", "Backend·보안", "ACTIVE", documentVersion, jira, "DELETED 상태"],
  ["TERM-018", "온보딩", "초기 설문", "onboarding flow", "세션·문항별 처리 원장에서 진행·검증·멱등 반영을 추적하고 확인된 원자 사실만 최종 도메인에 분해하는 입력 흐름", "온보딩 대화", "프로필 원본", "onboarding_session, onboarding_answer, app_user, memory, care_record", "status, question_code, materialization_key", "Backend·기획·AI·Robot", "ACTIVE", documentVersion, jira, "질문 문구는 제품 정책이며 프로필은 최종 테이블을 조회"],
  ["TERM-019", "휴식", "휴식 보호 모드", "REST_GUARD", "일정 시간 이상 누움이 확정된 동안 일반 능동 기능을 억제하고 호출·안전·긴급 기능만 유지하는 로봇 모드", "휴식 상태", "완전 전원 정지, 수면 진단", "robot, care_record", "current_mode, REST_OBSERVATION", "Robot·Vision·Backend", "ACTIVE", documentVersion, jira, "프레임·자세 좌표를 중앙 저장하지 않음"],
  ["TERM-020", "환경", "환경 관찰", "ENVIRONMENT_OBSERVATION", "최신 온습도와 임계 초과 또는 사용자 확인이 결합된 의미 있는 환경 사건", "온습도 관찰", "초당 센서 로그", "robot, care_record", "ambient_temperature_c, ambient_humidity_percent", "IoT·Robot·Backend", "ACTIVE", documentVersion, jira, "원시 시계열은 별도 요구 전까지 저장하지 않음"],
  ["TERM-021", "온보딩", "온보딩 세션", "onboarding_session", "한 어르신이 현재 배정 로봇으로 진행하는 질문·동의 정책 버전이 고정된 한 번의 초기 설문 실행", "설문 시도", "NOT_STARTED 행", "onboarding_session", "senior_id, robot_id, status, version", "Backend·Robot", "ACTIVE", documentVersion, jira, "IN_PROGRESS는 어르신당 하나"],
  ["TERM-022", "온보딩", "답변 반영", "materialization", "확인된 한 답변을 app_user, memory, care_record에 한 번만 원자 반영하고 대상 참조를 남기는 처리", "최종 사실 반영", "프로필의 extraction 직접 조회", "onboarding_answer", "materialization_key, materialized_at, target_refs", "Backend", "ACTIVE", documentVersion, jira, "대상 값은 target_refs에 복제하지 않음"],
];

const guideRows = [
  ["6.1 목적과 범위", 1, "문서 역할", "이 컬럼정의서는 Backend·AI·Robot 팀이 업무 의미와 PostgreSQL 물리 설계를 함께 검토하는 사람이 읽는 기준 문서다. Excel에서 DDL이나 Flyway SQL을 생성하지 않는다."],
  ["6.1 목적과 범위", 2, "역할 구분", "ERD는 승인된 설계 근거, Excel은 유지보수·협업 원본, CSV는 Git diff용 자동 산출물, Flyway는 실제 DB 적용 기준, 실제 DB는 적용 결과다."],
  ["6.1 목적과 범위", 3, "Flyway 도입 전", "승인된 Excel 컬럼정의서가 사람이 읽는 DB 설계 기준이다."],
  ["6.1 목적과 범위", 4, "Flyway 도입 후", "Flyway는 실제 물리 스키마 적용 기준이고 Excel은 사람이 읽는 설계·협업 기준이다. DB 변경 MR에서는 가능한 한 Flyway, 컬럼정의서, 관련 API 계약을 함께 수정한다."],
  ["6.2 역할과 책임", 1, "문서 관리자", "전체 정합성, 문서 버전, 변경이력과 기준 파일을 관리하는 기본 담당자. 현재 담당자는 TBD다."],
  ["6.2 역할과 책임", 2, "변경 담당자", "해당 변경 건에서 실제 Excel 파일을 수정하는 한 명. 팀 회의 후 누구나 지정될 수 있다."],
  ["6.2 역할과 책임", 3, "도메인 검토자", "Backend, AI, Robot 등 영향 영역의 계약·구현·데이터 정책을 검토한다."],
  ["6.2 역할과 책임", 4, "승인자", "팀 회의 결정과 최종 반영 여부를 확인한다. 확정 전에는 TBD로 둔다."],
  ["6.3 변경 절차", 1, "1~5", "변경 필요 발견 → Jira 등록 → 팀 회의 및 설계 결정 → 영향 범위 확인 → 변경 담당자 한 명 지정"],
  ["6.3 변경 절차", 2, "6~9", "별도 Git 브랜치에서 Excel 수정 → 관련 시트 수정 → 문서 버전·변경이력 갱신 → 12_검증결과 확인 및 필요 시 검증 스크립트 실행"],
  ["6.3 변경 절차", 3, "10~14", "CSV 스냅샷 생성 → GitLab MR 생성 → 영향 도메인 리뷰 → 문서 관리자 확인 → 병합 및 버전 확정"],
  ["6.4 동시 수정 방지", 1, "단일 편집자", "동일 Excel에 두 개 이상의 수정 MR을 동시에 진행하지 않고 하나의 변경 건에서는 한 사람만 실제 파일을 수정한다."],
  ["6.4 동시 수정 방지", 2, "최신 기준", "다른 변경이 먼저 병합되면 최신 파일을 다시 받은 뒤 수정한다. 서로 다른 Excel 복사본을 나중에 수동 병합하지 않는다."],
  ["6.4 동시 수정 방지", 3, "충돌 처리", "충돌 시 문서 관리자가 기준 파일을 정하고 병합 전 현재 브랜치가 최신 기준 브랜치를 반영했는지 확인한다."],
  ["6.5 버전 규칙", 1, "Major", "컬럼 삭제·이름 변경·호환되지 않는 타입 변경·PK 의미 변경 등 하위 호환 불가 변경"],
  ["6.5 버전 규칙", 2, "Minor", "테이블·컬럼·인덱스·코드값 등 하위 호환 가능한 추가"],
  ["6.5 버전 규칙", 3, "Patch", "설명·예시·오탈자처럼 물리 스키마 의미가 바뀌지 않는 수정. 승인 전 0.x.y, 최초 공식 승인 시 1.0.0."],
  ["6.6 입력 규칙", 1, "표준값", "여부 Y/N, 해당 없음 N/A, 미확정 TBD, 객체 PLANNED/ACTIVE/DEPRECATED/REMOVED, 문서 DRAFT/REVIEW/APPROVED/SUPERSEDED"],
  ["6.6 입력 규칙", 2, "변경·호환성", "변경 ADD/MODIFY/RENAME/DEPRECATE/DROP, 호환성 COMPATIBLE/CONDITIONAL/BREAKING. 빈 셀은 누락을 뜻하므로 해당 없음은 N/A를 쓴다."],
  ["6.8 컬럼 폐기", 1, "DEPRECATED", "기존 행을 즉시 삭제하지 말고 DEPRECATED로 바꾼 뒤 폐기 예정 버전과 Jira를 기록하고 FK·인덱스·코드·JSONB·연계 영향을 확인한다."],
  ["6.8 컬럼 폐기", 2, "REMOVED", "실제 삭제 승인 뒤 REMOVED로 바꾸고 Git과 변경이력에서 과거를 추적한다."],
  ["6.9 MR 리뷰", 1, "체크리스트", "아래 tblReviewChecklist를 모두 확인하고 근거를 MR에 남긴다."],
  ["6.10 복구", 1, "Git 복구", "이전 Excel은 Git 이력에서 복원한다. 최종·백업 파일을 만들지 않고 잘못된 변경은 새 수정 커밋으로 복구하며 변경이력에 사유와 대상 버전을 기록한다."],
  ["CSV 스냅샷", 1, "재생성 명령", "저장소 루트 PowerShell에서: powershell -ExecutionPolicy Bypass -File docs/database/column-definition/scripts/export-column-definition-csv.ps1"],
  ["CSV 스냅샷", 2, "일치 검증 명령", "저장소 루트 PowerShell에서: powershell -ExecutionPolicy Bypass -File docs/database/column-definition/scripts/export-column-definition-csv.ps1 -Check"],
  ["최초 생성", 1, "초기 전용", "generate-column-definition.mjs는 최초 생성용이며 기존 Excel이 있으면 실패한다. 사람이 관리하기 시작한 뒤에는 실행해 Excel을 재생성하지 않는다."],
  ["유지보수 업데이트", 1, "0.3.0 전용", "update-column-definition-v0.3.0.mjs는 기존 Excel을 불러와 온보딩 세션·답변 원장과 연계 계약을 반영한 일회성 migration 스크립트다. 적용 후 CSV와 검증 결과를 다시 생성한다."],
  ["내부 이동", 1, "참조 링크", "각 시트 A3와 04_컬럼정의의 관련 객체 이동 셀은 대상 셀을 직접 참조한다. 셀을 선택하고 Excel의 Ctrl+[ 단축키로 참조 원본으로 이동한다."],
  ["수식·목록", 1, "보호와 유지보수", "수식·입력 목록은 매크로 없이 사용한다. 99_입력목록은 비밀번호로 잠그지 않았으며 관리자가 팀 합의 후 수정할 수 있다."],
];

const impactRows = [
  ["테이블 추가", "03, 04, 05, 06, 11, 12, 01", "07~10은 해당 시 추가", "Minor 이상"],
  ["컬럼 추가", "04, 11, 12, 01", "05~10 영향 시 함께", "Minor"],
  ["컬럼 타입 변경", "04, 05, 06, 11, 12, 01", "API·MQTT 계약 및 Flyway", "Major 또는 Conditional"],
  ["NULL 정책 변경", "04, 05, 11, 12, 01", "기존 데이터 backfill", "Major/Minor 판단"],
  ["컬럼명 변경", "04, 05~10, 11, 12, 01", "Flyway·API·코드 동시 검토", "Major"],
  ["FK 추가·변경", "04, 05, 06, 11, 12, 01", "삭제 동작과 서비스 교차행 규칙", "Minor/Major"],
  ["UNIQUE 또는 CHECK 추가", "04, 05, 06, 11, 12", "기존 위반 데이터 검사", "Conditional"],
  ["인덱스 추가", "06, 11, 12, 01", "조회 근거·쓰기 비용", "Minor"],
  ["JSONB 키 추가", "07, 04, 11, 12", "DTO schemaVersion·하위 호환성", "Minor/Conditional"],
  ["벡터 모델 또는 차원 변경", "08, 04, 06, 11, 12", "재임베딩·Flyway·검색 평가", "Major/Conditional"],
  ["상태 코드 추가", "09, 04, 05, 11, 12", "API/MQTT 상태 매핑", "Minor/Conditional"],
  ["API·MQTT·ROS 2 매핑 변경", "10, 관련 04/07/09, 11, 12", "계약 문서와 Mock E2E", "Conditional"],
  ["컬럼 폐기 또는 삭제", "04, 05~10, 11, 12, 01", "DEPRECATED 선행·데이터 migration", "Major"],
];

const checklistItems = ["Jira 번호가 기록되었는가?", "팀 회의 결정과 일치하는가?", "문서 버전이 갱신되었는가?", "변경이력 행이 추가되었는가?", "논리명과 물리명이 명확한가?", "데이터 타입과 NULL 정책이 작성되었는가?", "FK 및 삭제 동작을 확인했는가?", "민감정보와 보존 정책을 확인했는가?", "JSONB, 코드값, 인덱스 영향을 확인했는가?", "AI, Robot, MQTT, OpenAPI 연계 영향을 확인했는가?", "하위 호환성을 판단했는가?", "검증 결과에 오류가 없는가?", "CSV 스냅샷을 다시 생성했는가?", "한 명만 Excel을 편집했는가?"];
const checklistRows = checklistItems.map((item, i) => [i + 1, "☐", item, "MR에서 근거 확인"]);

const documentInfoRows = [
  ["문서명", "BOMI 컬럼정의서"], ["문서 목적", "BOMI 중앙 PostgreSQL 설계·협업·리뷰를 위한 사람이 읽는 기준 문서"], ["적용 프로젝트", "BOMI"],
  ["적용 범위", "PostgreSQL 17 / pgvector 기반 10개 MVP 테이블"], ["문서 버전", documentVersion], ["문서 상태", "DRAFT"],
  ["문서 관리자", "TBD"], ["현재 변경 담당자", "TBD"], ["검토자", "TBD"], ["승인자", "TBD"], ["기준 Jira", jira],
  ["기준 Git 브랜치", branch], ["기준 Git 커밋", sourceCommit], ["최초 작성일", today], ["최종 수정일", today], ["승인일", "TBD"],
  ["PostgreSQL 버전", "17"], ["pgvector 사용 여부 및 버전", "Y / 0.8.5 (운영 이미지 기준)"], ["기준 시간대", "UTC"],
  ["파일 경로", "docs/database/column-definition/BOMI_컬럼정의서.xlsx"], ["CSV 스냅샷 경로", "docs/database/column-definition/snapshots/"],
  ["원본 ERD 경로", "docs/database/mvp-erd.md"], ["비고", "Flyway·업무 Entity 미도입 상태. Excel은 DDL을 생성하지 않음"],
];

const sheetCatalogRows = [
  ["00_유지보수가이드", "역할, 변경 절차, 동시 수정, 버전, 영향 범위, 리뷰·복구·명령"], ["01_문서정보", "버전·관리·기준 커밋과 시트 카탈로그"],
  ["02_용어집", "업무 용어와 모호한 표현 통제"], ["03_테이블정의", "테이블별 업무 단위·책임·보존·삭제"], ["04_컬럼정의", "컬럼별 업무·물리·데이터·변경 관리"],
  ["05_관계_제약조건", "PK/FK/UNIQUE/CHECK/교차행·상태·멱등 규칙"], ["06_인덱스정의", "명시된 PostgreSQL 인덱스와 조회 근거"],
  ["07_JSONB정의", "8개 JSONB 구조를 경로 단위로 관리"], ["08_벡터정의", "pgvector 모델·차원·검색·삭제 정책"], ["09_코드정의", "코드값과 상태 전이"],
  ["10_연계매핑", "근거가 명확한 REST/MQTT/내부 필드 매핑"], ["11_변경이력", "버전·Jira·담당·호환성·Flyway 영향"], ["12_검증결과", "구조·값·원본 정합성·TBD·충돌"],
  ["99_입력목록", "Excel 데이터 유효성 검사 표준 목록"],
];

const validationHeaders = ["검증 ID", "분류", "검증 항목", "상태", "오류/경고 건수", "대상 시트", "대상 객체 ID", "검증 근거·조치", "검사 기준 버전", "검사 일시"];
const validationRows = [
  ["VAL-001", "구조", "기준 테이블 10개 존재", "PASS", 0, "03_테이블정의", "전체", "10개 모두 존재", documentVersion, `${today} 00:00Z`],
  ["VAL-002", "구조", "중복 테이블 ID 없음", "PASS", 0, "03_테이블정의", "전체", "10개 ID 고유", documentVersion, `${today} 00:00Z`],
  ["VAL-003", "구조", "중복 컬럼 ID 없음", "PASS", 0, "04_컬럼정의", "전체", `${sourceColumnCount}개 ID 고유`, documentVersion, `${today} 00:00Z`],
  ["VAL-004", "구조", "테이블별 컬럼 순번 중복 없음", "PASS", 0, "04_컬럼정의", "전체", "1부터 원본 순서대로 부여", documentVersion, `${today} 00:00Z`],
  ["VAL-005", "구조", "필수 항목 누락 없음", "PASS", 0, "04_컬럼정의", "전체", "필수 15개 필드 N/A/TBD 포함 검사", documentVersion, `${today} 00:00Z`],
  ["VAL-006", "구조", "물리명 snake_case", "PASS", 0, "03,04", "전체", "^[a-z][a-z0-9_]*$ 검사", documentVersion, `${today} 00:00Z`],
  ["VAL-007", "구조", "FK 참조 테이블·컬럼 존재 및 타입 일치", "PASS", 0, "05_관계_제약조건", "FK_*", "모든 물리 FK는 id(uuid) 참조", documentVersion, `${today} 00:00Z`],
  ["VAL-008", "구조", "제약·인덱스·코드·JSONB·벡터 ID 참조", "PASS", 0, "04~09", "전체", "안정 ID 집합 대조", documentVersion, `${today} 00:00Z`],
  ["VAL-009", "구조", "연계 매핑 대상 참조", "PASS", 0, "10_연계매핑", "전체", "대상 테이블·컬럼 또는 승인 JSON 경로 존재", documentVersion, `${today} 00:00Z`],
  ["VAL-010", "값", "Y/N 및 허용 객체 상태", "PASS", 0, "전체", "전체", "입력 목록 기준", documentVersion, `${today} 00:00Z`],
  ["VAL-011", "값", "ACTIVE인데 타입·설명이 TBD인 항목", "PASS", 0, "04_컬럼정의", "전체", "벡터는 PLANNED로 분리", documentVersion, `${today} 00:00Z`],
  ["VAL-012", "값", "DEPRECATED/REMOVED 이력 규칙", "PASS", 0, "04,11", "전체", "현재 해당 객체 없음", documentVersion, `${today} 00:00Z`],
  ["VAL-013", "값", "UUID와 외부 불투명 문자열 정책", "PASS", 0, "04,10", "ID 정책", "내부 UUID, 외부 varchar(64) 원문 보존", documentVersion, `${today} 00:00Z`],
  ["VAL-014", "값", "시간 타입과 UTC 원칙", "PASS", 0, "04,10", "*_at", "사건 시각 timestamptz, 반복 규칙은 IANA timeZone", documentVersion, `${today} 00:00Z`],
  ["VAL-015", "값", "민감정보 보존·삭제 정책", "PASS", 0, "03,04,07,08", "전체", "모든 민감 컬럼에 보존·삭제 설명 존재", documentVersion, `${today} 00:00Z`],
  ["VAL-016", "원본", "원본 ERD 10개 테이블 및 데이터 사전 전수 반영", "PASS", 0, "03,04", "전체", `실제 데이터 사전 ${sourceColumnCount}행 전수 반영`, documentVersion, `${today} 00:00Z`],
  ["VAL-017", "원본", "기존 173개 요구 후보와 신규 확장 요구 추적", "PASS", 0, "12_검증결과", "REQ-CANDIDATES", `173은 초기 후보 요구 수이고 신규 온보딩·휴식·온습도 요구를 별도 반영. 실제 데이터 사전은 ${sourceColumnCount}행이며 숫자 맞춤용 컬럼을 만들지 않음`, documentVersion, `${today} 00:00Z`],
  ["VAL-018", "원본", "JSONB 8개 구조 반영", "PASS", 0, "07_JSONB정의", "JSON_*", "8개 구조를 경로 단위로 정의", documentVersion, `${today} 00:00Z`],
  ["VAL-019", "원본", "FK 삭제 정책·핵심 인덱스·상태 흐름", "PASS", 0, "05,06,09", "전체", "mvp-erd.md E/G/H/K 기준", documentVersion, `${today} 00:00Z`],
  ["VAL-020", "원본", "pgvector 미확정 값을 임의 확정하지 않음", "PASS", 0, "08_벡터정의", "VEC_MEMORY_EMBEDDING", "차원·모델·거리·정규화·인덱스 TBD", documentVersion, `${today} 00:00Z`],
  ["VAL-033", "원본", "온보딩 세션·답변·동의·대화 출처 요구 반영", "PASS", 0, "03,04,05,06,07,09,10", "ONBOARDING-CONSENT", "두 처리 원장, 세션/projection 원자 갱신, revision, 수신·반영 멱등성, 단기 파기와 최종 테이블 조회 원칙 반영", documentVersion, `${today} 00:00Z`],
  ["VAL-034", "원본", "휴식 보호 저장 경계와 기능 allowlist", "PASS", 0, "04,05,07,09,10", "REST-GUARD", "프레임별 자세 금지, REST_OBSERVATION과 REST_GUARD, 호출·안전·긴급 기능 유지", documentVersion, `${today} 00:00Z`],
  ["VAL-035", "원본", "온습도 최신값·임계 사건 분리", "PASS", 0, "04,05,07,09,10", "AMBIENT-OBSERVATION", "robot 최신 스냅샷, ENVIRONMENT_OBSERVATION 임계 사건, 원시 시계열 금지", documentVersion, `${today} 00:00Z`],
  ["VAL-021", "충돌", "Vision identifiedPerson.personId와 승인 ERD 식별 금지 원칙", "WARNING", 1, "10_연계매핑", "TBD-VISION-IDENTITY", "OpenAPI는 선택 식별 결과를 허용하지만 승인 ERD에는 저장 필드가 없고 중앙 생체·신원 승격을 금지. 매핑하지 않고 AI Vision/Backend/보안 결정 필요", documentVersion, `${today} 00:00Z`],
  ["VAL-022", "TBD", "임베딩 모델·버전·차원·거리 함수", "WARNING", 1, "08_벡터정의", "VEC_MEMORY_EMBEDDING", "AI/Backend가 migration 전 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-023", "TBD", "외부 ID 생산 형식 UUIDv7 또는 ULID", "WARNING", 1, "10_연계매핑", "ID-POLICY", "전체 연계 팀 합의; 물리 varchar(64)는 유지", documentVersion, `${today} 00:00Z`],
  ["VAL-024", "TBD", "일반·요약·안전·감사 최종 법적 보존기간", "WARNING", 1, "03,04", "RETENTION-POLICY", "Backend·보안·법무 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-025", "TBD", "비밀번호 해시와 계정 복구 정책", "WARNING", 1, "04_컬럼정의", "app_user.password_hash", "Backend·보안 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-026", "TBD", "API/MQTT↔DB 상태 및 timeout 최종 매핑", "WARNING", 1, "09,10", "STATE-MAPPING", "Backend·Robot·AI 합의", documentVersion, `${today} 00:00Z`],
  ["VAL-027", "TBD", "PRIMARY 미응답 후 SECONDARY 알림 시간·채널", "WARNING", 1, "09_코드정의", "ALERT-ESCALATION", "Backend·기획 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-028", "TBD", "개인정보 삭제 시 확인 기억·안전 기록 처리 동의", "WARNING", 1, "03,04", "DELETION-CONSENT", "기획·보안·법무 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-029", "구현", "Flyway·업무 Entity 실제 구현 상태", "WARNING", 1, "01_문서정보", "IMPLEMENTATION", "현재 pgvector 확장 초기화만 있고 업무 Flyway/JPA Entity는 없음. 구현 후 Excel과 migration을 함께 갱신", documentVersion, `${today} 00:00Z`],
  ["VAL-030", "충돌", "OpenAPI scenarioType HOMECOMING_WELCOME와 DB HOMECOMING", "WARNING", 1, "09,10", "MAP-VISION-SCENARIO-TYPE", "Vision·Voice OpenAPI는 HOMECOMING_WELCOME, 승인 ERD scenario_type은 HOMECOMING. 변환 규칙 또는 코드 통일을 Backend·AI가 승인해야 함", documentVersion, `${today} 00:00Z`],
  ["VAL-031", "충돌", "Vision Callback eventId 전달 중복 저장 위치", "WARNING", 1, "05,07,10", "MAP-VISION-CALLBACK-EVENT-ID", "Callback 계약은 eventId 전달 중복과 requestId 최종 작업 중복을 분리하지만 승인 ERD에는 eventId 전용 UNIQUE 컬럼이 없음. timeline 기록/별도 dedupe 저장소/스키마 변경 중 결정 필요", documentVersion, `${today} 00:00Z`],
  ["VAL-032", "충돌", "Voice AI 응답의 모델명·버전 근거", "WARNING", 1, "04,10", "conversation.model_name, conversation.model_version", "승인 ERD는 모델명·버전을 보존하지만 voice-ai.openapi.yaml 응답에는 모델 메타데이터가 없음. Backend 구성값 또는 계약 필드 추가를 Backend·Voice AI가 결정", documentVersion, `${today} 00:00Z`],
  ["VAL-036", "TBD", "온보딩 질문·동의·보존·반영 정책 세부값", "WARNING", 1, "01,04,07,09,10", "ONBOARDING-POLICY", "기획·Backend·AI·Robot이 최초 questionSetVersion/consentPolicyVersion, 질문 코드, 세션 만료, 단기 보존기간과 materializationKey 생성 규칙을 승인", documentVersion, `${today} 00:00Z`],
  ["VAL-037", "TBD", "휴식 판정 임계시간·해제 조건·비긴급 기능 정책", "WARNING", 1, "04,07,09,10", "REST-POLICY", "Vision·Robot·Backend·기획이 누움 지속시간, 기상 판정, 오탐 보정, 복약 알림 처리와 접근 전 안전 조건을 승인", documentVersion, `${today} 00:00Z`],
  ["VAL-038", "TBD", "온습도 임계값·샘플링·중복 질문 억제·센서 보정", "WARNING", 1, "04,07,09,10", "AMBIENT-POLICY", "IoT·Robot·Backend·기획이 단위, 임계값, 히스테리시스, 전송 주기와 고장 판정을 승인", documentVersion, `${today} 00:00Z`],
];

const changeHeaders = ["문서 버전", "변경일", "Jira 번호", "회의 일자", "변경 유형", "대상 유형", "대상 ID", "변경 전", "변경 후", "변경 사유", "영향 영역", "관련 API·MQTT·ROS 2", "호환성", "데이터 마이그레이션 필요 여부", "Flyway 필요 여부", "변경 담당자", "검토자", "승인자", "승인 상태", "Git 커밋", "비고"];
const changeRows = [
  ["0.1.0", "2026-07-22", jira, "TBD", "ADD", "DOCUMENT", "BOMI_컬럼정의서", "N/A", "승인 ERD 기반 최초 자동 생성; 176개 실제 컬럼", "팀 공통 데이터 사전과 Git diff 체계 구축", "Backend, AI, Robot, DB", "OpenAPI, MQTT, ROS 2/Nav2 문서", "COMPATIBLE", "N", "N", "TBD", "TBD", "TBD", "DRAFT", "c2e44f8 (source baseline)", "초기 버전"],
  ["0.2.0", "2026-07-23", jira, "TBD", "UPDATE", "SCHEMA", "ONBOARDING_REST_AMBIENT", "0.1.0", "기존 8개 테이블을 유지하면서 192개 실제 컬럼으로 확장", "초기 설문·동의, 휴식 보호 모드, 온습도 최신값과 의미 있는 사건을 추적", "Backend, AI, Vision, Robot, IoT, DB", "MQTT topic-convention, 운영 정책", "CONDITIONAL", "Y", "Y", "TBD", "TBD", "TBD", "DRAFT", sourceCommit, "별도 설문 원장 없이 최종 사실 분해 저장"],
  [documentVersion, today, jira, "TBD", "ADD", "SCHEMA", "ONBOARDING_SESSION_ANSWER", "0.2.0", `온보딩 원장 2개를 추가한 10개 테이블·${sourceColumnCount}개 실제 컬럼`, "문항별 재개·revision·검증·QoS 1 재전송·최종 사실 반영·단기 파기 추적 필요", "Backend, AI, Voice, Robot, MQTT, DB", "MQTT ONBOARDING_ANSWER_CAPTURED, 프로필 조회 원칙", "COMPATIBLE", "Y", "Y", "TBD", "TBD", "TBD", "DRAFT", sourceCommit, "기존 Excel을 artifact-tool로 마이그레이션하고 CSV 재생성"],
];

const inputLists = {
  "여부": ["Y", "N"], "해당없음_미확정": ["N/A", "TBD"], "문서상태": ["DRAFT", "REVIEW", "APPROVED", "SUPERSEDED"],
  "객체상태": ["PLANNED", "ACTIVE", "DEPRECATED", "REMOVED"], "변경유형": ["ADD", "MODIFY", "RENAME", "DEPRECATE", "DROP"],
  "호환성": ["COMPATIBLE", "CONDITIONAL", "BREAKING"], "제약유형": ["PK", "FK", "UNIQUE", "CHECK", "EXCLUDE", "STATE_TRANSITION", "SERVICE_RULE"],
  "인덱스유형": ["BTREE", "GIN", "HNSW", "IVFFLAT"], "인터페이스유형": ["REST", "MQTT", "ROS2", "INTERNAL"],
  "매핑방향": ["IN", "OUT", "BIDIRECTIONAL"], "민감정보분류": ["N", "간접", "Y"],
  "구현계층": ["PostgreSQL", "Spring 서비스", "애플리케이션 검증"], "승인상태": ["DRAFT", "REVIEW", "APPROVED", "REJECTED"],
  "검증결과": ["PASS", "WARNING", "ERROR"],
};

const workbook = Workbook.create();
const colors = { navy: "#16324F", teal: "#0F766E", pale: "#E8F1F5", gold: "#FFF4CC", red: "#FEE2E2", green: "#DCFCE7", amber: "#FEF3C7", gray: "#F3F4F6", white: "#FFFFFF", ink: "#172033" };

function colLetter(index) {
  let n = index + 1;
  let result = "";
  while (n > 0) { n -= 1; result = String.fromCharCode(65 + (n % 26)) + result; n = Math.floor(n / 26); }
  return result;
}

function writeTitle(sheet, title, description, lastCol) {
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${lastCol}1`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A1:${lastCol}1`).format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 16 }, verticalAlignment: "center" };
  sheet.getRange("1:1").format.rowHeight = 30;
  sheet.mergeCells(`A2:${lastCol}2`);
  sheet.getRange("A2").values = [[description]];
  sheet.getRange(`A2:${lastCol}2`).format = { fill: colors.pale, font: { color: colors.ink, italic: true }, wrapText: true, verticalAlignment: "center" };
  sheet.getRange("2:2").format.rowHeight = 28;
  if (sheet.name !== "00_유지보수가이드") {
    sheet.getRange("A3").formulas = [[`='00_유지보수가이드'!A1`]];
    sheet.getRange("A3").format = { font: { color: "#2563EB", bold: true } };
    if (lastCol !== "A") {
      sheet.mergeCells(`B3:${lastCol}3`);
      sheet.getRange("B3").values = [["참조 셀 선택 후 Ctrl+[ : 00_유지보수가이드로 이동"]];
      sheet.getRange(`B3:${lastCol}3`).format = { font: { color: "#2563EB", italic: true } };
    }
  }
}

function addTable(sheet, startRow, startCol, headers, rows, name, options = {}) {
  const endRow = startRow + rows.length;
  const endCol = startCol + headers.length - 1;
  const range = sheet.getRange(`${colLetter(startCol)}${startRow}:${colLetter(endCol)}${endRow}`);
  range.values = [headers, ...rows];
  const table = sheet.tables.add(range, true, name);
  table.style = options.style || "TableStyleMedium2";
  table.showFilterButton = true;
  table.showBandedRows = true;
  sheet.getRange(`${colLetter(startCol)}${startRow}:${colLetter(endCol)}${startRow}`).format = {
    fill: colors.teal, font: { bold: true, color: colors.white }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "center",
  };
  if (rows.length) {
    sheet.getRange(`${colLetter(startCol)}${startRow + 1}:${colLetter(endCol)}${endRow}`).format = { wrapText: true, verticalAlignment: "top", font: { color: colors.ink, size: 9 } };
  }
  return { table, startRow, endRow, startCol, endCol };
}

function setWidths(sheet, headers, startCol = 0) {
  const narrow = new Set(["순서", "표시 순서", "컬럼 순번", "PK 순번", "스케일", "정밀도", "길이", "오류/경고 건수"]);
  const medium = /ID|물리명|논리명|타입|상태|여부|버전|날짜|시각|컬럼명|테이블명|방향|도메인|Jira|Git|경로/;
  headers.forEach((header, i) => {
    const width = narrow.has(header) ? 10 : medium.test(header) ? 18 : /설명|목적|의미|정책|근거|규칙|비고|변환/.test(header) ? 34 : 22;
    sheet.getRange(`${colLetter(startCol + i)}:${colLetter(startCol + i)}`).format.columnWidth = Math.min(width, 38);
  });
}

function applyValidation(sheet, headerRow, headers, rowsCount, mapping) {
  for (const [header, listColumn] of Object.entries(mapping)) {
    const index = headers.indexOf(header);
    if (index < 0) continue;
    const inputHeaders = Object.keys(inputLists);
    const listIndex = inputHeaders.indexOf(listColumn);
    const listLength = inputLists[listColumn].length;
    const listCol = colLetter(listIndex);
    sheet.getRange(`${colLetter(index)}${headerRow + 1}:${colLetter(index)}${headerRow + rowsCount}`).dataValidation = {
      rule: { type: "list", formula1: `'99_입력목록'!$${listCol}$6:$${listCol}$${5 + listLength}` },
    };
  }
}

function addStandardSheet(name, title, description, headers, rows, tableName, validations = {}) {
  const sheet = workbook.worksheets.add(name);
  writeTitle(sheet, title, description, colLetter(headers.length - 1));
  sheet.mergeCells(`A4:${colLetter(headers.length - 1)}4`);
  sheet.getRange("A4").values = [["입력 규칙: 빈 셀은 누락을 뜻합니다. 해당 없음은 N/A, 미확정은 TBD를 사용합니다."]];
  sheet.getRange(`A4:${colLetter(headers.length - 1)}4`).format = { fill: colors.gold, font: { bold: true, color: colors.ink }, wrapText: true };
  const table = addTable(sheet, 5, 0, headers, rows, tableName);
  setWidths(sheet, headers);
  sheet.freezePanes.freezeRows(5);
  applyValidation(sheet, 5, headers, rows.length, validations);
  return { sheet, table };
}

// 00 guide
{
  const sheet = workbook.worksheets.add("00_유지보수가이드");
  writeTitle(sheet, "00 유지보수가이드", "이 시트만 읽고도 Excel 원본을 안전하게 수정하고 CSV를 재생성할 수 있도록 역할·절차·규칙을 설명합니다.", "D");
  sheet.getRange("A3:D3").values = [["원칙", "Excel은 사람이 편집하는 원본", "CSV는 자동 산출물", "Flyway는 실제 DB 적용 기준"]];
  sheet.getRange("A3:D3").format = { fill: colors.gold, font: { bold: true, color: colors.ink }, horizontalAlignment: "center" };
  const guide = addTable(sheet, 5, 0, ["구분", "순서", "항목", "안내"], guideRows, "tblMaintenanceGuide");
  const impactStart = guide.endRow + 3;
  sheet.getRange(`A${impactStart - 1}:D${impactStart - 1}`).merge();
  sheet.getRange(`A${impactStart - 1}`).values = [["6.7 변경 유형별 수정 범위"]];
  sheet.getRange(`A${impactStart - 1}:D${impactStart - 1}`).format = { fill: colors.navy, font: { bold: true, color: colors.white } };
  const impact = addTable(sheet, impactStart, 0, ["변경 유형", "필수 수정 시트", "조건부 확인", "버전 판단"], impactRows, "tblChangeImpact", { style: "TableStyleMedium4" });
  const checklistStart = impact.endRow + 3;
  sheet.getRange(`A${checklistStart - 1}:D${checklistStart - 1}`).merge();
  sheet.getRange(`A${checklistStart - 1}`).values = [["6.9 MR 리뷰 체크리스트"]];
  sheet.getRange(`A${checklistStart - 1}:D${checklistStart - 1}`).format = { fill: colors.navy, font: { bold: true, color: colors.white } };
  addTable(sheet, checklistStart, 0, ["번호", "체크", "검토 항목", "확인 방법"], checklistRows, "tblReviewChecklist", { style: "TableStyleMedium9" });
  sheet.getRange("A:A").format.columnWidth = 22; sheet.getRange("B:B").format.columnWidth = 10; sheet.getRange("C:C").format.columnWidth = 31; sheet.getRange("D:D").format.columnWidth = 78;
  sheet.freezePanes.freezeRows(5);
}

// 01 document info
{
  const sheet = workbook.worksheets.add("01_문서정보");
  writeTitle(sheet, "01 문서정보", "문서 버전·책임·기준 Git 상태와 각 시트의 목적을 관리합니다.", "F");
  const info = addTable(sheet, 5, 0, ["항목", "값"], documentInfoRows, "tblDocumentInfo");
  addTable(sheet, 5, 3, ["시트명", "목적"], sheetCatalogRows, "tblSheetCatalog", { style: "TableStyleMedium4" });
  sheet.getRange("A:A").format.columnWidth = 28; sheet.getRange("B:B").format.columnWidth = 58; sheet.getRange("D:D").format.columnWidth = 27; sheet.getRange("E:E").format.columnWidth = 70;
  sheet.freezePanes.freezeRows(5);
}

addStandardSheet("02_용어집", "02 용어집", "업무 의미와 사용을 피해야 할 모호한 표현을 통일합니다.", glossaryHeaders, glossaryRows, "tblGlossary", { "상태": "객체상태" });
addStandardSheet("03_테이블정의", "03 테이블정의", "테이블마다 한 행으로 업무 단위·책임·보존·삭제 정책을 정의합니다.", tableHeaders, tableRows, "tblTables", { "민감정보 포함 여부": "민감정보분류", "객체 상태": "객체상태" });
const columnsSheet = addStandardSheet("04_컬럼정의", "04 컬럼정의", `mvp-erd.md 데이터 사전의 실제 ${sourceColumnCount}개 컬럼을 원본 순서로 전수 반영했습니다.`, columnHeaders, columnRows, "tblColumns", {
  "NULL 허용 여부": "여부", "자동 생성 여부": "여부", "PK 여부": "여부", "FK 여부": "여부", "단일 컬럼 UNIQUE 여부": "여부",
  "민감정보 여부": "민감정보분류", "마스킹 필요 여부": "여부", "암호화 필요 여부": "여부", "감사 대상 여부": "여부", "객체 상태": "객체상태",
});
const constraintsSheet = addStandardSheet("05_관계_제약조건", "05 관계·제약조건", "PK/FK/UNIQUE/CHECK와 DB 밖 교차행·상태·멱등 규칙을 한 곳에서 관리합니다.", constraintHeaders, constraintRows, "tblConstraints", { "제약 유형": "제약유형", "DB 구현 여부": "여부", "구현 계층": "구현계층", "객체 상태": "객체상태" });
addStandardSheet("06_인덱스정의", "06 인덱스정의", "원본 ERD G절에 명시된 B-tree/부분 UNIQUE 인덱스만 반영하며 벡터 인덱스는 확정하지 않습니다.", indexHeaders, indexRows, "tblIndexes", { "인덱스 유형": "인덱스유형", "UNIQUE 여부": "여부", "객체 상태": "객체상태" });
const jsonSheet = addStandardSheet("07_JSONB정의", "07 JSONB정의", "승인된 8개 JSONB 컬럼의 키를 경로 단위로 정의하고 금지 정보·보존·호환성 규칙을 관리합니다.", jsonHeaders, jsonDefinitions, "tblJsonbFields", { "필수 여부": "여부", "NULL 허용 여부": "여부", "배열 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" });
const vectorSheet = addStandardSheet("08_벡터정의", "08 벡터정의", "pgvector 차원·모델·거리 함수는 확정 전까지 TBD이며 초기에는 정확 검색을 사용합니다.", vectorHeaders, vectorRows, "tblVectorFields", { "차원 확정 여부": "여부", "정규화 여부": "여부", "재생성 가능 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" });
const codeSheet = addStandardSheet("09_코드정의", "09 코드정의", "컬럼·JSONB에서 참조하는 코드값과 확인된 상태 전이를 코드 그룹별로 관리합니다.", codeHeaders, codeRows, "tblCodeValues", { "시작 상태 여부": "여부", "종료 상태 여부": "여부", "활성 여부": "여부" });
addStandardSheet("10_연계매핑", "10 연계매핑", "DB 컬럼 또는 승인 JSON 경로와 명시적으로 연결되는 REST·MQTT 필드만 반영합니다.", mappingHeaders, mappingRows, "tblInterfaceMappings", { "인터페이스 유형": "인터페이스유형", "방향": "매핑방향", "멱등성 키 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" });
addStandardSheet("11_변경이력", "11 변경이력", "변경 객체마다 버전·Jira·담당·호환성·Flyway 영향을 기록합니다.", changeHeaders, changeRows, "tblChangeHistory", { "변경 유형": "변경유형", "호환성": "호환성", "데이터 마이그레이션 필요 여부": "여부", "Flyway 필요 여부": "여부", "승인 상태": "승인상태" });

// Internal object links on column sheet. Links are presentation-only and excluded from CSV snapshots.
{
  const targetCol = columnHeaders.indexOf("관련 객체 이동");
  const formulas = columnRows.map((row) => {
    const fkId = row[columnHeaders.indexOf("FK 제약조건 ID")];
    const jsonId = row[columnHeaders.indexOf("JSONB 구조 ID")];
    const vectorId = row[columnHeaders.indexOf("벡터 정의 ID")];
    const codeId = row[columnHeaders.indexOf("코드 그룹 ID")];
    if (fkId !== "N/A") {
      const target = constraintRows.findIndex((r) => r[0] === fkId) + 6;
      return [`='05_관계_제약조건'!A${target}`];
    }
    if (jsonId !== "N/A") {
      const target = jsonDefinitions.findIndex((r) => r[0] === jsonId) + 6;
      return [`='07_JSONB정의'!A${target}`];
    }
    if (vectorId !== "N/A") return [`='08_벡터정의'!A6`];
    if (codeId !== "N/A") {
      const target = codeRows.findIndex((r) => r[0] === codeId) + 6;
      return [`='09_코드정의'!A${target}`];
    }
    const tableTarget = tableOrder.indexOf(row[columnHeaders.indexOf("테이블 물리명")]) + 6;
    return [`='03_테이블정의'!D${tableTarget}`];
  });
  columnsSheet.sheet.getRange(`${colLetter(targetCol)}6:${colLetter(targetCol)}${5 + columnRows.length}`).formulas = formulas;
}

// 12 validation with summary formulas
{
  const sheet = workbook.worksheets.add("12_검증결과");
  writeTitle(sheet, "12 검증결과", "구조·값·원본 정합성, TBD와 문서 충돌을 PASS/WARNING/ERROR로 구분합니다.", "J");
  sheet.getRange("A5:B7").values = [["요약 항목", "값"], ["ERROR", null], ["WARNING", null]];
  sheet.getRange("B6").formulas = [[`=COUNTIF(D11:D${10 + validationRows.length},"ERROR")`]];
  sheet.getRange("B7").formulas = [[`=COUNTIF(D11:D${10 + validationRows.length},"WARNING")`]];
  sheet.getRange("D5:E7").values = [["검사 기준", "값"], ["문서 버전", documentVersion], ["검사 일시", `${today} 00:00Z`]];
  sheet.getRange("A5:B5").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
  sheet.getRange("D5:E5").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
  sheet.getRange("A6:B7").format = { fill: colors.gray, font: { bold: true } };
  const table = addTable(sheet, 10, 0, validationHeaders, validationRows, "tblValidationResults", { style: "TableStyleMedium2" });
  setWidths(sheet, validationHeaders);
  sheet.getRange(`D11:D${table.endRow}`).dataValidation = { rule: { type: "list", formula1: "'99_입력목록'!$N$6:$N$8" } };
  sheet.getRange(`D11:D${table.endRow}`).conditionalFormats.add("containsText", { text: "ERROR", format: { fill: colors.red, font: { bold: true, color: "#991B1B" } } });
  sheet.getRange(`D11:D${table.endRow}`).conditionalFormats.add("containsText", { text: "WARNING", format: { fill: colors.amber, font: { bold: true, color: "#92400E" } } });
  sheet.getRange(`D11:D${table.endRow}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
  sheet.freezePanes.freezeRows(10);
}

// 99 input lists
{
  const sheet = workbook.worksheets.add("99_입력목록");
  const headers = Object.keys(inputLists);
  const maxRows = Math.max(...Object.values(inputLists).map((values) => values.length));
  const rows = Array.from({ length: maxRows }, (_, rowIndex) => headers.map((header) => inputLists[header][rowIndex] ?? null));
  writeTitle(sheet, "99 입력목록", "데이터 유효성 검사에 사용하는 표준 목록입니다. 비밀번호 보호 없이 관리자가 팀 합의 후 수정할 수 있습니다.", colLetter(headers.length - 1));
  sheet.mergeCells(`A4:${colLetter(headers.length - 1)}4`);
  sheet.getRange("A4").values = [["일반 사용자는 임의 수정하지 않습니다. 목록 변경은 Jira·변경이력·영향 시트를 함께 검토합니다."]];
  sheet.getRange(`A4:${colLetter(headers.length - 1)}4`).format = { fill: colors.gold, font: { bold: true } };
  addTable(sheet, 5, 0, headers, rows, "tblInputLists", { style: "TableStyleMedium4" });
  setWidths(sheet, headers);
  sheet.freezePanes.freezeRows(5);
}

// Consistent identifier/text formatting and required-column visual cue.
for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  if (used) used.format.verticalAlignment = "top";
}

const requiredColumnNames = new Set(["컬럼 ID", "테이블 물리명", "컬럼 순번", "컬럼 논리명", "컬럼 물리명", "컬럼 설명", "PostgreSQL 타입", "NULL 허용 여부", "기본값", "PK 여부", "FK 여부", "민감정보 여부", "보존 정책", "객체 상태", "최초 도입 버전", "최종 변경 Jira"]);
for (const [index, header] of columnHeaders.entries()) {
  if (requiredColumnNames.has(header)) columnsSheet.sheet.getRange(`${colLetter(index)}5`).format.fill = "#B45309";
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const summary = {
  outputPath,
  sourceCommit,
  branch,
  counts: {
    tables: tableRows.length,
    columns: columnRows.length,
    constraints: constraintRows.length,
    indexes: indexRows.length,
    jsonbFields: jsonDefinitions.length,
    vectorFields: vectorRows.length,
    codeValues: codeRows.length,
    interfaceMappings: mappingRows.length,
    validationErrors: validationRows.filter((row) => row[3] === "ERROR").length,
    validationWarnings: validationRows.filter((row) => row[3] === "WARNING").length,
  },
};
console.log(JSON.stringify(summary, null, 2));
