// 서버(GET /v1/memories, MemoryDto) → FE ConversationPreference 매핑.
// memory 테이블에 title/isEnabled 컬럼이 없어 FE 에서 파생한다.
//   - title  : keywords[0] ?? content 앞부분
//   - isEnabled : lifecycleStatus === 'ACTIVE'

import type {
  ConversationPreference,
  InformationSource,
  MemoryLifecycleStatus,
  MemoryType,
  MemoryVerificationStatus,
  MemoryVisibility,
} from '../../types/domain'

export interface MemoryDto {
  id: string
  seniorId: string
  memoryType?: string | null
  content?: string | null
  keywords?: string[] | null
  visibility?: string | null
  verificationStatus?: string | null
  lifecycleStatus?: string | null
  sourceConversationId?: string | null
  firstObservedAt?: string | null
  lastConfirmedAt?: string | null
}

const undef = <T>(v: T | null | undefined): T | undefined =>
  v === null || v === undefined ? undefined : v

const MEMORY_TYPE_VALUES = new Set<MemoryType>([
  'PERSONAL_RELATIONSHIP',
  'PREFERENCE',
  'HOBBY',
  'DAILY_ROUTINE',
  'LIFE_EVENT',
  'FAMILY_MEMORY',
  'EMOTIONAL_EVENT',
  'CONVERSATION_SUMMARY',
  'OTHER',
])

const VERIFICATION_VALUES = new Set<MemoryVerificationStatus>([
  'UNVERIFIED',
  'AUTO_ACCEPTED',
  'USER_CONFIRMED',
  'GUARDIAN_CONFIRMED',
  'REJECTED',
])

const LIFECYCLE_VALUES = new Set<MemoryLifecycleStatus>([
  'ACTIVE',
  'DISPUTED',
  'SUPERSEDED',
  'EXPIRED',
  'DELETED',
])

const VISIBILITY_VALUES = new Set<MemoryVisibility>([
  'PRIVATE',
  'SHARED_WITH_PRIMARY',
  'SHARED_WITH_GUARDIANS',
])

function deriveTitle(keywords: string[], content: string): string {
  if (keywords.length > 0) return keywords[0]
  if (content.length <= 20) return content
  return `${content.slice(0, 20)}…`
}

export function mapMemory(dto: MemoryDto): ConversationPreference {
  const keywords = dto.keywords ?? []
  const content = dto.content ?? ''
  const createdAt = dto.firstObservedAt ?? ''
  const memoryType = MEMORY_TYPE_VALUES.has(dto.memoryType as MemoryType)
    ? (dto.memoryType as MemoryType)
    : 'OTHER'
  const verificationStatus = VERIFICATION_VALUES.has(
    dto.verificationStatus as MemoryVerificationStatus,
  )
    ? (dto.verificationStatus as MemoryVerificationStatus)
    : 'UNVERIFIED'
  const lifecycleStatus = LIFECYCLE_VALUES.has(
    dto.lifecycleStatus as MemoryLifecycleStatus,
  )
    ? (dto.lifecycleStatus as MemoryLifecycleStatus)
    : 'EXPIRED'
  const visibility = VISIBILITY_VALUES.has(dto.visibility as MemoryVisibility)
    ? (dto.visibility as MemoryVisibility)
    : 'PRIVATE'
  return {
    id: dto.id,
    elderId: dto.seniorId,
    memoryType,
    title: deriveTitle(keywords, content),
    content,
    keywords,
    isEnabled: lifecycleStatus === 'ACTIVE',
    source: 'SYSTEM' as InformationSource,
    verificationStatus,
    lifecycleStatus,
    visibility,
    lastConfirmedAt: undef(dto.lastConfirmedAt),
    createdAt,
    updatedAt: dto.lastConfirmedAt ?? createdAt,
  }
}

export function isGuardianVisibleMemory(
  memory: ConversationPreference,
): boolean {
  const guardianVisible =
    memory.visibility === 'SHARED_WITH_PRIMARY' ||
    memory.visibility === 'SHARED_WITH_GUARDIANS'
  const safeMemoryType =
    memory.memoryType !== 'CONVERSATION_SUMMARY' &&
    memory.memoryType !== 'EMOTIONAL_EVENT'

  return (
    guardianVisible &&
    safeMemoryType &&
    memory.lifecycleStatus === 'ACTIVE' &&
    memory.verificationStatus !== 'REJECTED'
  )
}
