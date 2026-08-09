// 서버(fact_candidate) 응답 → FE ConfirmationRequest 매핑.
//
// 계약: 서버는 fact_candidate 원본 enum/필드를 그대로 내려주고, FE가 이 모듈에서
// 화면 표시값(status)·분류(kind)로 변환한다. (P0 필드매핑 문서 A-3 / A-4)
// HttpBomiService 가 GET /v1/confirmation-requests 응답을 도메인 타입으로 바꿀 때 사용한다.

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

const SAFE_VALUE_KEYS: Record<ConfirmationKind, readonly string[]> = {
  INTEREST: ['content', 'memoryType', 'title', 'keywords'],
  SCHEDULE: ['content', 'recordType', 'title', 'startsAt'],
  HEALTH: ['content', 'recordType', 'title', 'statusLevel'],
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
