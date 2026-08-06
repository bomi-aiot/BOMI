import type {
  ActivitySummary,
  HomeDashboardSummary,
  InformationSource,
  MedicationProgress,
  MedicationResponse,
  MedicationResponseStatus,
  RobotMode,
  RobotStatus,
  SafetyAlert,
  Schedule,
  ScheduleStatus,
  ScheduleType,
} from '../../types/domain'
import { mapFactCandidate, type FactCandidateDto } from './confirmationRequest'

interface DashboardElderDto {
  id: string
  displayName?: string | null
  statusLevel?: string | null
  statusLabel?: string | null
  lastCheckedAt?: string | null
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
  statusLevel?: string | null
  label?: string | null
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
  status?: string | null
}

interface DashboardMedResponseDto {
  id: string
  medicationId?: string | null
  medicationScheduleId?: string | null
  scheduledAt?: string | null
  respondedAt?: string | null
  status?: string | null
  responseText?: string | null
}

interface DashboardActivityDto {
  id: string
  title?: string | null
  summary?: string | null
  occurredAt?: string | null
  source?: string | null
  statusLevel?: string | null
  visibility?: string | null
}

export interface DashboardDto {
  elder: DashboardElderDto
  robot: DashboardRobotDto
  homeEnvironment: DashboardEnvDto
  todayIncidentCount?: number | null
  todaySchedules?: DashboardScheduleDto[] | null
  medicationResponses?: DashboardMedResponseDto[] | null
  medicationProgress?: MedicationProgress | null
  pendingConfirmationCount?: number | null
  confirmationRequests?: FactCandidateDto[] | null
  recentActivities?: DashboardActivityDto[] | null
  activityVisibilityContract?: string | null
  generatedAt: string
}

const undef = <T>(value: T | null | undefined): T | undefined =>
  value === null || value === undefined ? undefined : value

const isValidDateTime = (value: string | null | undefined): value is string =>
  typeof value === 'string' && !Number.isNaN(new Date(value).getTime())

const ROBOT_MODES = new Set<RobotMode>([
  'IDLE',
  'SCENARIO_ACTIVE',
  'REST_GUARD',
  'SAFE_STOP',
  'HOMECOMING',
])

function mapRobotMode(value: string | null | undefined): RobotMode | undefined {
  return ROBOT_MODES.has(value as RobotMode) ? (value as RobotMode) : undefined
}

function mapRobot(dto: DashboardRobotDto): RobotStatus {
  return {
    id: dto.id ?? '',
    elderId: dto.elderId,
    deviceId: undef(dto.deviceId),
    currentMode: mapRobotMode(dto.currentMode),
    registrationActive: dto.isActive,
    ambientTemperatureC: undef(dto.ambientTemperatureC),
    ambientHumidityPercent: undef(dto.ambientHumidityPercent),
    ambientObservedAt: isValidDateTime(dto.ambientObservedAt)
      ? dto.ambientObservedAt
      : undefined,
  }
}

function mapScheduleStatus(status: string | null | undefined): ScheduleStatus {
  if (status === 'COMPLETED') return 'COMPLETED'
  if (status === 'CANCELLED') return 'CANCELLED'
  if (status === 'UPCOMING' || status === 'ACTIVE') return 'UPCOMING'
  return 'UNKNOWN'
}

function mapScheduleType(value: string): ScheduleType | null {
  if (value === 'APPOINTMENT' || value === 'PERSONAL_SCHEDULE') return value
  return null
}

function mapSchedule(dto: DashboardScheduleDto, elderId: string): Schedule | null {
  const recordType = mapScheduleType(dto.recordType)
  if (!recordType || !isValidDateTime(dto.startsAt)) return null

  return {
    id: dto.id,
    elderId,
    recordType,
    title: dto.title?.trim() || '제목이 확인되지 않은 일정',
    startsAt: dto.startsAt,
    endsAt: isValidDateTime(dto.endsAt) ? dto.endsAt : undefined,
    location: undef(dto.location),
    relatedPersonName: undef(dto.relatedPersonName),
    status: mapScheduleStatus(dto.status),
    reminderEnabled: false,
    reminderLeadMinutes: 0,
    followUpEnabled: false,
    sourceType: 'SYSTEM',
    verificationStatus: 'UNVERIFIED',
    createdAt: '',
    updatedAt: '',
  }
}

function mapMedicationResponseStatus(
  status: string | null | undefined,
): MedicationResponseStatus {
  if (
    status === 'CONFIRMED' ||
    status === 'NO_RESPONSE' ||
    status === 'UPCOMING' ||
    status === 'MISSED' ||
    status === 'DECLINED'
  ) {
    return status
  }
  return 'UNKNOWN'
}

function mapMedicationResponse(
  dto: DashboardMedResponseDto,
): MedicationResponse | null {
  if (!isValidDateTime(dto.scheduledAt)) return null
  return {
    id: dto.id,
    medicationId: dto.medicationId ?? '',
    medicationScheduleId: dto.medicationScheduleId ?? '',
    scheduledAt: dto.scheduledAt,
    respondedAt: isValidDateTime(dto.respondedAt) ? dto.respondedAt : undefined,
    status: mapMedicationResponseStatus(dto.status),
  }
}

function normalizeSource(source: string | null | undefined): InformationSource {
  if (source === 'ROBOT' || source === '로봇') return 'ROBOT'
  if (source === 'GUARDIAN') return 'GUARDIAN'
  if (source === 'USER') return 'USER'
  if (source === 'AI') return 'AI'
  return 'SYSTEM'
}

function mapKnownT1Alert(dto: DashboardActivityDto): SafetyAlert | null {
  if (
    dto.statusLevel !== 'URGENT' ||
    normalizeSource(dto.source) !== 'ROBOT'
  ) {
    return null
  }
  return {
    id: dto.id,
    message: '보미의 안전 확인 요청이 보호자에게 도착했어요.',
    occurredAt: isValidDateTime(dto.occurredAt) ? dto.occurredAt : undefined,
    status: 'OPEN',
  }
}

function mapGuardianSafeActivity(
  dto: DashboardActivityDto,
  elderId: string,
): ActivitySummary | null {
  const guardianVisibility =
    dto.visibility === 'SHARED_WITH_PRIMARY' ||
    dto.visibility === 'SHARED_WITH_GUARDIANS'
      ? dto.visibility
      : undefined
  if (
    !guardianVisibility ||
    dto.statusLevel !== 'INFO' ||
    normalizeSource(dto.source) !== 'ROBOT'
  ) {
    return null
  }
  if (!isValidDateTime(dto.occurredAt)) return null
  return {
    id: dto.id,
    elderId,
    title: '공유된 하루 요약',
    summary: '보미가 보호자에게 공유하도록 정리한 하루 기록이 도착했어요.',
    occurredAt: dto.occurredAt,
    source: 'ROBOT',
    statusLevel: 'NORMAL',
    kind: 'DAILY_SUMMARY',
    visibility: guardianVisibility,
  }
}

function latestObservedAt(values: Array<string | undefined>): string | undefined {
  return values
    .filter((value): value is string => isValidDateTime(value))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0]
}

export function mapDashboard(dto: DashboardDto): HomeDashboardSummary {
  const elderId = dto.elder.id
  const activityDtos = dto.recentActivities ?? []
  const knownT1Alerts = activityDtos
    .map(mapKnownT1Alert)
    .filter((alert): alert is SafetyAlert => alert !== null)
  const mappedActivities = activityDtos
    .map((activity) => mapGuardianSafeActivity(activity, elderId))
    .filter((activity): activity is ActivitySummary => activity !== null)
  const recentActivities =
    dto.activityVisibilityContract === 'GUARDIAN_VISIBLE_V1'
      ? mappedActivities
      : null
  const environmentObservedAt = isValidDateTime(dto.homeEnvironment.lastObservedAt)
    ? dto.homeEnvironment.lastObservedAt
    : undefined
  const robot = mapRobot(dto.robot)

  return {
    elder: {
      id: elderId,
      displayName: dto.elder.displayName?.trim() || '어르신',
      lastObservedAt: latestObservedAt([
        environmentObservedAt,
        robot.ambientObservedAt,
        ...knownT1Alerts.map((alert) => alert.occurredAt),
        ...(recentActivities ?? []).map((activity) => activity.occurredAt),
      ]),
    },
    robot,
    // 현재 DTO는 T1을 최근 활동 5건에 섞어 주므로, 관측된 T1은 표시하되
    // 없을 때는 전체 알림 조회 성공으로 간주하지 않는다.
    safetyAlerts: knownT1Alerts.length > 0 ? knownT1Alerts : null,
    homeEnvironment: {
      temperatureC: undef(dto.homeEnvironment.temperatureC),
      humidityPercent: undef(dto.homeEnvironment.humidityPercent),
      lastObservedAt: environmentObservedAt,
    },
    todaySchedules: (dto.todaySchedules ?? [])
      .map((schedule) => mapSchedule(schedule, elderId))
      .filter((schedule): schedule is Schedule => schedule !== null),
    medications: [],
    medicationResponses: (dto.medicationResponses ?? [])
      .map(mapMedicationResponse)
      .filter((response): response is MedicationResponse => response !== null),
    medicationProgress: dto.medicationProgress ?? {
      total: 0,
      confirmed: 0,
      noResponse: 0,
      upcoming: 0,
      missed: 0,
    },
    pendingConfirmationCount: Math.max(0, dto.pendingConfirmationCount ?? 0),
    confirmationRequests: (dto.confirmationRequests ?? []).map(mapFactCandidate),
    recentActivities,
    generatedAt: dto.generatedAt,
  }
}
