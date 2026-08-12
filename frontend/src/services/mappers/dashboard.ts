import type {
  ActivitySummary,
  GuardianSummary,
  HomeDashboardSummary,
  InformationSource,
  MedicationProgress,
  MedicationResponse,
  MedicationResponseStatus,
  RobotMode,
  RobotStatus,
  SafetyAlert,
  ScenarioType,
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
  activeScenarioType?: string | null
  activeScenarioStartedAt?: string | null
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

interface DashboardGuardianDto {
  id?: string | null
  name?: string | null
  priority?: string | null
}

export interface DashboardDto {
  elder: DashboardElderDto
  guardian?: DashboardGuardianDto | null
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
])

const SCENARIO_TYPES = new Set<ScenarioType>([
  'HOMECOMING',
  'WELLNESS_CHECK',
  'MEDICATION_REMINDER',
  'WAKE_WORD_CALL',
  'WALK',
  'FALL_RESPONSE',
  'MANUAL_INTERACTION',
])

function mapRobotMode(value: string | null | undefined): RobotMode | undefined {
  return ROBOT_MODES.has(value as RobotMode) ? (value as RobotMode) : undefined
}

// 모르는 값은 버린다 — 백엔드에 시나리오 종류가 늘어도 화면이 깨지지 않고,
// 배너는 모드 라벨로 조용히 폴백한다.
function mapScenarioType(value: string | null | undefined): ScenarioType | undefined {
  return SCENARIO_TYPES.has(value as ScenarioType) ? (value as ScenarioType) : undefined
}

function mapRobot(dto: DashboardRobotDto): RobotStatus {
  return {
    id: dto.id ?? '',
    elderId: dto.elderId,
    deviceId: undef(dto.deviceId),
    currentMode: mapRobotMode(dto.currentMode),
    activeScenarioType: mapScenarioType(dto.activeScenarioType),
    activeScenarioStartedAt: isValidDateTime(dto.activeScenarioStartedAt)
      ? dto.activeScenarioStartedAt
      : undefined,
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
  // 문구를 왜 여기서 만들지 않는가
  //   백엔드는 이미 사유별 문구를 만들어 보낸다(DashboardService.alertSummary:
  //   no_response / not_returned / self_harm_override / explicit_request).
  //   지금까지 그 값을 버리고 고정 문구 한 줄을 썼고, 그래서 사유가 다른 알림
  //   세 건이 화면에서 한 글자도 다르지 않게 보였다 — 보호자는 무슨 일이
  //   있었는지 화면만 봐서는 끝내 알 수 없었다.
  //
  //   고정 문구는 폴백으로만 남긴다. summary 가 비어 오는 경우(구버전 백엔드,
  //   details.reason 누락)에도 카드가 빈 줄을 그리면 안 되기 때문이다.
  const summary = dto.summary?.trim()
  return {
    id: dto.id,
    message:
      summary && summary.length > 0
        ? summary
        : '보미의 안전 확인 요청이 보호자에게 도착했어요.',
    occurredAt: isValidDateTime(dto.occurredAt) ? dto.occurredAt : undefined,
    status: 'OPEN',
  }
}

// 무엇을 거르고 무엇을 거르지 않는가
//
//   거른다 — visibility 가 보호자 공개 범위가 아닌 것. 이 한 줄이 PRIVATE 유출을
//   막는 실제 방어선이고, 그래서 백엔드가 건별 visibility 를 보내지 않으면
//   mapDashboard 가 피드 전체를 null 로 처리한다.
//
//   거른다 — URGENT(T1). 같은 알림을 안전 알림 카드와 기록 피드에 두 번 그리면
//   보호자가 두 건이 일어난 줄로 읽는다. T1 은 safetyAlerts 가 담당한다.
//
//   거르지 않는다 — source 와 statusLevel. 예전 조건(ROBOT + INFO)은 로봇이 올린
//   하루 요약 하나만 통과시켰고, 정작 대부분을 차지하는 기억(source "AI",
//   statusLevel "NORMAL")을 전부 떨어뜨렸다. 백엔드가 이미 가시성으로 걸러 보낸
//   것을 프론트가 출처를 이유로 한 번 더 버릴 근거가 없다.
//
//   title / summary 도 백엔드 값을 그대로 쓴다. 고정 문구로 덮으면 "새로 기억한
//   내용"과 "하루 요약"이 화면에서 한 글자도 다르지 않게 보인다 — 안전 알림에서
//   이미 한 번 고친 실수다.
function mapGuardianSafeActivity(
  dto: DashboardActivityDto,
  elderId: string,
): ActivitySummary | null {
  const guardianVisibility =
    dto.visibility === 'SHARED_WITH_PRIMARY' ||
    dto.visibility === 'SHARED_WITH_GUARDIANS'
      ? dto.visibility
      : undefined
  if (!guardianVisibility || dto.statusLevel === 'URGENT') return null
  if (!isValidDateTime(dto.occurredAt)) return null

  const title = dto.title?.trim()
  const summary = dto.summary?.trim()
  return {
    id: dto.id,
    elderId,
    title: title && title.length > 0 ? title : '공유된 돌봄 기록',
    summary: summary && summary.length > 0 ? summary : '',
    occurredAt: dto.occurredAt,
    source: normalizeSource(dto.source),
    statusLevel: 'NORMAL',
    kind: dto.statusLevel === 'INFO' ? 'DAILY_SUMMARY' : 'SHARED_MEMORY',
    visibility: guardianVisibility,
  }
}

function latestObservedAt(values: Array<string | undefined>): string | undefined {
  return values
    .filter((value): value is string => isValidDateTime(value))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0]
}

// 이름이 비어 오면 보호자 정보 자체를 없는 것으로 본다 — 빈 이름표를 띄우느니
// 헤더가 그 자리를 비우는 편이 정직하다.
function mapGuardian(
  dto: DashboardGuardianDto | null | undefined,
): GuardianSummary | undefined {
  const name = dto?.name?.trim()
  if (!dto?.id || !name) return undefined
  return {
    id: dto.id,
    name,
    priority: dto.priority === 'SECONDARY' ? 'SECONDARY' : 'PRIMARY',
  }
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
    guardian: mapGuardian(dto.guardian),
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
    // null 과 [] 를 무엇으로 가르는가
    //   null = "알림이 있는지 확인하지 못했다", [] = "확인했고 없다". 화면이 이 둘을
    //   다르게 그리므로 판정이 곧 문구가 된다.
    //
    // 판정 기준은 recentActivities 가 배열로 왔는지다. 배열이면 서버가 활동 피드를
    // 정상으로 돌려준 것이므로 그 안에 T1 이 없다는 것은 "없음"으로 읽어도 된다.
    // 이전 판정(T1 이 하나도 없으면 무조건 null)은 평상시에도 화면에 "확인하지
    // 못했어요"를 띄워, 정상 상태를 오류처럼 보이게 만들었다.
    //
    // 남아 있는 한계 — 백엔드가 활동을 5건으로 잘라 주므로, 더 최근 활동 5건에
    // 밀려난 오래된 T1 은 보이지 않는다. 방금 도착한 알림을 놓치지는 않는다.
    safetyAlerts: Array.isArray(dto.recentActivities) ? knownT1Alerts : null,
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
