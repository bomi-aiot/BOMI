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
    case 'NEEDS_CLARIFICATION':
      return 'REASK_REQUESTED'
    case 'CONFIRMED':
    case 'MATERIALIZED':
      return 'CONFIRMED'
    case 'REJECTED':
    case 'EXPIRED':
      return 'REJECTED'
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

// --- 전체 매핑 -------------------------------------------------------------

export function mapFactCandidate(dto: FactCandidateDto): ConfirmationRequest {
  return {
    id: dto.id,
    elderId: dto.seniorId,
    kind: deriveConfirmationKind(dto.targetDomain, dto.factType, dto.operation),
    title: dto.title,
    summary: dto.summary,
    question: dto.question,
    evidence: dto.evidence,
    currentValue: dto.currentValue ?? undefined,
    proposedValue: dto.proposedValue,
    status: mapFactCandidateStatus(dto.status),
    riskLevel: dto.riskLevel,
    coordinationStatus: dto.coordinationStatus,
    source: CONFIRMATION_SOURCE,
    sourceConversationId: dto.conversationId ?? undefined,
    sourceMessageId: dto.sourceMessageId ?? undefined,
    createdAt: dto.createdAt,
    resolvedAt: dto.confirmedAt ?? dto.materializedAt ?? undefined,
    appliedEntityId: dto.materializedTargetId ?? undefined,
  }
}
