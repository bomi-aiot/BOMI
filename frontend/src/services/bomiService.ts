// 보호자 웹 데이터 접근 계층.
// 예시(mock) 데이터는 사용하지 않는다. 화면에 노출되는 모든 값은 백엔드 API 응답이다.
// 백엔드에 API 가 없는 기능은 이 파일에 존재하지 않으며, 화면에서도 제공하지 않는다.
// 앞으로 필요한 서버 API 목록: docs/backend-api-todo.md

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
import { mapKnownPerson, type KnownPersonDto } from "./mappers/knownPerson";
import type {
  ActivitySummary,
  ConfirmationRequest,
  ConfirmationResolution,
  ConversationPreference,
  CreateMedicationInput,
  CreateScheduleInput,
  ElderProfile,
  HomeDashboardSummary,
  ImportantPerson,
  Medication,
  MedicationResponse,
  PersonalPreference,
  RobotStatus,
  Schedule,
  StructuredValue,
  UpdateMedicationInput,
  UpdateScheduleInput,
} from "../types/domain";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (
  configuredApiBaseUrl && configuredApiBaseUrl.length > 0
    ? configuredApiBaseUrl
    : "/api"
).replace(/\/+$/, "");

export const API_ENDPOINTS = {
  dashboard: `${API_BASE_URL}/v1/guardian/dashboard`,
  elderProfile: `${API_BASE_URL}/v1/elders/profile`,
  conversationPreferences: `${API_BASE_URL}/v1/memories`,
  confirmationRequests: `${API_BASE_URL}/v1/confirmation-requests`,
  knownPersons: `${API_BASE_URL}/v1/known-persons`,
  medications: `${API_BASE_URL}/v1/care-records/medications`,
  medicationResponses: `${API_BASE_URL}/v1/care-records/medication-responses`,
  schedules: `${API_BASE_URL}/v1/care-records/schedules`,
} as const;

const isProfilePreferenceType = (
  memoryType: ConversationPreference["memoryType"],
): memoryType is "PREFERENCE" | "HOBBY" | "DAILY_ROUTINE" =>
  memoryType === "PREFERENCE" ||
  memoryType === "HOBBY" ||
  memoryType === "DAILY_ROUTINE";

const toPersonalPreference = (
  preference: ConversationPreference,
): PersonalPreference => ({
  id: preference.id,
  elderId: preference.elderId,
  memoryType: preference.memoryType as PersonalPreference["memoryType"],
  title: preference.title,
  detail: preference.content,
  keywords: preference.keywords,
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
});

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

/** 백엔드에 실제 엔드포인트가 있는 기능만 선언한다. */
export interface BomiService {
  getInitialData(): Promise<BomiInitialData>;
  getDashboard(): Promise<HomeDashboardSummary>;
  getElderProfile(): Promise<ElderProfile>;
  getConversationPreferences(): Promise<ConversationPreference[]>;
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
  toggleMedicationReminder(id: string): Promise<Medication>;
  deleteMedication(id: string): Promise<string>;
  getSchedules(): Promise<Schedule[]>;
  createSchedule(input: CreateScheduleInput): Promise<Schedule>;
  updateSchedule(id: string, input: UpdateScheduleInput): Promise<Schedule>;
}

class HttpBomiService implements BomiService {
  /** GET /v1/guardian/dashboard */
  async getDashboard(): Promise<HomeDashboardSummary> {
    const dto = await httpGet<DashboardDto>(API_ENDPOINTS.dashboard);
    return mapDashboard(dto);
  }

  /** GET /v1/known-persons — 어르신 주변 인물 명부. */
  async getKnownPersons(elderId: string): Promise<ImportantPerson[]> {
    const dtos = await httpGet<KnownPersonDto[]>(API_ENDPOINTS.knownPersons);
    return dtos.map((dto) => mapKnownPerson(dto, elderId));
  }

  /**
   * 프로필 화면이 쓰는 값은 세 API 로 나뉘어 있어 함께 조회한다.
   * - 기본정보: GET /v1/elders/profile
   * - 맞춤 대화 정보: GET /v1/memories
   * - 중요한 사람: GET /v1/known-persons
   * 보조 두 건이 실패해도 기본정보는 그대로 보여준다.
   */
  async getElderProfile(): Promise<ElderProfile> {
    const dto = await httpGet<ElderProfileDto>(API_ENDPOINTS.elderProfile);
    const profile = mapElderProfile(dto);
    const [memories, people] = await Promise.all([
      this.getConversationPreferences().catch(
        (): ConversationPreference[] => [],
      ),
      this.getKnownPersons(dto.id).catch((): ImportantPerson[] => []),
    ]);
    return {
      ...profile,
      personalPreferences: memories
        .filter((memory) => isProfilePreferenceType(memory.memoryType))
        .map(toPersonalPreference),
      importantPeople: people,
    };
  }

  /** GET /v1/memories */
  async getConversationPreferences(): Promise<ConversationPreference[]> {
    const dtos = await httpGet<MemoryDto[]>(
      API_ENDPOINTS.conversationPreferences,
    );
    return dtos.map(mapMemory).filter(isGuardianVisibleMemory);
  }

  /** GET /v1/confirmation-requests */
  async getConfirmationRequests(): Promise<ConfirmationRequest[]> {
    const dtos = await httpGet<FactCandidateDto[]>(
      API_ENDPOINTS.confirmationRequests,
    );
    return dtos.map(mapFactCandidate);
  }

  /** POST /v1/confirmation-requests/{id}/resolve */
  async resolveConfirmationRequest(
    id: string,
    resolution: ConfirmationResolution,
    options?: {
      editedValue?: StructuredValue;
      note?: string;
    },
  ): Promise<ConfirmationRequest> {
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

  /** POST /v1/confirmation-requests/{id}/undo */
  async undoConfirmationResolution(id: string): Promise<ConfirmationRequest> {
    const dto = await httpPost<FactCandidateDto>(
      `${API_ENDPOINTS.confirmationRequests}/${id}/undo`,
    );
    return mapFactCandidate(dto);
  }

  /** GET /v1/care-records/schedules */
  async getSchedules(): Promise<Schedule[]> {
    const dtos = await httpGet<ScheduleDto[]>(API_ENDPOINTS.schedules);
    return dtos.flatMap((dto) => {
      try {
        return [mapSchedule(dto)];
      } catch {
        return [];
      }
    });
  }

  /** GET /v1/care-records/medications */
  async getMedications(): Promise<Medication[]> {
    const dtos = await httpGet<MedicationDto[]>(API_ENDPOINTS.medications);
    return dtos.map(mapMedication);
  }

  /** GET /v1/care-records/medication-responses */
  async getMedicationResponses(): Promise<MedicationResponse[]> {
    const dtos = await httpGet<MedicationResponseDto[]>(
      API_ENDPOINTS.medicationResponses,
    );
    return dtos.map(mapMedicationResponse);
  }

  /** POST /v1/care-records/medications */
  async createMedication(input: CreateMedicationInput): Promise<Medication> {
    const dto = await httpPost<MedicationDto>(API_ENDPOINTS.medications, input);
    return mapMedication(dto);
  }

  /** PUT /v1/care-records/medications/{id} */
  async updateMedication(
    id: string,
    input: UpdateMedicationInput,
  ): Promise<Medication> {
    const dto = await httpPut<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}`,
      input,
    );
    return mapMedication(dto);
  }

  /** POST /v1/care-records/medications/{id}/toggle-status */
  async toggleMedicationStatus(id: string): Promise<Medication> {
    const dto = await httpPost<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}/toggle-status`,
    );
    return mapMedication(dto);
  }

  /** POST /v1/care-records/medications/{id}/toggle-reminder */
  async toggleMedicationReminder(id: string): Promise<Medication> {
    const dto = await httpPost<MedicationDto>(
      `${API_ENDPOINTS.medications}/${id}/toggle-reminder`,
    );
    return mapMedication(dto);
  }

  /** DELETE /v1/care-records/medications/{id} */
  async deleteMedication(id: string): Promise<string> {
    const res = await httpDelete<{ id: string }>(
      `${API_ENDPOINTS.medications}/${id}`,
    );
    return res.id;
  }

  /** POST /v1/care-records/schedules */
  async createSchedule(input: CreateScheduleInput): Promise<Schedule> {
    const dto = await httpPost<ScheduleDto>(API_ENDPOINTS.schedules, input);
    return mapSchedule(dto);
  }

  /** PUT /v1/care-records/schedules/{id} */
  async updateSchedule(
    id: string,
    input: UpdateScheduleInput,
  ): Promise<Schedule> {
    const dto = await httpPut<ScheduleDto>(
      `${API_ENDPOINTS.schedules}/${id}`,
      input,
    );
    return mapSchedule(dto);
  }

  /** 첫 진입 시 필요한 데이터를 한 번에 조회한다. 실패한 항목만 errors 에 담는다. */
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
}

export const bomiService: BomiService = new HttpBomiService();
