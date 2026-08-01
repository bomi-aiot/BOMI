// 서버(GET /v1/guardian/dashboard, DashboardResponse) → FE HomeDashboardSummary 매핑.
// robot/homeEnvironment/medicationResponses 는 필드가 이미 정렬돼 거의 1:1.
// schedule 은 FE Schedule 타입이 더 넓어 서버에 없는 필드는 기본값으로 채운다.

import type {
  ActivitySummary,
  HomeDashboardSummary,
  HomeEnvironmentSummary,
  InformationSource,
  MedicationProgress,
  MedicationResponse,
  MedicationResponseStatus,
  RobotMode,
  RobotStatus,
  Schedule,
  ScheduleStatus,
  ScheduleType,
  StatusLevel,
} from '../../types/domain'
import { mapFactCandidate, type FactCandidateDto } from './confirmationRequest'

// --- 서버 응답 DTO (BE DashboardResponse 미러) -----------------------------

interface DashboardElderDto {
  id: string
  displayName: string
  statusLevel: string
  statusLabel: string
  lastCheckedAt: string
}

interface DashboardRobotDto {
  id: string | null
  elderId: string
  deviceId?: string | null
  currentMode?: string | null
  isActive: boolean
  ambientTemperatureC?: number | null
  ambientHumidityPercent?: number | null
  ambientObservedAt?: string | null
}

interface DashboardEnvDto {
  statusLevel: string
  label: string
  temperatureC?: number | null
  humidityPercent?: number | null
  lastObservedAt?: string | null
}

interface DashboardScheduleDto {
  id: string
  recordType: string
  title?: string | null
  startsAt?: string | null
  endsAt?: string | null
  location?: string | null
  relatedPersonName?: string | null
  status: string
}

interface DashboardMedResponseDto {
  id: string
  medicationId?: string | null
  medicationScheduleId?: string | null
  scheduledAt: string
  respondedAt?: string | null
  status: string
  responseText?: string | null
}

interface DashboardActivityDto {
  id: string
  title: string
  summary: string
  occurredAt: string
  source: string
  statusLevel: string
}

export interface DashboardDto {
  elder: DashboardElderDto
  robot: DashboardRobotDto
  homeEnvironment: DashboardEnvDto
  todayIncidentCount: number
  todaySchedules: DashboardScheduleDto[]
  medicationResponses: DashboardMedResponseDto[]
  medicationProgress: MedicationProgress
  pendingConfirmationCount: number
  confirmationRequests: FactCandidateDto[]
  recentActivities: DashboardActivityDto[]
  generatedAt: string
}

// --- 매핑 ------------------------------------------------------------------

const undef = <T>(value: T | null | undefined): T | undefined =>
  value === null || value === undefined ? undefined : value

function mapScheduleStatus(status: string): ScheduleStatus {
  if (status === 'COMPLETED') return 'COMPLETED'
  if (status === 'CANCELLED') return 'CANCELLED'
  return 'UPCOMING'
}

function mapRobot(dto: DashboardRobotDto): RobotStatus {
  return {
    id: dto.id ?? '',
    elderId: dto.elderId,
    deviceId: undef(dto.deviceId),
    currentMode: (dto.currentMode ?? 'IDLE') as RobotMode,
    isActive: dto.isActive,
    ambientTemperatureC: undef(dto.ambientTemperatureC),
    ambientHumidityPercent: undef(dto.ambientHumidityPercent),
    ambientObservedAt: undef(dto.ambientObservedAt),
  }
}

function mapEnv(dto: DashboardEnvDto): HomeEnvironmentSummary {
  return {
    statusLevel: dto.statusLevel as StatusLevel,
    label: dto.label,
    temperatureC: undef(dto.temperatureC),
    humidityPercent: undef(dto.humidityPercent),
    lastObservedAt: undef(dto.lastObservedAt),
  }
}

function mapSchedule(dto: DashboardScheduleDto, elderId: string): Schedule {
  const startsAt = dto.startsAt ?? ''
  return {
    id: dto.id,
    elderId,
    recordType: dto.recordType as ScheduleType,
    title: dto.title ?? '',
    startsAt,
    endsAt: undef(dto.endsAt),
    location: undef(dto.location),
    relatedPersonName: undef(dto.relatedPersonName),
    status: mapScheduleStatus(dto.status),
    reminderEnabled: false,
    reminderLeadMinutes: 0,
    followUpEnabled: false,
    sourceType: 'GUARDIAN',
    verificationStatus: 'GUARDIAN_CONFIRMED',
    createdAt: startsAt,
    updatedAt: startsAt,
  }
}

function mapMedicationResponse(dto: DashboardMedResponseDto): MedicationResponse {
  return {
    id: dto.id,
    medicationId: dto.medicationId ?? '',
    medicationScheduleId: dto.medicationScheduleId ?? '',
    scheduledAt: dto.scheduledAt,
    respondedAt: undef(dto.respondedAt),
    status: dto.status as MedicationResponseStatus,
    responseText: undef(dto.responseText),
  }
}

function mapActivity(dto: DashboardActivityDto, elderId: string): ActivitySummary {
  return {
    id: dto.id,
    elderId,
    title: dto.title,
    summary: dto.summary,
    occurredAt: dto.occurredAt,
    source: dto.source as InformationSource,
    statusLevel: dto.statusLevel as StatusLevel,
  }
}

export function mapDashboard(dto: DashboardDto): HomeDashboardSummary {
  const elderId = dto.elder.id
  return {
    elder: {
      id: dto.elder.id,
      displayName: dto.elder.displayName,
      statusLevel: dto.elder.statusLevel as StatusLevel,
      statusLabel: dto.elder.statusLabel,
      lastCheckedAt: dto.elder.lastCheckedAt,
    },
    robot: mapRobot(dto.robot),
    todayIncidentCount: dto.todayIncidentCount,
    homeEnvironment: mapEnv(dto.homeEnvironment),
    todaySchedules: dto.todaySchedules.map((s) => mapSchedule(s, elderId)),
    medications: [],
    medicationResponses: dto.medicationResponses.map(mapMedicationResponse),
    medicationProgress: dto.medicationProgress,
    pendingConfirmationCount: dto.pendingConfirmationCount,
    confirmationRequests: dto.confirmationRequests.map(mapFactCandidate),
    recentActivities: dto.recentActivities.map((a) => mapActivity(a, elderId)),
    generatedAt: dto.generatedAt,
  }
}
