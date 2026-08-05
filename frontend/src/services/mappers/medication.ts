// 서버(GET /v1/care-records/medications, /medication-responses) → FE Medication/MedicationResponse.
// BE 는 seed 필드명(medicationName/dose/doseUnit)을 그대로 전송 → FE 에서 name/dosage 로 변환(계약퍼스트).

import type {
  Medication,
  MedicationResponse,
  MedicationResponseStatus,
  MedicationSchedule,
  MedicationStatus,
  RecurrenceType,
} from '../../types/domain'

interface MedicationScheduleDto {
  id: string
  medicationId?: string | null
  recurrence?: string | null
  timeZone?: string | null
  localTimes?: string[] | null
  reminderLeadMinutes?: number | null
  isActive: boolean
}

export interface MedicationDto {
  id: string
  recordType: string
  status: string
  medicationName?: string | null
  dose?: string | null
  doseUnit?: string | null
  instruction?: string | null
  purpose?: string | null
  activeIngredient?: string | null
  startedOn?: string | null
  endedOn?: string | null
  reminderEnabled?: boolean | null
  schedules: MedicationScheduleDto[]
}

export interface MedicationResponseDto {
  id: string
  medicationId?: string | null
  medicationScheduleId?: string | null
  scheduledAt: string
  respondedAt?: string | null
  status: string
  responseText?: string | null
}

const undef = <T>(v: T | null | undefined): T | undefined =>
  v === null || v === undefined ? undefined : v

function mapMedicationStatus(status: string): MedicationStatus {
  if (status === 'ACTIVE' || status === 'PAUSED' || status === 'ENDED') {
    return status
  }
  return 'UNKNOWN'
}

function mapMedicationSchedule(dto: MedicationScheduleDto): MedicationSchedule {
  return {
    id: dto.id,
    recordType: 'MEDICATION_SCHEDULE',
    medicationId: dto.medicationId ?? '',
    recurrence: (dto.recurrence ?? 'DAILY') as RecurrenceType,
    timeZone: dto.timeZone ?? 'Asia/Seoul',
    localTimes: dto.localTimes ?? [],
    startsOn: '',
    reminderLeadMinutes: dto.reminderLeadMinutes ?? 0,
    isActive: dto.isActive,
  }
}

export function mapMedication(dto: MedicationDto): Medication {
  const dosage = `${dto.dose ?? ''}${dto.doseUnit ?? ''}`.trim()
  return {
    id: dto.id,
    elderId: '',
    recordType: 'MEDICATION',
    name: dto.medicationName ?? '',
    dosage,
    purpose: undef(dto.purpose),
    instructions: undef(dto.instruction),
    activeIngredient: undef(dto.activeIngredient),
    startedOn: undef(dto.startedOn),
    endedOn: undef(dto.endedOn),
    status: mapMedicationStatus(dto.status),
    schedules: (dto.schedules ?? []).map(mapMedicationSchedule),
    reminderEnabled: dto.reminderEnabled ?? false,
    sourceType: 'SYSTEM',
    verificationStatus: 'UNVERIFIED',
    createdAt: '',
    updatedAt: '',
  }
}

export function mapMedicationResponse(dto: MedicationResponseDto): MedicationResponse {
  const status: MedicationResponseStatus =
    dto.status === 'CONFIRMED' ||
    dto.status === 'NO_RESPONSE' ||
    dto.status === 'UPCOMING' ||
    dto.status === 'MISSED' ||
    dto.status === 'DECLINED'
      ? dto.status
      : 'UNKNOWN'
  return {
    id: dto.id,
    medicationId: dto.medicationId ?? '',
    medicationScheduleId: dto.medicationScheduleId ?? '',
    scheduledAt: dto.scheduledAt,
    respondedAt: undef(dto.respondedAt),
    status,
  }
}
