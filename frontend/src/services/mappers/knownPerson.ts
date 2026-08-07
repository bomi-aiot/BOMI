// 서버(GET /v1/known-persons, KnownPersonDto) → FE ImportantPerson 매핑.
// known_person 테이블에는 memory 메타데이터가 없어 보호자 확정 정보로 간주한다.

import type { ImportantPerson } from '../../types/domain'

export interface KnownPersonDto {
  id: string
  displayName?: string | null
  relationship?: string | null
  isDeceased?: boolean | null
  deceasedNote?: string | null
  livesWith?: boolean | null
  contactFrequency?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

function buildNote(dto: KnownPersonDto): string | undefined {
  const parts = [
    dto.isDeceased ? '돌아가신 분입니다.' : undefined,
    dto.deceasedNote?.trim() || undefined,
    dto.livesWith ? '함께 살고 계십니다.' : undefined,
    dto.contactFrequency?.trim()
      ? `연락 빈도: ${dto.contactFrequency.trim()}`
      : undefined,
  ].filter((part): part is string => Boolean(part))
  return parts.length > 0 ? parts.join(' ') : undefined
}

export function mapKnownPerson(
  dto: KnownPersonDto,
  elderId: string,
): ImportantPerson {
  const createdAt = dto.createdAt ?? ''
  const name = dto.displayName ?? ''
  return {
    id: dto.id,
    elderId,
    memoryType: 'PERSONAL_RELATIONSHIP',
    name,
    relationship: dto.relationship ?? '',
    preferredReference: name,
    note: buildNote(dto),
    source: 'GUARDIAN',
    verificationStatus: 'GUARDIAN_CONFIRMED',
    lifecycleStatus: 'ACTIVE',
    visibility: 'SHARED_WITH_GUARDIANS',
    createdAt,
    updatedAt: dto.updatedAt ?? createdAt,
  }
}
