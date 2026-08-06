export const USER_TYPES = ["ELDER", "GUARDIAN", "ADMIN"] as const;
export type UserType = (typeof USER_TYPES)[number];

export const GENDERS = ["FEMALE", "MALE", "OTHER", "UNKNOWN"] as const;
export type Gender = (typeof GENDERS)[number];

export const APP_USER_STATUSES = ["ACTIVE", "SUSPENDED", "WITHDRAWN"] as const;
export type AppUserStatus = (typeof APP_USER_STATUSES)[number];

export const ONBOARDING_STATUSES = [
  "NOT_STARTED",
  "IN_PROGRESS",
  "COMPLETED",
  "DECLINED",
] as const;
export type OnboardingStatus = (typeof ONBOARDING_STATUSES)[number];

export const CONSENT_STATUSES = [
  "NOT_ASKED",
  "GRANTED",
  "DENIED",
  "REVOKED",
] as const;
export type ConsentStatus = (typeof CONSENT_STATUSES)[number];

export const INFORMATION_SOURCES = [
  "USER",
  "GUARDIAN",
  "ROBOT",
  "AI",
  "SYSTEM",
] as const;
export type InformationSource = (typeof INFORMATION_SOURCES)[number];

export const STATUS_LEVELS = [
  "NORMAL",
  "ATTENTION",
  "DANGER",
  "OFFLINE",
  "UNKNOWN",
] as const;
export type StatusLevel = (typeof STATUS_LEVELS)[number];

export const MEMORY_TYPES = [
  "PERSONAL_RELATIONSHIP",
  "PREFERENCE",
  "HOBBY",
  "DAILY_ROUTINE",
  "LIFE_EVENT",
  "FAMILY_MEMORY",
  "EMOTIONAL_EVENT",
  "CONVERSATION_SUMMARY",
  "OTHER",
] as const;
export type MemoryType = (typeof MEMORY_TYPES)[number];

export const MEMORY_VERIFICATION_STATUSES = [
  "UNVERIFIED",
  "AUTO_ACCEPTED",
  "USER_CONFIRMED",
  "GUARDIAN_CONFIRMED",
  "REJECTED",
] as const;
export type MemoryVerificationStatus =
  (typeof MEMORY_VERIFICATION_STATUSES)[number];

export const MEMORY_LIFECYCLE_STATUSES = [
  "ACTIVE",
  "DISPUTED",
  "SUPERSEDED",
  "EXPIRED",
  "DELETED",
] as const;
export type MemoryLifecycleStatus =
  (typeof MEMORY_LIFECYCLE_STATUSES)[number];

export const MEMORY_VISIBILITIES = [
  "PRIVATE",
  "SHARED_WITH_PRIMARY",
  "SHARED_WITH_GUARDIANS",
] as const;
export type MemoryVisibility = (typeof MEMORY_VISIBILITIES)[number];

export const CARE_RECORD_TYPES = [
  "HEALTH_CONDITION",
  "ALLERGY",
  "PHYSICAL_LIMITATION",
  "MEDICATION",
  "MEDICATION_SCHEDULE",
  "MEDICATION_REMINDER",
  "MEDICATION_TAKEN",
  "APPOINTMENT",
  "PERSONAL_SCHEDULE",
  "HEALTH_OBSERVATION",
  "REST_OBSERVATION",
  "ENVIRONMENT_OBSERVATION",
  "COGNITIVE_ASSESSMENT",
  "GUARDIAN_NOTIFICATION",
] as const;
export type CareRecordType = (typeof CARE_RECORD_TYPES)[number];

export type CareRecordSourceType = InformationSource;

export const CARE_RECORD_VERIFICATION_STATUSES = [
  "UNVERIFIED",
  "USER_CONFIRMED",
  "GUARDIAN_CONFIRMED",
  "DOCUMENT_VERIFIED",
  "REJECTED",
] as const;
export type CareRecordVerificationStatus =
  (typeof CARE_RECORD_VERIFICATION_STATUSES)[number];

export const ROBOT_REGISTRATION_STATUSES = [
  "REGISTERED",
  "ACTIVE",
  "MAINTENANCE",
  "RETIRED",
] as const;
export type RobotRegistrationStatus =
  (typeof ROBOT_REGISTRATION_STATUSES)[number];

export const ROBOT_MODES = [
  "IDLE",
  "SCENARIO_ACTIVE",
  "REST_GUARD",
  "SAFE_STOP",
  "HOMECOMING",
] as const;
export type RobotMode = (typeof ROBOT_MODES)[number];

export type RobotConnectionStatus = "ONLINE" | "OFFLINE";
export type SensorConnectionStatus = "CONNECTED" | "DISCONNECTED";

export interface ConversationWindow {
  id: string;
  daysOfWeek: number[];
  startTime: string;
  endTime: string;
  label: string;
}

/**
 * app_user.conversation_preferences JSONB v2.
 * API에서는 snake_case로 직렬화되더라도 프론트엔드 내부에서는 camelCase를 사용한다.
 */
export interface ConversationSettings {
  schemaVersion: 2;
  responseLength: "SHORT" | "MEDIUM" | "LONG";
  speechRate: "SLOW" | "NORMAL" | "FAST";
  speechVolume: "QUIET" | "NORMAL" | "LOUD";
  proactiveSpeechLevel: "LOW" | "MEDIUM" | "HIGH";
  reminiscenceEnabled: boolean;
  humorLevel: "NONE" | "LOW" | "MEDIUM" | "HIGH";
  healthSuggestionSensitivity: "CAUTIOUS" | "BALANCED" | "PROACTIVE";
  needsRepeatedExplanation: boolean;
  preferredConversationWindows: ConversationWindow[];
  defaultReminderLeadMinutes: number;
  avoidedTopics: string[];
}

export interface Elder {
  id: string;
  userType: Extract<UserType, "ELDER">;
  name: string;
  preferredName: string;
  birthDate: string;
  gender: Gender;
  phone?: string;
  address?: string;
  status: AppUserStatus;
  onboardingStatus: OnboardingStatus;
  onboardingVersion?: string;
  onboardingCompletedAt?: string;
  personalizationConsentStatus: ConsentStatus;
  healthDataConsentStatus: ConsentStatus;
  scheduleConsentStatus: ConsentStatus;
  guardianSharingConsentStatus: ConsentStatus;
  consentPolicyVersion?: string;
  consentUpdatedAt?: string;
  lastCheckedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface HealthCondition {
  id: string;
  recordType: Extract<CareRecordType, "HEALTH_CONDITION">;
  name: string;
  diagnosedAt?: string;
  note?: string;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
  recordedAt: string;
}

export interface Allergy {
  id: string;
  recordType: Extract<CareRecordType, "ALLERGY">;
  allergen: string;
  reaction?: string;
  severity: "MILD" | "MODERATE" | "SEVERE" | "UNKNOWN";
  note?: string;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
  recordedAt: string;
}

export interface PhysicalLimitation {
  id: string;
  recordType: Extract<CareRecordType, "PHYSICAL_LIMITATION">;
  bodyArea: string;
  description: string;
  severity: "MILD" | "MODERATE" | "SEVERE";
  firstObservedAt?: string;
  lastObservedAt?: string;
  note?: string;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
}

export interface HealthObservation {
  id: string;
  recordType: Extract<CareRecordType, "HEALTH_OBSERVATION">;
  title: string;
  description: string;
  observedAt: string;
  statusLevel: StatusLevel;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
}

export interface HealthProfile {
  conditions: HealthCondition[];
  allergies: Allergy[];
  physicalLimitations: PhysicalLimitation[];
  observations: HealthObservation[];
  recentHospitalVisitAt?: string;
  primaryHospital?: string;
  generalNote?: string;
}

export interface MemoryMetadata {
  source: InformationSource;
  sourceConversationId?: string;
  sourceMessageId?: string;
  confidence?: number;
  verificationStatus: MemoryVerificationStatus;
  lifecycleStatus: MemoryLifecycleStatus;
  visibility: MemoryVisibility;
  lastConfirmedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationPreference extends MemoryMetadata {
  id: string;
  elderId: string;
  memoryType: MemoryType;
  title: string;
  content: string;
  keywords: string[];
  isEnabled: boolean;
}

export interface PersonalPreference extends MemoryMetadata {
  id: string;
  elderId: string;
  memoryType: Extract<MemoryType, "PREFERENCE" | "HOBBY" | "DAILY_ROUTINE">;
  title: string;
  detail: string;
  keywords: string[];
}

export interface ImportantPerson extends MemoryMetadata {
  id: string;
  elderId: string;
  memoryType: Extract<MemoryType, "PERSONAL_RELATIONSHIP">;
  name: string;
  relationship: string;
  preferredReference: string;
  note?: string;
  lastInteractionAt?: string;
}

export interface OnboardingSurveyStatus {
  source: "ROBOT" | "GUARDIAN_WEB";
  status: OnboardingStatus;
  completedQuestionCount: number;
  totalQuestionCount: number;
  lastUpdatedAt?: string;
}

export interface ElderProfile {
  elder: Elder;
  healthProfile: HealthProfile;
  personalPreferences: PersonalPreference[];
  importantPeople: ImportantPerson[];
  conversationSettings: ConversationSettings;
  surveyStatus: OnboardingSurveyStatus;
  updatedAt: string;
}

export const MEDICATION_STATUSES = [
  "ACTIVE",
  "PAUSED",
  "ENDED",
  "UNKNOWN",
] as const;
export type MedicationStatus = (typeof MEDICATION_STATUSES)[number];

export const RECURRENCE_TYPES = ["DAILY", "WEEKLY"] as const;
export type RecurrenceType = (typeof RECURRENCE_TYPES)[number];

export interface MedicationSchedule {
  id: string;
  recordType: Extract<CareRecordType, "MEDICATION_SCHEDULE">;
  medicationId: string;
  recurrence: RecurrenceType;
  timeZone: string;
  localTimes: string[];
  daysOfWeek?: number[];
  startsOn: string;
  endsOn?: string;
  reminderLeadMinutes: number;
  isActive: boolean;
}

export interface Medication {
  id: string;
  elderId: string;
  recordType: Extract<CareRecordType, "MEDICATION">;
  name: string;
  dosage: string;
  purpose?: string;
  instructions?: string;
  activeIngredient?: string;
  startedOn?: string;
  endedOn?: string;
  status: MedicationStatus;
  schedules: MedicationSchedule[];
  reminderEnabled: boolean;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
  createdAt: string;
  updatedAt: string;
}

export interface CreateMedicationInput {
  name: string;
  dosage: string;
  purpose?: string;
  instructions?: string;
  activeIngredient?: string;
  localTime: string;
  reminderEnabled?: boolean;
  reminderLeadMinutes?: number;
}

export type UpdateMedicationInput = Partial<
  Pick<
    Medication,
    | "name"
    | "dosage"
    | "purpose"
    | "instructions"
    | "activeIngredient"
    | "reminderEnabled"
    | "verificationStatus"
  >
> & {
  localTime?: string;
};

export const MEDICATION_RESPONSE_STATUSES = [
  "CONFIRMED",
  "NO_RESPONSE",
  "UPCOMING",
  "MISSED",
  "DECLINED",
  "UNKNOWN",
] as const;
export type MedicationResponseStatus =
  (typeof MEDICATION_RESPONSE_STATUSES)[number];

export interface MedicationResponse {
  id: string;
  medicationId: string;
  medicationScheduleId: string;
  scheduledAt: string;
  respondedAt?: string;
  status: MedicationResponseStatus;
}

export const SCHEDULE_TYPES = ["APPOINTMENT", "PERSONAL_SCHEDULE"] as const;
export type ScheduleType = (typeof SCHEDULE_TYPES)[number];

export const SCHEDULE_STATUSES = [
  "UPCOMING",
  "COMPLETED",
  "CANCELLED",
  "UNKNOWN",
] as const;
export type ScheduleStatus = (typeof SCHEDULE_STATUSES)[number];

export interface Schedule {
  id: string;
  elderId: string;
  recordType: ScheduleType;
  title: string;
  description?: string;
  startsAt: string;
  endsAt?: string;
  location?: string;
  relatedPersonName?: string;
  status: ScheduleStatus;
  reminderEnabled: boolean;
  reminderLeadMinutes: number;
  followUpEnabled: boolean;
  followUpQuestion?: string;
  sourceType: CareRecordSourceType;
  verificationStatus: CareRecordVerificationStatus;
  createdAt: string;
  updatedAt: string;
}

export const CONFIRMATION_KINDS = [
  "INTEREST",
  "SCHEDULE",
  "HEALTH",
  "MEDICATION_CONFLICT",
] as const;
export type ConfirmationKind = (typeof CONFIRMATION_KINDS)[number];

export const CONFIRMATION_REQUEST_STATUSES = [
  "PENDING",
  "CONFIRMED",
  "EDITED",
  "REJECTED",
  "REASK_REQUESTED",
  "EXPIRED",
] as const;
export type ConfirmationRequestStatus =
  (typeof CONFIRMATION_REQUEST_STATUSES)[number];

export type ConfirmationResolution = "CONFIRM" | "EDIT" | "REJECT" | "REASK";

export const RISK_LEVELS = ["NORMAL", "SENSITIVE", "HIGH"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export const COORDINATION_STATUSES = [
  "NOT_REQUIRED",
  "COORDINATION_REQUIRED",
  "WAITING_PRIMARY_GUARDIAN",
  "WAITING_SENIOR",
  "AGREED",
  "DISAGREED",
  "SENIOR_UNREACHABLE",
  "GUARDIAN_OVERRIDE_CONFIRMED",
  "COMPLETED",
] as const;
export type CoordinationStatus = (typeof COORDINATION_STATUSES)[number];

export type StructuredValue =
  | string
  | number
  | boolean
  | null
  | StructuredValue[]
  | { [key: string]: StructuredValue };

export interface ConfirmationRequest {
  id: string;
  elderId: string;
  kind: ConfirmationKind;
  title: string;
  summary: string;
  question: string;
  evidence: string;
  currentValue?: StructuredValue;
  proposedValue: StructuredValue;
  status: ConfirmationRequestStatus;
  riskLevel: RiskLevel;
  coordinationStatus: CoordinationStatus;
  source: InformationSource;
  sourceConversationId?: string;
  sourceMessageId?: string;
  createdAt: string;
  resolvedAt?: string;
  resolutionNote?: string;
  previousStatus?: ConfirmationRequestStatus;
  previousProposedValue?: StructuredValue;
  appliedEntityId?: string;
  canResolve?: boolean;
  canRequestRecheck?: boolean;
  waitingReason?: "CLARIFICATION" | "COORDINATION" | "CAPTURED" | "EXPIRED";
}

export interface ActivitySummary {
  id: string;
  elderId: string;
  title: string;
  summary: string;
  occurredAt: string;
  source: InformationSource;
  statusLevel: StatusLevel;
  kind?: "SHARED_MEMORY" | "CARE_UPDATE" | "DAILY_SUMMARY";
  visibility?: Extract<
    MemoryVisibility,
    "SHARED_WITH_PRIMARY" | "SHARED_WITH_GUARDIANS"
  >;
  relatedMemoryId?: string;
  relatedCareRecordId?: string;
}

export interface SafetyAlert {
  id: string;
  message: string;
  occurredAt?: string;
  status: "OPEN";
}

export interface RobotStatus {
  id: string;
  elderId: string;
  deviceId?: string;
  currentMode?: RobotMode;
  registrationActive: boolean;
  ambientTemperatureC?: number;
  ambientHumidityPercent?: number;
  ambientObservedAt?: string;
}

export interface HomeEnvironmentSummary {
  temperatureC?: number;
  humidityPercent?: number;
  lastObservedAt?: string;
}

export interface MedicationProgress {
  total: number;
  confirmed: number;
  noResponse: number;
  upcoming: number;
  missed: number;
}

export interface HomeDashboardSummary {
  elder: {
    id: string;
    displayName: string;
    lastObservedAt?: string;
  };
  robot: RobotStatus;
  /** null means the alert feed could not be verified; [] means a successful empty result. */
  safetyAlerts: SafetyAlert[] | null;
  homeEnvironment: HomeEnvironmentSummary;
  todaySchedules: Schedule[];
  medications: Medication[];
  medicationResponses: MedicationResponse[];
  medicationProgress: MedicationProgress;
  pendingConfirmationCount: number;
  confirmationRequests: ConfirmationRequest[];
  /** null means the guardian-visible activity contract is unavailable. */
  recentActivities: ActivitySummary[] | null;
  generatedAt: string;
}

export type CreateConversationPreferenceInput = Pick<
  ConversationPreference,
  "elderId" | "memoryType" | "title" | "content" | "keywords" | "visibility"
> & {
  source?: InformationSource;
};

export type UpdateConversationPreferenceInput = Partial<
  Pick<
    ConversationPreference,
    | "memoryType"
    | "title"
    | "content"
    | "keywords"
    | "visibility"
    | "verificationStatus"
  >
>;

export type CreateScheduleInput = Pick<
  Schedule,
  "elderId" | "recordType" | "title" | "startsAt"
> &
  Partial<
    Pick<
      Schedule,
      | "description"
      | "endsAt"
      | "location"
      | "relatedPersonName"
      | "reminderEnabled"
      | "reminderLeadMinutes"
      | "followUpEnabled"
      | "followUpQuestion"
      | "sourceType"
      | "verificationStatus"
    >
  >;

export type UpdateScheduleInput = Partial<
  Pick<
    Schedule,
    | "recordType"
    | "title"
    | "description"
    | "startsAt"
    | "endsAt"
    | "location"
    | "relatedPersonName"
    | "status"
    | "reminderEnabled"
    | "reminderLeadMinutes"
    | "followUpEnabled"
    | "followUpQuestion"
    | "verificationStatus"
  >
>;
