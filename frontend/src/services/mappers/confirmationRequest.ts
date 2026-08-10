// 서버(fact_candidate) 응답 → FE ConfirmationRequest 매핑.
//
// 계약: 서버는 fact_candidate 원본 enum/필드를 그대로 내려주고, FE가 이 모듈에서
// 화면 표시값(status)·분류(kind)로 변환한다. (P0 필드매핑 문서 A-3 / A-4)
// USE_MOCK_API=false 로 실제 API를 붙일 때 HttpBomiService 가 이 함수를 사용한다.

import type {
  ConfirmationKind,
  ConfirmationRequest,
  ConfirmationRequestStatus,
  CoordinationStatus,
  InformationSource,
  RiskLevel,
  StructuredValue,
} from '../../types/domain'

// --- 서버 원본 enum (fact_candidate) ---------------------------------------

export type FactCandidateStatus =
  | 'CAPTURED'
  | 'NEEDS_CLARIFICATION'
  | 'NEEDS_CONFIRMATION'
  | 'COORDINATION_REQUIRED'
  | 'CONFIRMED'
  | 'MATERIALIZED'
  | 'REJECTED'
  | 'EXPIRED'

export type FactTargetDomain =
  | 'PROFILE'
  | 'CARE_RELATIONSHIP'
  | 'MEMORY'
  | 'CARE_RECORD'

export type FactOperation = 'CREATE' | 'UPDATE' | 'CANCEL'

export type FactSourceType = 'ONBOARDING_ANSWER' | 'CONVERSATION_MESSAGE'

// --- 서버 응답 DTO (fact_candidate 컬럼 + 서버 생성 문구) ---------------------
// 평평한 형태로, DB 컬럼명을 camelCase 로만 바꿔 미러링한다.
// title/summary/question/evidence 는 DB 컬럼이 아니라 서버가 생성하는 표시 문구.

export interface FactCandidateDto {
  id: string
  seniorId: string
  targetDomain: FactTargetDomain
  factType: string
  operation: FactOperation
  status: FactCandidateStatus
  riskLevel: RiskLevel
  coordinationStatus: CoordinationStatus
  sourceType: FactSourceType
  conversationId?: string | null
  sourceMessageId?: string | null
  proposedValue: StructuredValue
  confirmedValue?: StructuredValue | null
  // 충돌(UPDATE) 시 기존 값. 서버가 대상 엔티티의 현재 값을 함께 실어 보낸다.
  currentValue?: StructuredValue | null
  // 서버 생성 표시 문구
  title: string
  summary: string
  question: string
  evidence: string
  materializedTargetId?: string | null
  createdAt: string
  confirmedAt?: string | null
  materializedAt?: string | null
}

// --- A-3: 상태 매핑 --------------------------------------------------------

export function mapFactCandidateStatus(
  status: FactCandidateStatus,
): ConfirmationRequestStatus {
  switch (status) {
    case 'CONFIRMED':
    case 'MATERIALIZED':
      return 'CONFIRMED'
    case 'REJECTED':
      return 'REJECTED'
    case 'EXPIRED':
      return 'EXPIRED'
    // CAPTURED / NEEDS_CONFIRMATION / COORDINATION_REQUIRED
    // → 보호자 확인 대기. COORDINATION_REQUIRED 는 coordinationStatus 배지로 세부 표시.
    default:
      return 'PENDING'
  }
}

// --- A-4: 분류(kind) 파생 --------------------------------------------------
// fact_type 은 자유 문자열이라 target_domain + fact_type prefix 규칙으로 파생.
// ⚠️ FE ConfirmationKind 에는 일반 '복약' 값이 없어, 복약 CREATE 는 임시로 HEALTH 로
//    떨어진다. 복약 카테고리가 필요해지면 ConfirmationKind 확장 필요(후속).

export function deriveConfirmationKind(
  targetDomain: FactTargetDomain,
  factType: string,
  operation: FactOperation,
): ConfirmationKind {
  const ft = factType.toUpperCase()

  if (targetDomain === 'CARE_RECORD') {
    if (ft.startsWith('MEDICATION')) {
      return operation === 'UPDATE' ? 'MEDICATION_CONFLICT' : 'HEALTH'
    }
    if (ft.includes('SCHEDULE') || ft.includes('APPOINTMENT')) {
      return 'SCHEDULE'
    }
    return 'HEALTH'
  }

  // PROFILE / CARE_RELATIONSHIP / MEMORY → 관심사·선호 계열
  return 'INTEREST'
}

// 온보딩 답변·대화 메시지 모두 AI 가 추출한 후보이므로 표시상 'AI'.
const CONFIRMATION_SOURCE: InformationSource = 'AI'

const COORDINATION_VALUES = new Set<CoordinationStatus>([
  'NOT_REQUIRED',
  'COORDINATION_REQUIRED',
  'WAITING_PRIMARY_GUARDIAN',
  'WAITING_SENIOR',
  'AGREED',
  'DISAGREED',
  'SENIOR_UNREACHABLE',
  'GUARDIAN_OVERRIDE_CONFIRMED',
  'COMPLETED',
])

function normalizeRiskLevel(value: string): RiskLevel {
  return value === 'NORMAL' || value === 'SENSITIVE' || value === 'HIGH'
    ? value
    : 'HIGH'
}

function normalizeCoordinationStatus(value: string): CoordinationStatus {
  return COORDINATION_VALUES.has(value as CoordinationStatus)
    ? (value as CoordinationStatus)
    : 'COORDINATION_REQUIRED'
}

// 화면에 내보낼 수 있는 키. 여기 없는 키는 통째로 버린다 — proposedValue 는 서버가
// 검증하지 않는 자유 JSON 이라, 모르는 키를 그대로 그리면 무엇이 나올지 알 수 없다.
//
// ★ 'content' 가 빠져 있었다. 그리고 로봇이 보내는 키는 그것 하나다
//   (ai_chat fact_contract.to_intake_payload — 나머지 키를 채우는 경로는 APPOINTMENT
//   뿐이다). 그래서 이 목록은 <b>로봇이 만든 모든 확인 요청의 값을 100% 걸러냈고</b>,
//   화면에는 "AI가 제안한 내용"이라는 제목이 붙은 빈 상자만 남았다. 보호자가 무엇을
//   확정하는지 모르는 채로 확정 버튼을 누르는 화면이었다.
//
//   허용 목록 자체는 유지한다 — 없애면 방어선이 사라진다. 대신 실제로 오는 키를
//   목록에 넣는다. 어느 종류든 content 는 어르신이 한 말이므로 전부에 넣는다.
const SAFE_VALUE_KEYS: Record<ConfirmationKind, readonly string[]> = {
  INTEREST: ['content', 'memoryType', 'title', 'keywords'],
  SCHEDULE: ['content', 'recordType', 'title', 'startsAt'],
  HEALTH: ['content', 'note', 'recordType', 'title', 'statusLevel'],
  MEDICATION_CONFLICT: [
    'content',
    'medicationName',
    'localTime',
    'localTimes',
  ],
}

function sanitizeValue(
  value: StructuredValue | null | undefined,
  kind: ConfirmationKind,
): StructuredValue | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const allowed = new Set(SAFE_VALUE_KEYS[kind])
  const safeEntries = Object.entries(value).filter(([key, item]) => {
    if (!allowed.has(key)) return false
    if (key === 'keywords' || key === 'localTimes') {
      return Array.isArray(item) && item.every((entry) => typeof entry === 'string')
    }
    return typeof item === 'string'
  })
  return safeEntries.length > 0 ? Object.fromEntries(safeEntries) : undefined
}

// 서버 문구가 비어 올 때만 쓰는 폴백.
//
// 왜 "폴백만" 인가 — 예전에는 이 문구가 서버 값을 <b>덮어썼다.</b> 그러면 어떤 건강
// 후보든 화면에 한 글자도 다르지 않게 보인다. 보호자는 "확인 배경"이라는 칸을 매번
// 읽지만 거기서 얻는 정보는 언제나 0이고, 서버가 실제로 보낸 근거("사용자 직접 발화")도
// 함께 버려진다. 같은 실수를 안전 알림에서 이미 한 번 고쳤다
// (mappers/dashboard.ts 의 mapKnownT1Alert / mapGuardianSafeActivity 주석).
//
// 그래도 폴백을 지우지는 않는다 — 서버가 문구를 못 만든 경우(구버전 백엔드, 빈 문자열)에
// 카드가 빈 줄을 그리면 안 되기 때문이다. 위 두 함수와 정확히 같은 구조다.
function fallbackCopy(kind: ConfirmationKind): Pick<
  ConfirmationRequest,
  'title' | 'summary' | 'question' | 'evidence'
> {
  switch (kind) {
    case 'SCHEDULE':
      return {
        title: '새 일정을 확인해 주세요',
        summary: '보미가 일정으로 보이는 새 정보를 들었어요.',
        question: '확인한 뒤 돌봄 계획에 반영할까요?',
        evidence: '대화에서 확인 전 일정 후보로 정리됐어요.',
      }
    case 'HEALTH':
      return {
        title: '건강 관련 정보를 확인해 주세요',
        summary: '보미가 돌봄에 참고할 수 있는 새 정보를 들었어요.',
        question: '어르신께 다시 확인한 뒤 기록할까요?',
        evidence: '확정 전 건강 정보 후보예요.',
      }
    case 'MEDICATION_CONFLICT':
      return {
        title: '복약 정보가 기존 기록과 달라요',
        summary: '기록된 정보는 변경하지 않고 보호자 확인을 기다리고 있어요.',
        question: '어르신과 처방 내용을 다시 확인할까요?',
        evidence: '복약 정보가 서로 달라 자동 반영하지 않았어요.',
      }
    case 'INTEREST':
      return {
        title: '새 정보를 확인해 주세요',
        summary: '보미가 관심사나 생활 습관으로 보이는 정보를 들었어요.',
        question: '확인한 뒤 대화와 돌봄에 참고할까요?',
        evidence: '대화에서 확인 전 후보로 정리됐어요.',
      }
  }
}

// --- 전체 매핑 -------------------------------------------------------------

const preferServerText = (
  value: string | null | undefined,
  fallback: string,
): string => {
  const trimmed = typeof value === 'string' ? value.trim() : ''
  return trimmed.length > 0 ? trimmed : fallback
}

export function mapFactCandidate(dto: FactCandidateDto): ConfirmationRequest {
  const kind = deriveConfirmationKind(dto.targetDomain, dto.factType, dto.operation)
  const fallback = fallbackCopy(kind)
  const copy = {
    title: preferServerText(dto.title, fallback.title),
    summary: preferServerText(dto.summary, fallback.summary),
    question: preferServerText(dto.question, fallback.question),
    evidence: preferServerText(dto.evidence, fallback.evidence),
  }
  const proposedValue = sanitizeValue(dto.proposedValue, kind) ?? {}
  const currentValue = sanitizeValue(dto.currentValue, kind)
  const canResolve = dto.status === 'NEEDS_CONFIRMATION'
  const canRequestRecheck =
    dto.status === 'NEEDS_CONFIRMATION' ||
    dto.status === 'NEEDS_CLARIFICATION' ||
    dto.status === 'COORDINATION_REQUIRED'
  const riskLevel = normalizeRiskLevel(dto.riskLevel)
  const coordinationStatus = normalizeCoordinationStatus(dto.coordinationStatus)

  return {
    id: dto.id,
    elderId: dto.seniorId,
    kind,
    ...copy,
    currentValue,
    proposedValue,
    status: mapFactCandidateStatus(dto.status),
    riskLevel,
    coordinationStatus,
    source: CONFIRMATION_SOURCE,
    origin:
      dto.sourceType === 'CONVERSATION_MESSAGE'
        ? 'CONVERSATION'
        : dto.sourceType === 'ONBOARDING_ANSWER'
          ? 'ONBOARDING'
          : undefined,
    sourceConversationId: dto.conversationId ?? undefined,
    sourceMessageId: dto.sourceMessageId ?? undefined,
    createdAt: dto.createdAt,
    resolvedAt: dto.confirmedAt ?? dto.materializedAt ?? undefined,
    appliedEntityId: dto.materializedTargetId ?? undefined,
    canResolve,
    canRequestRecheck,
    waitingReason:
      dto.status === 'NEEDS_CLARIFICATION'
        ? 'CLARIFICATION'
        : dto.status === 'COORDINATION_REQUIRED'
          ? 'COORDINATION'
          : dto.status === 'CAPTURED'
            ? 'CAPTURED'
            : dto.status === 'EXPIRED'
              ? 'EXPIRED'
              : undefined,
  }
}
