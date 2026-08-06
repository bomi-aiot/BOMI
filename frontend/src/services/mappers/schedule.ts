// 서버(GET /v1/care-records/schedules, ScheduleDto) → FE Schedule 매핑.
// care_record.details(계약 §1-4)는 이미 FE 이름을 쓰므로 대부분 1:1.
// FE Schedule 이 더 넓은 필드는 기본값으로 채운다(sourceType/verificationStatus 등).

import type {
  Schedule,
  ScheduleStatus,
  ScheduleType,
} from '../../types/domain'

export interface ScheduleDto {
  id: string
  recordType: string
  status: string
  title?: string | null
  startsAt?: string | null
  endsAt?: string | null
  location?: string | null
  relatedPersonName?: string | null
  description?: string | null
  reminderEnabled?: boolean | null
  reminderLeadMinutes?: number | null
  followUpEnabled?: boolean | null
  followUpQuestion?: string | null
}

const undef = <T>(v: T | null | undefined): T | undefined =>
  v === null || v === undefined ? undefined : v

function mapScheduleStatus(status: string): ScheduleStatus {
  if (status === 'COMPLETED') return 'COMPLETED'
  if (status === 'CANCELLED') return 'CANCELLED'
  if (status === 'UPCOMING' || status === 'ACTIVE') return 'UPCOMING'
  return 'UNKNOWN'
}

export function mapSchedule(dto: ScheduleDto): Schedule {
  if (dto.recordType !== 'APPOINTMENT' && dto.recordType !== 'PERSONAL_SCHEDULE') {
    throw new Error('지원하지 않는 일정 유형입니다.')
  }
  const startsAt = dto.startsAt ?? ''
  if (Number.isNaN(new Date(startsAt).getTime())) {
    throw new Error('일정 시각을 확인할 수 없습니다.')
  }
  return {
    id: dto.id,
    elderId: '',
    recordType: dto.recordType as ScheduleType,
    title: dto.title?.trim() || '제목이 확인되지 않은 일정',
    description: undef(dto.description),
    startsAt,
    endsAt: undef(dto.endsAt),
    location: undef(dto.location),
    relatedPersonName: undef(dto.relatedPersonName),
    status: mapScheduleStatus(dto.status),
    reminderEnabled: dto.reminderEnabled ?? false,
    reminderLeadMinutes: dto.reminderLeadMinutes ?? 0,
    followUpEnabled: dto.followUpEnabled ?? false,
    followUpQuestion: undef(dto.followUpQuestion),
    sourceType: 'SYSTEM',
    verificationStatus: 'UNVERIFIED',
    createdAt: '',
    updatedAt: '',
  }
}
