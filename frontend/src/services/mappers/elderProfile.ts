// 서버(GET /v1/elders/profile, ElderProfileDto) → FE ElderProfile 매핑.
// app_user 기반 기본정보만 실데이터. 스키마에 없는 건강정보·생년월일·성별 등은 빈 기본값으로 채우고
// 화면(ElderProfilePage)에서 표시하지 않는다.

import type {
  AppUserStatus,
  ConsentStatus,
  ConversationSettings,
  ElderProfile,
  Gender,
  OnboardingStatus,
} from '../../types/domain'

export interface ElderProfileDto {
  id: string
  userType: string
  name: string
  preferredName?: string | null
  onboardingStatus: string
  timeZone: string
  status: string
  personalizationConsentStatus: string
  healthDataConsentStatus: string
  scheduleConsentStatus: string
  guardianSharingConsentStatus: string
  conversationPreferences?: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

// BE ConsentStatus(NOT_REQUESTED) → FE ConsentStatus(NOT_ASKED). 나머지 값은 동일.
function mapConsent(value: string): ConsentStatus {
  return value === 'NOT_REQUESTED' ? 'NOT_ASKED' : (value as ConsentStatus)
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function mapConversationSettings(
  prefs: Record<string, unknown> | null | undefined,
): ConversationSettings {
  const p = prefs ?? {}
  return {
    schemaVersion: 2,
    responseLength: 'MEDIUM',
    speechRate: (asString(p.speechRate) ?? 'NORMAL') as ConversationSettings['speechRate'],
    speechVolume: (asString(p.volume) ?? 'NORMAL') as ConversationSettings['speechVolume'],
    proactiveSpeechLevel: 'MEDIUM',
    reminiscenceEnabled: false,
    humorLevel: 'LOW',
    healthSuggestionSensitivity: 'BALANCED',
    needsRepeatedExplanation: p.repeatWhenUnclear === true,
    preferredConversationWindows: [],
    defaultReminderLeadMinutes: 10,
    avoidedTopics: [],
  }
}

export function mapElderProfile(dto: ElderProfileDto): ElderProfile {
  const onboardingStatus = dto.onboardingStatus as OnboardingStatus
  return {
    elder: {
      id: dto.id,
      userType: 'ELDER',
      name: dto.name,
      preferredName: dto.preferredName ?? dto.name,
      birthDate: '',
      gender: 'UNKNOWN' as Gender,
      status: dto.status as AppUserStatus,
      onboardingStatus,
      personalizationConsentStatus: mapConsent(dto.personalizationConsentStatus),
      healthDataConsentStatus: mapConsent(dto.healthDataConsentStatus),
      scheduleConsentStatus: mapConsent(dto.scheduleConsentStatus),
      guardianSharingConsentStatus: mapConsent(dto.guardianSharingConsentStatus),
      lastCheckedAt: dto.updatedAt,
      createdAt: dto.createdAt,
      updatedAt: dto.updatedAt,
    },
    healthProfile: {
      conditions: [],
      allergies: [],
      physicalLimitations: [],
      observations: [],
    },
    personalPreferences: [],
    importantPeople: [],
    conversationSettings: mapConversationSettings(dto.conversationPreferences),
    surveyStatus: {
      source: 'GUARDIAN_WEB',
      status: onboardingStatus,
      completedQuestionCount: 0,
      totalQuestionCount: 0,
    },
    updatedAt: dto.updatedAt,
  }
}
