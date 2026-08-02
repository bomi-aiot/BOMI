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

function deriveTitle(keywords: string[], content: string): string {
  if (keywords.length > 0) return keywords[0]
  if (content.length <= 20) return content
  return `${content.slice(0, 20)}…`
}

export function mapMemory(dto: MemoryDto): ConversationPreference {
  const keywords = dto.keywords ?? []
  const content = dto.content ?? ''
  const createdAt = dto.firstObservedAt ?? ''
  return {
    id: dto.id,
    elderId: '',
    memoryType: (dto.memoryType ?? 'OTHER') as MemoryType,
    title: deriveTitle(keywords, content),
    content,
    keywords,
    isEnabled: dto.lifecycleStatus === 'ACTIVE',
    source: 'AI' as InformationSource,
    sourceConversationId: undef(dto.sourceConversationId),
    verificationStatus: (dto.verificationStatus ??
      'UNVERIFIED') as MemoryVerificationStatus,
    lifecycleStatus: (dto.lifecycleStatus ?? 'ACTIVE') as MemoryLifecycleStatus,
    visibility: (dto.visibility ?? 'PRIVATE') as MemoryVisibility,
    lastConfirmedAt: undef(dto.lastConfirmedAt),
    createdAt,
    updatedAt: dto.lastConfirmedAt ?? createdAt,
  }
}
