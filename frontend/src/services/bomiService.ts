import {
  mockActivities,
  mockConfirmationRequests,
  mockConversationPreferences,
  mockDashboardSummary,
  mockElderProfile,
  mockMedicationResponses,
  mockMedications,
  mockRobotStatus,
  mockSchedules,
} from "../mocks/data";
import { httpGet, httpPost, httpPut, httpDelete } from "./http";
import { mapDashboard, type DashboardDto } from "./mappers/dashboard";
import {
  mapFactCandidate,
  type FactCandidateDto,
} from "./mappers/confirmationRequest";
import { mapSchedule, type ScheduleDto } from "./mappers/schedule";
import {
  mapMedication,
  mapMedicationResponse,
  type MedicationDto,
  type MedicationResponseDto,
} from "./mappers/medication";
import {
  isGuardianVisibleMemory,
  mapMemory,
  type MemoryDto,
} from "./mappers/memory";
import {
  mapElderProfile,
  type ElderProfileDto,
} from "./mappers/elderProfile";
import type {
  ActivitySummary,
  ConfirmationRequest,
  ConfirmationResolution,
  ConversationPreference,
  CreateConversationPreferenceInput,
  CreateMedicationInput,
  CreateScheduleInput,
  ElderProfile,
  HomeDashboardSummary,
  Medication,
  MedicationResponse,
  PersonalPreference,
  RobotStatus,
  Schedule,
  StructuredValue,
  UpdateConversationPreferenceInput,
  UpdateMedicationInput,
  UpdateScheduleInput,
} from "../types/domain";
import { toDateInputValue } from "../utils/date";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (
  configuredApiBaseUrl && configuredApiBaseUrl.length > 0
    ? configuredApiBaseUrl
    : "/api"
).replace(/\/+$/, "");

export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== "false";
export const GUARDIAN_API_AUTH_READY =
  import.meta.env.VITE_GUARDIAN_API_AUTH_READY === "true";

export const API_ENDPOINTS = {
  dashboard: `${API_BASE_URL}/v1/guardian/dashboard`,
  elderProfile: `${API_BASE_URL}/v1/elders/profile`,
  conversationPreferences: `${API_BASE_URL}/v1/memories`,
  confirmationRequests: `${API_BASE_URL}/v1/confirmation-requests`,
  medications: `${API_BASE_URL}/v1/care-records/medications`,
  medicationResponses: `${API_BASE_URL}/v1/care-records/medication-responses`,
  schedules: `${API_BASE_URL}/v1/care-records/schedules`,
} as const;

const MOCK_LATENCY_MS = 180;

const clone = <T>(value: T): T => structuredClone(value);

const createId = (prefix: string): string => {
  const randomPart =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${randomPart}`;
};

const nowIso = (): string => new Date().toISOString();

type MockScenario =
  | "default"
  | "urgent"
  | "alert-error"
  | "empty"
  | "unknown"
  | "stale"
  | "error";

const readMockScenario = (): MockScenario => {
  if (typeof window === "undefined") return "default";
  const value = new URLSearchParams(window.location.search).get("demoState");
  return value === "urgent" ||
    value === "alert-error" ||
    value === "empty" ||
    value === "unknown" ||
    value === "stale" ||
    value === "error"
    ? value
    : "default";
};

const withLatency = <T>(factory: () => T): Promise<T> =>
  new Promise<T>((resolve, reject) => {
    window.setTimeout(() => {
      try {
        resolve(clone(factory()));
      } catch (error: unknown) {
        reject(error);
      }
    }, MOCK_LATENCY_MS);
  });

const requireEntity = <T>(
  items: T[],
  predicate: (item: T) => boolean,
  entityLabel: string,
): T => {
  const entity = items.find(predicate);
  if (!entity) {
    throw new Error(`${entityLabel} 정보를 찾을 수 없습니다.`);
  }
  return entity;
};

const mapResolutionToStatus = (
  resolution: ConfirmationResolution,
): ConfirmationRequest["status"] => {
  switch (resolution) {
    case "CONFIRM":
      return "CONFIRMED";
    case "EDIT":
      return "EDITED";
    case "REJECT":
      return "REJECTED";
    case "REASK":
      return "REASK_REQUESTED";
  }
};

const isStructuredObject = (
  value: StructuredValue,
): value is { [key: string]: StructuredValue } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const readStructuredString = (
  value: { [key: string]: StructuredValue },
  key: string,
): string | undefined => {
  const candidate = value[key];
  return typeof candidate === "string" ? candidate : undefined;
};

const readStructuredStrings = (
  value: { [key: string]: StructuredValue },
  key: string,
): string[] => {
  const candidate = value[key];
  return Array.isArray(candidate)
    ? candidate.filter((item): item is string => typeof item === "string")
    : [];
};

const isProfilePreferenceType = (
  memoryType: ConversationPreference["memoryType"],
): memoryType is "PREFERENCE" | "HOBBY" | "DAILY_ROUTINE" =>
  memoryType === "PREFERENCE" ||
  memoryType === "HOBBY" ||
  memoryType === "DAILY_ROUTINE";

const isGuardianVisibleActivity = (activity: ActivitySummary): boolean =>
  activity.visibility === "SHARED_WITH_PRIMARY" ||
  activity.visibility === "SHARED_WITH_GUARDIANS";

export type BomiDataKey =
  | "dashboard"
  | "elderProfile"
  | "conversationPreferences"
  | "confirmationRequests"
  | "medications"
  | "medicationResponses"
  | "schedules";

export interface BomiInitialData {
  dashboard: HomeDashboardSummary | null;
  elderProfile: ElderProfile | null;
  conversationPreferences: ConversationPreference[];
  confirmationRequests: ConfirmationRequest[];
  medications: Medication[];
  medicationResponses: MedicationResponse[];
  schedules: Schedule[];
  robotStatus: RobotStatus;
  activities: ActivitySummary[];
  errors?: Partial<Record<BomiDataKey, string>>;
}

export interface BomiService {
  getInitialData(): Promise<BomiInitialData>;
  getDashboard(): Promise<HomeDashboardSummary>;
  getElderProfile(): Promise<ElderProfile>;
  saveElderProfile(profile: ElderProfile): Promise<ElderProfile>;
  getConversationPreferences(): Promise<ConversationPreference[]>;
  createConversationPreference(
    input: CreateConversationPreferenceInput,
  ): Promise<ConversationPreference>;
  updateConversationPreference(
    id: string,
    input: UpdateConversationPreferenceInput,
  ): Promise<ConversationPreference>;
  deleteConversationPreference(id: string): Promise<string>;
  toggleConversationPreference(id: string): Promise<ConversationPreference>;
  getConfirmationRequests(): Promise<ConfirmationRequest[]>;
  resolveConfirmationRequest(
    id: string,
    resolution: ConfirmationResolution,
    options?: {
      editedValue?: StructuredValue;
      note?: string;
    },
  ): Promise<ConfirmationRequest>;
  undoConfirmationResolution(id: string): Promise<ConfirmationRequest>;
  getMedications(): Promise<Medication[]>;
  getMedicationResponses(): Promise<MedicationResponse[]>;
  createMedication(input: CreateMedicationInput): Promise<Medication>;
  updateMedication(
    id: string,
    input: UpdateMedicationInput,
  ): Promise<Medication>;
  toggleMedicationStatus(id: string): Promise<Medication>;
  deleteMedication(id: string): Promise<string>;
  toggleMedicationReminder(id: string): Promise<Medication>;
  getSchedules(): Promise<Schedule[]>;
  createSchedule(input: CreateScheduleInput): Promise<Schedule>;
  updateSchedule(id: string, input: UpdateScheduleInput): Promise<Schedule>;
  resetMockData(): Promise<BomiInitialData>;
}

class MockBomiService implements BomiService {
  private elderProfile = clone(mockElderProfile);
  private conversationPreferences = clone(mockConversationPreferences);
  private confirmationRequests = clone(mockConfirmationRequests);
  private medications = clone(mockMedications);
  private medicationResponses = clone(mockMedicationResponses);
  private schedules = clone(mockSchedules);
  private robotStatus = clone(mockRobotStatus);
  private activities = clone(mockActivities);

  private syncProfilePreferencesFromMemories(): void {
    const personalPreferences: PersonalPreference[] =
      this.conversationPreferences
        .filter(
          (preference) =>
            isGuardianVisibleMemory(preference) &&
            isProfilePreferenceType(preference.memoryType) &&
            preference.lifecycleStatus !== "DELETED",
        )
        .map((preference) => ({
          id: preference.id,
          elderId: preference.elderId,
          memoryType: preference.memoryType as
            | "PREFERENCE"
            | "HOBBY"
            | "DAILY_ROUTINE",
          title: preference.title,
          detail: preference.content,
          keywords: clone(preference.keywords),
          source: preference.source,
          sourceConversationId: preference.sourceConversationId,
          sourceMessageId: preference.sourceMessageId,
          confidence: preference.confidence,
          verificationStatus: preference.verificationStatus,
          lifecycleStatus: preference.lifecycleStatus,
          visibility: preference.visibility,
          lastConfirmedAt: preference.lastConfirmedAt,
          createdAt: preference.createdAt,
          updatedAt: preference.updatedAt,
        }));

    this.elderProfile = {
      ...this.elderProfile,
      personalPreferences,
    };
  }

  private syncMemoriesFromProfile(profile: ElderProfile): void {
    const timestamp = nowIso();
    profile.personalPreferences.forEach((preference) => {
      const existing = this.conversationPreferences.find(
        (memory) => memory.id === preference.id,
      );
      const synchronized: ConversationPreference = {
        id: preference.id,
        elderId: preference.elderId,
        memoryType: preference.memoryType,
        title: preference.title.trim(),
        content: preference.detail.trim(),
        keywords: clone(preference.keywords),
        source: preference.source,
        sourceConversationId: preference.sourceConversationId,
        sourceMessageId: preference.sourceMessageId,
        confidence: preference.confidence ?? existing?.confidence ?? 1,
        verificationStatus: preference.verificationStatus,
        lifecycleStatus: preference.lifecycleStatus,
        visibility: preference.visibility,
        isEnabled: existing?.isEnabled ?? true,
        lastConfirmedAt: preference.lastConfirmedAt,
        createdAt: existing?.createdAt ?? preference.createdAt ?? timestamp,
        updatedAt: timestamp,
      };
      this.conversationPreferences = existing
        ? this.conversationPreferences.map((memory) =>
            memory.id === preference.id ? synchronized : memory,
          )
        : [synchronized, ...this.conversationPreferences];
    });

    profile.importantPeople.forEach((person) => {
      const existing = this.conversationPreferences.find(
        (memory) => memory.id === person.id,
      );
      const synchronized: ConversationPreference = {
        id: person.id,
        elderId: person.elderId,
        memoryType: "PERSONAL_RELATIONSHIP",
        title: `${person.relationship} ${person.name}`.trim(),
        content:
          person.note?.trim() ||
          `${person.name} 님을 ${person.preferredReference}(으)로 부릅니다.`,
        keywords: Array.from(
          new Set([person.name, person.relationship, person.preferredReference]),
        ),
        source: person.source,
        sourceConversationId: person.sourceConversationId,
        sourceMessageId: person.sourceMessageId,
        confidence: person.confidence ?? existing?.confidence ?? 1,
        verificationStatus: person.verificationStatus,
        lifecycleStatus: person.lifecycleStatus,
        visibility: person.visibility,
        isEnabled: existing?.isEnabled ?? true,
        lastConfirmedAt: person.lastConfirmedAt,
        createdAt: existing?.createdAt ?? person.createdAt ?? timestamp,
        updatedAt: timestamp,
      };
      this.conversationPreferences = existing
        ? this.conversationPreferences.map((memory) =>
            memory.id === person.id ? synchronized : memory,
          )
        : [synchronized, ...this.conversationPreferences];
    });
  }

  private applyConfirmedValue(
    request: ConfirmationRequest,
    value: StructuredValue,
  ): string | undefined {
    if (!isStructuredObject(value)) {
      return undefined;
    }
    const timestamp = nowIso();

    if (request.kind === "INTEREST") {
      const memoryType = readStructuredString(value, "memoryType");
      const validMemoryType =
        memoryType === "PREFERENCE" ||
        memoryType === "HOBBY" ||
        memoryType === "DAILY_ROUTINE"
          ? memoryType
          : "PREFERENCE";
      const proposedTitle =
        readStructuredString(value, "title") ?? request.title;
      const proposedKeywords = readStructuredStrings(value, "keywords");
      const alreadyStored = this.conversationPreferences.some(
        (preference) =>
          preference.lifecycleStatus !== "DELETED" &&
          preference.memoryType === validMemoryType &&
          (preference.title.trim() === proposedTitle.trim() ||
            proposedKeywords.some((keyword) =>
              preference.keywords.includes(keyword),
            )),
      );
      if (alreadyStored) {
        return undefined;
      }
      const created: ConversationPreference = {
        id: createId("memory"),
        elderId: request.elderId,
        memoryType: validMemoryType,
        title: proposedTitle,
        content:
          readStructuredString(value, "content") ??
          request.summary,
        keywords: proposedKeywords,
        source: "AI",
        sourceConversationId: request.sourceConversationId,
        sourceMessageId: request.sourceMessageId,
        confidence: 1,
        verificationStatus: "GUARDIAN_CONFIRMED",
        lifecycleStatus: "ACTIVE",
        visibility: "SHARED_WITH_GUARDIANS",
        isEnabled: true,
        lastConfirmedAt: timestamp,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      this.conversationPreferences = [created, ...this.conversationPreferences];
      this.syncProfilePreferencesFromMemories();
      return created.id;
    }

    if (request.kind === "SCHEDULE") {
      const startsAt = readStructuredString(value, "startsAt");
      if (!startsAt) {
        throw new Error("일정 시작 시간이 없어 확정할 수 없습니다.");
      }
      const title = readStructuredString(value, "title") ?? request.title;
      const alreadyStored = this.schedules.some(
        (schedule) =>
          schedule.startsAt === startsAt &&
          schedule.title.trim() === title.trim() &&
          schedule.status !== "CANCELLED",
      );
      if (alreadyStored) {
        return undefined;
      }
      const created: Schedule = {
        id: createId("schedule"),
        elderId: request.elderId,
        recordType:
          readStructuredString(value, "recordType") === "PERSONAL_SCHEDULE"
            ? "PERSONAL_SCHEDULE"
            : "APPOINTMENT",
        title,
        description: request.summary,
        startsAt,
        location: readStructuredString(value, "location"),
        relatedPersonName: readStructuredString(value, "relatedPersonName"),
        status: "UPCOMING",
        reminderEnabled: true,
        reminderLeadMinutes: 60,
        followUpEnabled: true,
        followUpQuestion: "일정은 잘 다녀오셨어요? 기분은 어떠셨어요?",
        sourceType: "AI",
        verificationStatus: "GUARDIAN_CONFIRMED",
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      this.schedules = [...this.schedules, created].sort((left, right) =>
        left.startsAt.localeCompare(right.startsAt),
      );
      return created.id;
    }

    if (request.kind === "HEALTH") {
      const observationId = createId("health-observation");
      const proposedStatus = readStructuredString(value, "statusLevel");
      const statusLevel =
        proposedStatus === "NORMAL" ||
        proposedStatus === "ATTENTION" ||
        proposedStatus === "DANGER" ||
        proposedStatus === "OFFLINE"
          ? proposedStatus
          : "ATTENTION";
      this.elderProfile = {
        ...this.elderProfile,
        healthProfile: {
          ...this.elderProfile.healthProfile,
          observations: [
            {
              id: observationId,
              recordType: "HEALTH_OBSERVATION",
              title: readStructuredString(value, "title") ?? request.title,
              description:
                readStructuredString(value, "description") ?? request.summary,
              observedAt: timestamp,
              statusLevel,
              sourceType: "AI",
              verificationStatus: "GUARDIAN_CONFIRMED",
            },
            ...this.elderProfile.healthProfile.observations,
          ],
        },
        updatedAt: timestamp,
      };
      return observationId;
    }

    // 복약 충돌은 보호자의 확인 결과만 남기고 기존 복약값을 자동 변경하지 않는다.
    return undefined;
  }

  private removeAppliedConfirmationEntity(
    request: ConfirmationRequest,
  ): void {
    if (!request.appliedEntityId) {
      return;
    }
    if (request.kind === "INTEREST") {
      this.conversationPreferences = this.conversationPreferences.filter(
        (preference) => preference.id !== request.appliedEntityId,
      );
      this.syncProfilePreferencesFromMemories();
    } else if (request.kind === "SCHEDULE") {
      this.schedules = this.schedules.filter(
        (schedule) => schedule.id !== request.appliedEntityId,
      );
    } else if (request.kind === "HEALTH") {
      this.elderProfile = {
        ...this.elderProfile,
        healthProfile: {
          ...this.elderProfile.healthProfile,
          observations: this.elderProfile.healthProfile.observations.filter(
            (observation) => observation.id !== request.appliedEntityId,
          ),
        },
      };
    }
  }

  private buildDashboard(): HomeDashboardSummary {
    const scenario = readMockScenario();
    if (scenario === "error") {
      throw new Error("예시 오류 상태입니다. 정보를 다시 확인해 주세요.");
    }
    const pendingRequests = this.confirmationRequests.filter(
      (request) => request.status === "PENDING",
    );
    const todayKey = toDateInputValue(new Date());
    const todayMedicationResponses = this.medicationResponses.filter(
      (response) => toDateInputValue(response.scheduledAt) === todayKey,
    );
    const progress = todayMedicationResponses.reduce(
      (current, response) => {
        if (response.status === "CONFIRMED") {
          current.confirmed += 1;
        } else if (response.status === "NO_RESPONSE") {
          current.noResponse += 1;
        } else if (response.status === "UPCOMING") {
          current.upcoming += 1;
        } else if (response.status === "MISSED") {
          current.missed += 1;
        }
        return current;
      },
      {
        total: todayMedicationResponses.length,
        confirmed: 0,
        noResponse: 0,
        upcoming: 0,
        missed: 0,
      },
    );

    const result: HomeDashboardSummary = {
      ...clone(mockDashboardSummary),
      elder: {
        ...clone(mockDashboardSummary.elder),
        id: this.elderProfile.elder.id,
        displayName: this.elderProfile.elder.preferredName,
      },
      robot: clone(this.robotStatus),
      todaySchedules: this.schedules.filter(
        (schedule) => toDateInputValue(schedule.startsAt) === todayKey,
      ),
      medications: clone(
        this.medications.filter((medication) => medication.status !== "ENDED"),
      ),
      medicationResponses: clone(todayMedicationResponses),
      medicationProgress: progress,
      pendingConfirmationCount: pendingRequests.length,
      confirmationRequests: clone(pendingRequests),
      recentActivities: clone(
        this.activities.filter(isGuardianVisibleActivity),
      ),
      generatedAt: nowIso(),
    };

    if (scenario === "urgent") {
      result.safetyAlerts = [
        {
          id: "example-urgent-alert",
          message: "보미의 안전 확인에 응답이 없어 보호자 알림이 도착했어요.",
          occurredAt: "2026-08-06T00:20:00+09:00",
          status: "OPEN",
        },
      ];
    } else if (scenario === "alert-error") {
      result.safetyAlerts = null;
    } else if (scenario === "empty") {
      result.safetyAlerts = [];
      result.todaySchedules = [];
      result.medicationResponses = [];
      result.medicationProgress = {
        total: 0,
        confirmed: 0,
        noResponse: 0,
        upcoming: 0,
        missed: 0,
      };
      result.pendingConfirmationCount = 0;
      result.confirmationRequests = [];
      result.recentActivities = [];
    } else if (scenario === "unknown") {
      result.robot.currentMode = undefined;
      result.homeEnvironment = {};
      result.elder.lastObservedAt = undefined;
    } else if (scenario === "stale") {
      const staleAt = "2026-07-30T10:33:20+09:00";
      result.elder.lastObservedAt = staleAt;
      result.robot.ambientObservedAt = staleAt;
      result.homeEnvironment.lastObservedAt = staleAt;
    }

    return result;
  }

  getInitialData(): Promise<BomiInitialData> {
    return withLatency(() => {
      this.syncProfilePreferencesFromMemories();
      return {
        dashboard: this.buildDashboard(),
        elderProfile: this.elderProfile,
        conversationPreferences: this.conversationPreferences.filter(
          isGuardianVisibleMemory,
        ),
        confirmationRequests: this.confirmationRequests,
        medications: this.medications.filter(
          (medication) => medication.status !== "ENDED",
        ),
        medicationResponses: this.medicationResponses.filter(
          (response) =>
            toDateInputValue(response.scheduledAt) ===
            toDateInputValue(new Date()),
        ),
        schedules: this.schedules,
        robotStatus: this.robotStatus,
        activities: this.activities.filter(isGuardianVisibleActivity),
      };
    });
  }

  getDashboard(): Promise<HomeDashboardSummary> {
    return withLatency(() => this.buildDashboard());
  }

  getElderProfile(): Promise<ElderProfile> {
    return withLatency(() => {
      this.syncProfilePreferencesFromMemories();
      return this.elderProfile;
    });
  }

  saveElderProfile(profile: ElderProfile): Promise<ElderProfile> {
    return withLatency(() => {
      const updatedAt = nowIso();
      this.elderProfile = {
        ...clone(profile),
        elder: {
          ...clone(profile.elder),
          updatedAt,
        },
        updatedAt,
      };
      this.syncMemoriesFromProfile(this.elderProfile);
      this.syncProfilePreferencesFromMemories();
      return this.elderProfile;
    });
  }

  getConversationPreferences(): Promise<ConversationPreference[]> {
    return withLatency(() =>
      this.conversationPreferences.filter(isGuardianVisibleMemory),
    );
  }

  createConversationPreference(
    input: CreateConversationPreferenceInput,
  ): Promise<ConversationPreference> {
    return withLatency(() => {
      const timestamp = nowIso();
      const created: ConversationPreference = {
        id: createId("memory"),
        elderId: input.elderId,
        memoryType: input.memoryType,
        title: input.title.trim(),
        content: input.content.trim(),
        keywords: input.keywords.map((keyword) => keyword.trim()).filter(Boolean),
        source: input.source ?? "GUARDIAN",
        confidence: 1,
        verificationStatus: "GUARDIAN_CONFIRMED",
        lifecycleStatus: "ACTIVE",
        visibility: input.visibility,
        isEnabled: true,
        lastConfirmedAt: timestamp,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      this.conversationPreferences = [
        created,
        ...this.conversationPreferences,
      ];
      this.syncProfilePreferencesFromMemories();
      return created;
    });
  }

  updateConversationPreference(
    id: string,
    input: UpdateConversationPreferenceInput,
  ): Promise<ConversationPreference> {
    return withLatency(() => {
      const existing = requireEntity(
        this.conversationPreferences,
        (preference) => preference.id === id,
        "대화 정보",
      );
      const updated: ConversationPreference = {
        ...existing,
        ...clone(input),
        title: input.title?.trim() ?? existing.title,
        content: input.content?.trim() ?? existing.content,
        keywords:
          input.keywords
            ?.map((keyword) => keyword.trim())
            .filter((keyword) => keyword.length > 0) ?? existing.keywords,
        updatedAt: nowIso(),
      };
      this.conversationPreferences = this.conversationPreferences.map(
        (preference) => (preference.id === id ? updated : preference),
      );
      this.syncProfilePreferencesFromMemories();
      return updated;
    });
  }

  deleteConversationPreference(id: string): Promise<string> {
    return withLatency(() => {
      const existing = requireEntity(
        this.conversationPreferences,
        (preference) => preference.id === id,
        "대화 정보",
      );
      const deleted: ConversationPreference = {
        ...existing,
        isEnabled: false,
        lifecycleStatus: "DELETED",
        updatedAt: nowIso(),
      };
      this.conversationPreferences = this.conversationPreferences.map(
        (preference) => (preference.id === id ? deleted : preference),
      );
      if (existing.memoryType === "PERSONAL_RELATIONSHIP") {
        this.elderProfile = {
          ...this.elderProfile,
          importantPeople: this.elderProfile.importantPeople.filter(
            (person) => person.id !== id,
          ),
        };
      }
      this.syncProfilePreferencesFromMemories();
      return id;
    });
  }

  toggleConversationPreference(id: string): Promise<ConversationPreference> {
    return withLatency(() => {
      const existing = requireEntity(
        this.conversationPreferences,
        (preference) => preference.id === id,
        "대화 정보",
      );
      const updated: ConversationPreference = {
        ...existing,
        isEnabled: !existing.isEnabled,
        updatedAt: nowIso(),
      };
      this.conversationPreferences = this.conversationPreferences.map(
        (preference) => (preference.id === id ? updated : preference),
      );
      return updated;
    });
  }

  getConfirmationRequests(): Promise<ConfirmationRequest[]> {
    return withLatency(() => this.confirmationRequests);
  }

  resolveConfirmationRequest(
    id: string,
    resolution: ConfirmationResolution,
    options?: {
      editedValue?: StructuredValue;
      note?: string;
    },
  ): Promise<ConfirmationRequest> {
    return withLatency(() => {
      const existing = requireEntity(
        this.confirmationRequests,
        (request) => request.id === id,
        "확인 요청",
      );
      if (existing.status !== "PENDING") {
        throw new Error("이미 처리된 확인 요청입니다.");
      }
      if (resolution === "REASK" && existing.canRequestRecheck === false) {
        throw new Error("현재 상태에서는 다시 확인을 요청할 수 없습니다.");
      }
      if (resolution !== "REASK" && existing.canResolve === false) {
        throw new Error("필요한 확인 절차가 끝나기 전에는 이 정보를 확정할 수 없습니다.");
      }
      const proposedValue =
        resolution === "EDIT" && options?.editedValue !== undefined
          ? clone(options.editedValue)
          : existing.proposedValue;
      const appliedEntityId =
        resolution === "CONFIRM" || resolution === "EDIT"
          ? this.applyConfirmedValue(existing, proposedValue)
          : undefined;
      const updated: ConfirmationRequest = {
        ...existing,
        proposedValue,
        previousProposedValue:
          resolution === "EDIT" ? clone(existing.proposedValue) : undefined,
        appliedEntityId,
        previousStatus: existing.status,
        status: mapResolutionToStatus(resolution),
        resolvedAt: nowIso(),
        resolutionNote: options?.note,
      };
      this.confirmationRequests = this.confirmationRequests.map((request) =>
        request.id === id ? updated : request,
      );
      return updated;
    });
  }

  undoConfirmationResolution(id: string): Promise<ConfirmationRequest> {
    return withLatency(() => {
      const existing = requireEntity(
        this.confirmationRequests,
        (request) => request.id === id,
        "확인 요청",
      );
      if (!existing.previousStatus) {
        throw new Error("되돌릴 확인 요청 처리가 없습니다.");
      }
      this.removeAppliedConfirmationEntity(existing);
      const updated: ConfirmationRequest = {
        ...existing,
        proposedValue:
          existing.previousProposedValue !== undefined
            ? clone(existing.previousProposedValue)
            : existing.proposedValue,
        status: existing.previousStatus,
        previousStatus: undefined,
        previousProposedValue: undefined,
        appliedEntityId: undefined,
        resolvedAt: undefined,
        resolutionNote: undefined,
      };
      this.confirmationRequests = this.confirmationRequests.map((request) =>
        request.id === id ? updated : request,
      );
      return updated;
    });
  }

  getMedications(): Promise<Medication[]> {
    return withLatency(() =>
      this.medications.filter((medication) => medication.status !== "ENDED"),
    );
  }

  getMedicationResponses(): Promise<MedicationResponse[]> {
    return withLatency(() =>
      this.medicationResponses.filter(
        (response) =>
          toDateInputValue(response.scheduledAt) ===
          toDateInputValue(new Date()),
      ),
    );
  }

  createMedication(input: CreateMedicationInput): Promise<Medication> {
    return withLatency(() => {
      const timestamp = nowIso();
      const medicationId = createId("medication");
      const scheduleId = createId("med-schedule");
      const startsOn = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date());
      const created: Medication = {
        id: medicationId,
        elderId: this.elderProfile.elder.id,
        recordType: "MEDICATION",
        name: input.name.trim(),
        dosage: input.dosage.trim(),
        purpose: input.purpose?.trim(),
        instructions: input.instructions?.trim(),
        activeIngredient: input.activeIngredient?.trim(),
        startedOn: startsOn,
        status: "ACTIVE",
        schedules: [
          {
            id: scheduleId,
            recordType: "MEDICATION_SCHEDULE",
            medicationId,
            recurrence: "DAILY",
            timeZone: "Asia/Seoul",
            localTimes: [input.localTime],
            startsOn,
            reminderLeadMinutes: input.reminderLeadMinutes ?? 10,
            isActive: true,
          },
        ],
        reminderEnabled: input.reminderEnabled ?? true,
        sourceType: "GUARDIAN",
        verificationStatus: "GUARDIAN_CONFIRMED",
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      this.medications = [...this.medications, created];
      return created;
    });
  }

  updateMedication(
    id: string,
    input: UpdateMedicationInput,
  ): Promise<Medication> {
    return withLatency(() => {
      const existing = requireEntity(
        this.medications,
        (medication) => medication.id === id,
        "복약",
      );
      const updated: Medication = {
        ...existing,
        name: input.name?.trim() ?? existing.name,
        dosage: input.dosage?.trim() ?? existing.dosage,
        purpose:
          input.purpose === undefined ? existing.purpose : input.purpose.trim(),
        instructions:
          input.instructions === undefined
            ? existing.instructions
            : input.instructions.trim(),
        activeIngredient:
          input.activeIngredient === undefined
            ? existing.activeIngredient
            : input.activeIngredient.trim(),
        reminderEnabled:
          input.reminderEnabled ?? existing.reminderEnabled,
        verificationStatus:
          input.verificationStatus ?? existing.verificationStatus,
        schedules:
          input.localTime === undefined
            ? existing.schedules
            : existing.schedules.map((schedule) => ({
                ...schedule,
                localTimes: [input.localTime as string],
              })),
        updatedAt: nowIso(),
      };
      this.medications = this.medications.map((medication) =>
        medication.id === id ? updated : medication,
      );
      return updated;
    });
  }

  toggleMedicationStatus(id: string): Promise<Medication> {
    return withLatency(() => {
      const existing = requireEntity(
        this.medications,
        (medication) => medication.id === id,
        "복약",
      );
      if (existing.status === "ENDED") {
        throw new Error("종료된 복약 정보는 다시 활성화할 수 없습니다.");
      }
      const isActive = existing.status !== "ACTIVE";
      const updated: Medication = {
        ...existing,
        status: isActive ? "ACTIVE" : "PAUSED",
        schedules: existing.schedules.map((schedule) => ({
          ...schedule,
          isActive,
        })),
        updatedAt: nowIso(),
      };
      this.medications = this.medications.map((medication) =>
        medication.id === id ? updated : medication,
      );
      return updated;
    });
  }

  deleteMedication(id: string): Promise<string> {
    return withLatency(() => {
      const existing = requireEntity(
        this.medications,
        (medication) => medication.id === id,
        "복약",
      );
      const ended: Medication = {
        ...existing,
        status: "ENDED",
        endedOn: toDateInputValue(new Date()),
        reminderEnabled: false,
        schedules: existing.schedules.map((schedule) => ({
          ...schedule,
          isActive: false,
        })),
        updatedAt: nowIso(),
      };
      this.medications = this.medications.map(
        (medication) => (medication.id === id ? ended : medication),
      );
      return id;
    });
  }

  toggleMedicationReminder(id: string): Promise<Medication> {
    return withLatency(() => {
      const existing = requireEntity(
        this.medications,
        (medication) => medication.id === id,
        "복약",
      );
      const updated: Medication = {
        ...existing,
        reminderEnabled: !existing.reminderEnabled,
        updatedAt: nowIso(),
      };
      this.medications = this.medications.map((medication) =>
        medication.id === id ? updated : medication,
      );
      return updated;
    });
  }

  getSchedules(): Promise<Schedule[]> {
    return withLatency(() => this.schedules);
  }

  createSchedule(input: CreateScheduleInput): Promise<Schedule> {
    return withLatency(() => {
      const timestamp = nowIso();
      const created: Schedule = {
        id: createId("schedule"),
        elderId: input.elderId,
        recordType: input.recordType,
        title: input.title.trim(),
        description: input.description?.trim(),
        startsAt: input.startsAt,
        endsAt: input.endsAt,
        location: input.location?.trim(),
        relatedPersonName: input.relatedPersonName?.trim(),
        status: "UPCOMING",
        reminderEnabled: input.reminderEnabled ?? true,
        reminderLeadMinutes: input.reminderLeadMinutes ?? 60,
        followUpEnabled: input.followUpEnabled ?? false,
        followUpQuestion: input.followUpQuestion?.trim(),
        sourceType: input.sourceType ?? "GUARDIAN",
        verificationStatus:
          input.verificationStatus ?? "GUARDIAN_CONFIRMED",
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      this.schedules = [...this.schedules, created].sort((left, right) =>
        left.startsAt.localeCompare(right.startsAt),
      );
      return created;
    });
  }

  updateSchedule(
    id: string,
    input: UpdateScheduleInput,
  ): Promise<Schedule> {
    return withLatency(() => {
      const existing = requireEntity(
        this.schedules,
        (schedule) => schedule.id === id,
        "일정",
      );
      const updated: Schedule = {
        ...existing,
        ...clone(input),
        title: input.title?.trim() ?? existing.title,
        description:
          input.description === undefined
            ? existing.description
            : input.description.trim(),
        location:
          input.location === undefined
            ? existing.location
            : input.location.trim(),
        relatedPersonName:
          input.relatedPersonName === undefined
            ? existing.relatedPersonName
            : input.relatedPersonName.trim(),
        followUpQuestion:
          input.followUpQuestion === undefined
            ? existing.followUpQuestion
            : input.followUpQuestion.trim(),
        updatedAt: nowIso(),
      };
      this.schedules = this.schedules
        .map((schedule) => (schedule.id === id ? updated : schedule))
        .sort((left, right) => left.startsAt.localeCompare(right.startsAt));
      return updated;
    });
  }

  resetMockData(): Promise<BomiInitialData> {
    return withLatency(() => {
      this.elderProfile = clone(mockElderProfile);
      this.conversationPreferences = clone(mockConversationPreferences);
      this.confirmationRequests = clone(mockConfirmationRequests);
      this.medications = clone(mockMedications);
      this.medicationResponses = clone(mockMedicationResponses);
      this.schedules = clone(mockSchedules);
      this.robotStatus = clone(mockRobotStatus);
      this.activities = clone(mockActivities);
      this.syncProfilePreferencesFromMemories();
      return {
        dashboard: this.buildDashboard(),
        elderProfile: this.elderProfile,
        conversationPreferences: this.conversationPreferences.filter(
          isGuardianVisibleMemory,
        ),
        confirmationRequests: this.confirmationRequests,
        medications: this.medications.filter(
          (medication) => medication.status !== "ENDED",
        ),
        medicationResponses: this.medicationResponses.filter(
          (response) =>
            toDateInputValue(response.scheduledAt) ===
            toDateInputValue(new Date()),
        ),
        schedules: this.schedules,
        robotStatus: this.robotStatus,
        activities: this.activities.filter(isGuardianVisibleActivity),
      };
    });
  }
}

const unsupportedRealMutation = (label: string): never => {
  throw new Error(`${label} 기능은 아직 보호자 API와 연결되지 않았습니다.`);
};

const assertGuardianApiReady = (): void => {
  if (!GUARDIAN_API_AUTH_READY) {
    throw new Error(
      "인증된 보호자와 어르신 관계를 확인하는 API 계약이 준비되지 않아 실제 데이터를 조회하지 않았습니다.",
    );
  }
};

/** 실제 API 연동 서비스. mock 상태를 생성하거나 상속하지 않는다. */
class HttpBomiService implements BomiService {
  async getDashboard(): Promise<HomeDashboardSummary> {
    assertGuardianApiReady();
    const dto = await httpGet<DashboardDto>(API_ENDPOINTS.dashboard);
    return mapDashboard(dto);
  }

  async getElderProfile(): Promise<ElderProfile> {
    assertGuardianApiReady();
    const dto = await httpGet<ElderProfileDto>(API_ENDPOINTS.elderProfile);
    return mapElderProfile(dto);
  }

  async getConversationPreferences(): Promise<ConversationPreference[]> {
    assertGuardianApiReady();
    const dtos = await httpGet<MemoryDto[]>(
      API_ENDPOINTS.conversationPreferences,
    );
    return dtos.map(mapMemory).filter(isGuardianVisibleMemory);
  }

  async saveElderProfile(_profile: ElderProfile): Promise<ElderProfile> {
    return unsupportedRealMutation("어르신 설정 저장");
  }

  async createConversationPreference(
    _input: CreateConversationPreferenceInput,
  ): Promise<ConversationPreference> {
    return unsupportedRealMutation("대화 정보 추가");
  }

  async updateConversationPreference(
    _id: string,
    _input: UpdateConversationPreferenceInput,
  ): Promise<ConversationPreference> {
    return unsupportedRealMutation("대화 정보 수정");
  }

  async deleteConversationPreference(_id: string): Promise<string> {
    return unsupportedRealMutation("대화 정보 삭제");
  }

  async toggleConversationPreference(
    _id: string,
  ): Promise<ConversationPreference> {
    return unsupportedRealMutation("대화 정보 사용 설정");
  }

  async getConfirmationRequests(): Promise<ConfirmationRequest[]> {
    assertGuardianApiReady();
    const dtos = await httpGet<FactCandidateDto[]>(
      API_ENDPOINTS.confirmationRequests,
    );
    return dtos.map(mapFactCandidate);
  }

  async resolveConfirmationRequest(
    id: string,
    resolution: ConfirmationResolution,
    options?: {
      editedValue?: StructuredValue;
      note?: string;
    },
  ): Promise<ConfirmationRequest> {
    assertGuardianApiReady();
    const dto = await httpPost<FactCandidateDto>(
      `${API_ENDPOINTS.confirmationRequests}/${id}/resolve`,
      {
        resolution,
        editedValue: options?.editedValue,
        note: options?.note,
      },
    );
    return mapFactCandidate(dto);
  }

  async undoConfirmationResolution(id: string): Promise<ConfirmationRequest> {
    assertGuardianApiReady();
    const dto = await httpPost<FactCandidateDto>(
      `${API_ENDPOINTS.confirmationRequests}/${id}/undo`,
    );
    return mapFactCandidate(dto);
  }

  async getSchedules(): Promise<Schedule[]> {
    assertGuardianApiReady();
    const dtos = await httpGet<ScheduleDto[]>(API_ENDPOINTS.schedules);
    return dtos.flatMap((dto) => {
      try {
        return [mapSchedule(dto)];
      } catch {
        return [];
      }
    });
  }

  async getMedications(): Promise<Medication[]> {
    assertGuardianApiReady();
    const dtos = await httpGet<MedicationDto[]>(API_ENDPOINTS.medications);
    return dtos.map(mapMedication);
  }

  async getMedicationResponses(): Promise<MedicationResponse[]> {
    assertGuardianApiReady();
    const dtos = await httpGet<MedicationResponseDto[]>(
      API_ENDPOINTS.medicationResponses,
    );
    return dtos.map(mapMedicationResponse);
  }

  async createMedication(input: CreateMedicationInput): Promise<Medication> {
    assertGuardianApiReady();
    const dto = await httpPost<MedicationDto>(API_ENDPOINTS.medications, input);
    return mapMedication(dto);
  }

  async updateMedication(
    id: string,
    input: UpdateMedicationInput,
  ): Promise<Medication> {
    assertGuardianApiReady();
    const dto = await httpPut<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}`,
      input,
    );
    return mapMedication(dto);
  }

  async toggleMedicationStatus(id: string): Promise<Medication> {
    assertGuardianApiReady();
    const dto = await httpPost<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}/toggle-status`,
    );
    return mapMedication(dto);
  }

  async toggleMedicationReminder(id: string): Promise<Medication> {
    assertGuardianApiReady();
    const dto = await httpPost<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}/toggle-reminder`,
    );
    return mapMedication(dto);
  }

  async deleteMedication(id: string): Promise<string> {
    assertGuardianApiReady();
    const res = await httpDelete<{ id: string }>(
      `${API_ENDPOINTS.medications}/${id}`,
    );
    return res.id;
  }

  async createSchedule(input: CreateScheduleInput): Promise<Schedule> {
    assertGuardianApiReady();
    const dto = await httpPost<ScheduleDto>(API_ENDPOINTS.schedules, input);
    return mapSchedule(dto);
  }

  async updateSchedule(
    id: string,
    input: UpdateScheduleInput,
  ): Promise<Schedule> {
    assertGuardianApiReady();
    const dto = await httpPut<ScheduleDto>(
      `${API_ENDPOINTS.schedules}/${id}`,
      input,
    );
    return mapSchedule(dto);
  }

  async getInitialData(): Promise<BomiInitialData> {
    const results = await Promise.allSettled([
      this.getDashboard(),
      this.getConfirmationRequests(),
      this.getElderProfile(),
      this.getConversationPreferences(),
      this.getSchedules(),
      this.getMedications(),
      this.getMedicationResponses(),
    ]);
    const errors: Partial<Record<BomiDataKey, string>> = {};
    const readResult = <T,>(
      result: PromiseSettledResult<T>,
      key: BomiDataKey,
      fallback: T,
    ): T => {
      if (result.status === "fulfilled") return result.value;
      errors[key] =
        result.reason instanceof Error
          ? result.reason.message
          : "정보를 불러오지 못했습니다.";
      return fallback;
    };
    const dashboard = readResult(results[0], "dashboard", null);
    const confirmationRequests = readResult(
      results[1],
      "confirmationRequests",
      [],
    );
    const elderProfile = readResult(results[2], "elderProfile", null);
    const conversationPreferences = readResult(
      results[3],
      "conversationPreferences",
      [],
    );
    const schedules = readResult(results[4], "schedules", []);
    const medications = readResult(results[5], "medications", []);
    const medicationResponses = readResult(
      results[6],
      "medicationResponses",
      [],
    );
    return {
      dashboard,
      confirmationRequests,
      elderProfile,
      conversationPreferences,
      schedules,
      medications,
      medicationResponses,
      robotStatus: dashboard?.robot ?? {
        id: "",
        elderId: "",
        registrationActive: false,
      },
      activities: dashboard?.recentActivities ?? [],
      errors,
    };
  }

  async resetMockData(): Promise<BomiInitialData> {
    return unsupportedRealMutation("예시 데이터 초기화");
  }
}

export const bomiService: BomiService = USE_MOCK_API
  ? new MockBomiService()
  : new HttpBomiService();
