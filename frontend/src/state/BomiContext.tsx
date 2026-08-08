import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  API_BASE_URL,
  USE_MOCK_API,
  bomiService,
  type BomiDataKey,
} from "../services/bomiService";
import type {
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
  Schedule,
  StructuredValue,
  UpdateConversationPreferenceInput,
  UpdateMedicationInput,
  UpdateScheduleInput,
  WalkAction,
  WalkRequestResult,
} from "../types/domain";

export interface BomiToast {
  id: number;
  // EMERGENCY 는 ERROR 와 다르다. ERROR 는 "내가 누른 것이 실패했다"이고,
  // EMERGENCY 는 "어르신 쪽에서 지금 무슨 일이 일어났다"이다. 같은 톤으로
  // 그리면 저장 실패 토스트와 위급 알림이 구분되지 않는다.
  tone: "SUCCESS" | "INFO" | "ERROR" | "EMERGENCY";
  message: string;
  actionLabel?: string;
  actionRequestId?: string;
}

export interface BomiContextValue {
  dashboard: HomeDashboardSummary | null;
  elderProfile: ElderProfile | null;
  conversationPreferences: ConversationPreference[];
  confirmationRequests: ConfirmationRequest[];
  medications: Medication[];
  medicationResponses: MedicationResponse[];
  schedules: Schedule[];
  isLoading: boolean;
  isSaving: boolean;
  pendingActionId: string | null;
  error: string | null;
  dataErrors: Partial<Record<BomiDataKey, string>>;
  toast: BomiToast | null;
  isMockMode: boolean;
  apiBaseUrl: string;
  refresh: () => Promise<void>;
  saveElderProfile: (profile: ElderProfile) => Promise<ElderProfile>;
  addConversationPreference: (
    input: CreateConversationPreferenceInput,
  ) => Promise<ConversationPreference>;
  updateConversationPreference: (
    id: string,
    input: UpdateConversationPreferenceInput,
  ) => Promise<ConversationPreference>;
  deleteConversationPreference: (id: string) => Promise<void>;
  toggleConversationPreference: (
    id: string,
  ) => Promise<ConversationPreference>;
  resolveConfirmationRequest: (
    id: string,
    resolution: ConfirmationResolution,
    options?: {
      editedValue?: StructuredValue;
      note?: string;
    },
  ) => Promise<ConfirmationRequest>;
  undoConfirmationRequest: (id: string) => Promise<ConfirmationRequest>;
  addMedication: (input: CreateMedicationInput) => Promise<Medication>;
  updateMedication: (
    id: string,
    input: UpdateMedicationInput,
  ) => Promise<Medication>;
  toggleMedicationStatus: (id: string) => Promise<Medication>;
  deleteMedication: (id: string) => Promise<void>;
  toggleMedicationReminder: (id: string) => Promise<Medication>;
  addSchedule: (input: CreateScheduleInput) => Promise<Schedule>;
  requestWalk: (action: WalkAction) => Promise<WalkRequestResult>;
  updateSchedule: (
    id: string,
    input: UpdateScheduleInput,
  ) => Promise<Schedule>;
  resetDemoData: () => Promise<void>;
  clearError: () => void;
  clearToast: () => void;
}

export const BomiContext = createContext<BomiContextValue | undefined>(
  undefined,
);

interface BomiProviderProps {
  children: ReactNode;
}

/**
 * 보호자 화면 자동 갱신 주기(ms).
 *
 * 왜 대시보드만인가 — 로봇 모드·실내 온습도·복약 진행·확인 대기 건수가 모두
 * GET /v1/guardian/dashboard 응답 하나에 담긴다. 나머지(프로필·기억·명부·일정)는
 * 사람이 고쳐야 바뀌는 값이라 폴링 대상이 아니다.
 *
 * 왜 1초인가 — 시연 중 로봇 상태 변화를 즉시 보여야 한다. refresh() 전체는
 * API 를 9개 때리므로 1초로 돌리면 nginx limit_req(20r/s, IP 기준)에 탭 3개부터
 * 걸린다. getDashboard() 하나만 돌리면 탭당 1r/s 라 여유가 크다.
 */
const DASHBOARD_POLL_INTERVAL_MS = 1000;

/**
 * 산책 요청이 거절된 이유를 보호자의 말로 옮긴다.
 * 백엔드 WalkRequestDisposition 의 reasonCode 와 1:1.
 */
const WALK_REJECT_COPY: Record<string, string> = {
  NO_ACTIVE_WALK: "지금 진행 중인 산책이 없습니다.",
  ALREADY_STOPPING: "산책을 종료하는 중입니다.",
  UNKNOWN_ROBOT: "등록된 보미를 찾을 수 없습니다.",
  INACTIVE_ROBOT: "보미가 지금 사용 중이 아닙니다.",
  UNASSIGNED_ROBOT: "보미가 어르신께 연결되어 있지 않습니다.",
  SAFE_STOP: "보미가 안전 정지 상태예요. 확인 후 다시 시도해 주세요.",
  REST_GUARD: "지금은 어르신 휴식 시간이라 산책을 시작하지 않습니다.",
  ACTIVE_SCENARIO: "보미가 다른 돌봄을 수행 중이에요. 끝난 뒤 다시 시도해 주세요.",
  BUSY_MODE: "보미가 지금 다른 일을 하고 있어요.",
  REQUEST_ID_REUSED: "이미 처리된 요청입니다.",
  MQTT_UNAVAILABLE: "보미와 연결이 끊겨 요청을 전달하지 못했습니다.",
};

const messageFromError = (error: unknown): string =>
  error instanceof Error
    ? error.message
    : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";

export function BomiProvider({ children }: BomiProviderProps) {
  const [dashboard, setDashboard] = useState<HomeDashboardSummary | null>(null);
  const [elderProfile, setElderProfile] = useState<ElderProfile | null>(null);
  const [conversationPreferences, setConversationPreferences] = useState<
    ConversationPreference[]
  >([]);
  const [confirmationRequests, setConfirmationRequests] = useState<
    ConfirmationRequest[]
  >([]);
  const [medications, setMedications] = useState<Medication[]>([]);
  const [medicationResponses, setMedicationResponses] = useState<
    MedicationResponse[]
  >([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dataErrors, setDataErrors] = useState<
    Partial<Record<BomiDataKey, string>>
  >({});
  const [toast, setToast] = useState<BomiToast | null>(null);

  const showToast = useCallback(
    (
      message: string,
      tone: BomiToast["tone"] = "SUCCESS",
      undoRequestId?: string,
    ) => {
      setToast({
        id: Date.now(),
        tone,
        message,
        actionLabel: undoRequestId ? "되돌리기" : undefined,
        actionRequestId: undoRequestId,
      });
    },
    [],
  );

  // 진행 중인 대시보드 요청이 있는지. 1초 폴링에서 응답이 1초를 넘기면 요청이
  // 겹쳐 쌓이고, 그대로 두면 스스로 rate limit 을 때린다.
  const dashboardInFlight = useRef(false);

  // 이미 본 위급 알림(T1) id.
  //
  // 왜 "지금 알림이 있다"를 조건으로 쓰지 않는가
  //   폴링이 1초다. 존재 여부로 판정하면 알림이 남아 있는 동안 매 초 토스트가
  //   다시 뜬다. 화면에 계속 떠 있는 경고는 곧 아무도 안 보는 경고가 된다.
  //
  // 왜 첫 응답은 기준선으로만 쓰는가 (null → Set)
  //   화면을 여는 순간 어제 알림이 위급 토스트로 튀어나오면, 정작 진짜 위급이
  //   왔을 때 아무도 그 토스트를 믿지 않는다. 첫 응답에 들어 있던 것은
  //   "이미 있던 것"으로 간주하고, 그 이후에 새로 생긴 id 만 알린다.
  const seenAlertIds = useRef<Set<string> | null>(null);

  const refreshDashboard = useCallback(async () => {
    if (dashboardInFlight.current) return;
    dashboardInFlight.current = true;
    try {
      const nextDashboard = await bomiService.getDashboard();
      setDashboard(nextDashboard);
      // 대시보드 응답 하나가 복약 응답과 확인 요청까지 이미 담고 있다.
      // 이 값을 각 화면의 상태로 흘려보내면 요청 수를 늘리지 않고도
      // 복약 관리·확인할 일 화면이 같은 1초 주기로 살아난다.
      // (복약 "목록" 자체는 사람이 등록할 때만 바뀌므로 여기서 건드리지 않는다.)
      setMedicationResponses(nextDashboard.medicationResponses);
      setConfirmationRequests(nextDashboard.confirmationRequests);

      // safetyAlerts 가 null 이면 "확인하지 못했다"는 뜻이다. 그 응답으로
      // 기준선을 세우거나 알림을 지우면 안 된다 — 다음 성공 응답까지 기다린다.
      const alerts = nextDashboard.safetyAlerts;
      if (alerts !== null) {
        const seen = seenAlertIds.current;
        if (seen === null) {
          seenAlertIds.current = new Set(alerts.map((alert) => alert.id));
        } else {
          const fresh = alerts.filter((alert) => !seen.has(alert.id));
          fresh.forEach((alert) => seen.add(alert.id));
          if (fresh.length > 0) {
            // 여러 건이 한 틱에 같이 오면 가장 위의 한 건만 문장으로 보여주고
            // 나머지는 건수로 접는다. 토스트를 여러 개 쌓으면 서로를 가린다.
            showToast(
              fresh.length === 1
                ? fresh[0].message
                : `${fresh[0].message} (외 ${fresh.length - 1}건)`,
              "EMERGENCY",
            );
          }
        }
      }
    } catch {
      // 주 변경은 이미 성공했으므로 파생 요약 갱신 실패를 액션 실패로 되돌리지 않는다.
      // 폴링에서도 같은 이유로 삼킨다 — 일시적 실패에 1초마다 에러를 띄우면
      // 화면이 더 못 쓰게 된다. 다음 틱에 저절로 복구된다.
    } finally {
      dashboardInFlight.current = false;
    }
  }, [showToast]);

  const refreshPersonalizationState = useCallback(async () => {
    try {
      const [nextProfile, nextPreferences] = await Promise.all([
        bomiService.getElderProfile(),
        bomiService.getConversationPreferences(),
      ]);
      setElderProfile(nextProfile);
      setConversationPreferences(nextPreferences);
    } catch {
      // 다음 전체 새로고침에서 재동기화한다.
    }
  }, []);

  const refreshConfirmationEffects = useCallback(async () => {
    try {
      const [
        nextDashboard,
        nextProfile,
        nextPreferences,
        nextSchedules,
      ] = await Promise.all([
        bomiService.getDashboard(),
        bomiService.getElderProfile(),
        bomiService.getConversationPreferences(),
        bomiService.getSchedules(),
      ]);
      setDashboard(nextDashboard);
      setElderProfile(nextProfile);
      setConversationPreferences(nextPreferences);
      setSchedules(nextSchedules);
    } catch {
      // 확인 결과 자체는 저장되었으므로 중복 처리를 막기 위해 성공으로 유지한다.
    }
  }, []);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setDataErrors({});
    try {
      const data = await bomiService.getInitialData();
      setDashboard(data.dashboard);
      setElderProfile(data.elderProfile);
      setConversationPreferences(data.conversationPreferences);
      setConfirmationRequests(data.confirmationRequests);
      setMedications(data.medications);
      setMedicationResponses(data.medicationResponses);
      setSchedules(data.schedules);
      setDataErrors(data.errors ?? {});
    } catch (requestError: unknown) {
      setError(messageFromError(requestError));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 대시보드 자동 갱신. isLoading 을 건드리지 않으므로 로딩 스켈레톤이 깜빡이지 않고,
  // 화면은 바뀐 값만 조용히 다시 그린다. 탭이 보이지 않을 때는 요청하지 않는다.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") void refreshDashboard();
    };
    const timer = window.setInterval(tick, DASHBOARD_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refreshDashboard]);

  const runAction = useCallback(
    async <T,>(
      actionId: string,
      request: () => Promise<T>,
      successMessage?: string,
    ): Promise<T> => {
      setPendingActionId(actionId);
      setError(null);
      try {
        const result = await request();
        if (successMessage) {
          showToast(successMessage);
        }
        return result;
      } catch (requestError: unknown) {
        const message = messageFromError(requestError);
        setError(message);
        showToast(message, "ERROR");
        throw requestError;
      } finally {
        setPendingActionId(null);
      }
    },
    [showToast],
  );

  const saveElderProfile = useCallback(
    async (profile: ElderProfile): Promise<ElderProfile> => {
      setIsSaving(true);
      try {
        const saved = await runAction(
          "elder-profile",
          () => bomiService.saveElderProfile(profile),
          "어르신 정보가 저장되었습니다.",
        );
        setElderProfile(saved);
        void refreshPersonalizationState();
        void refreshDashboard();
        return saved;
      } finally {
        setIsSaving(false);
      }
    },
    [refreshDashboard, refreshPersonalizationState, runAction],
  );

  const addConversationPreference = useCallback(
    async (
      input: CreateConversationPreferenceInput,
    ): Promise<ConversationPreference> => {
      const created = await runAction(
        "preference-new",
        () => bomiService.createConversationPreference(input),
        "맞춤 대화 정보가 추가되었습니다.",
      );
      setConversationPreferences((current) => [created, ...current]);
      void refreshPersonalizationState();
      return created;
    },
    [refreshPersonalizationState, runAction],
  );

  const updateConversationPreference = useCallback(
    async (
      id: string,
      input: UpdateConversationPreferenceInput,
    ): Promise<ConversationPreference> => {
      const updated = await runAction(
        `preference-${id}`,
        () => bomiService.updateConversationPreference(id, input),
        "맞춤 대화 정보가 수정되었습니다.",
      );
      setConversationPreferences((current) =>
        current.map((preference) =>
          preference.id === id ? updated : preference,
        ),
      );
      void refreshPersonalizationState();
      return updated;
    },
    [refreshPersonalizationState, runAction],
  );

  const deleteConversationPreference = useCallback(
    async (id: string): Promise<void> => {
      await runAction(
        `preference-${id}`,
        () => bomiService.deleteConversationPreference(id),
        "맞춤 대화 정보가 삭제되었습니다.",
      );
      setConversationPreferences((current) =>
        current.filter((preference) => preference.id !== id),
      );
      setElderProfile((current) =>
        current
          ? {
              ...current,
              personalPreferences: current.personalPreferences.filter(
                (preference) => preference.id !== id,
              ),
              importantPeople: current.importantPeople.filter(
                (person) => person.id !== id,
              ),
            }
          : current,
      );
      void refreshPersonalizationState();
    },
    [refreshPersonalizationState, runAction],
  );

  const toggleConversationPreference = useCallback(
    async (id: string): Promise<ConversationPreference> => {
      const updated = await runAction(
        `preference-${id}`,
        () => bomiService.toggleConversationPreference(id),
        "대화 활용 상태가 변경되었습니다.",
      );
      setConversationPreferences((current) =>
        current.map((preference) =>
          preference.id === id ? updated : preference,
        ),
      );
      return updated;
    },
    [runAction],
  );

  const resolveConfirmationRequest = useCallback(
    async (
      id: string,
      resolution: ConfirmationResolution,
      options?: {
        editedValue?: StructuredValue;
        note?: string;
      },
    ): Promise<ConfirmationRequest> => {
      const updated = await runAction(
        `confirmation-${id}`,
        () => bomiService.resolveConfirmationRequest(id, resolution, options),
      );
      setConfirmationRequests((current) =>
        current.map((request) => (request.id === id ? updated : request)),
      );
      void refreshConfirmationEffects();
      showToast(
        resolution === "REASK"
          ? "로봇에게 다시 질문하도록 요청했습니다."
          : "확인 요청을 처리했습니다.",
        "SUCCESS",
        id,
      );
      return updated;
    },
    [refreshConfirmationEffects, runAction, showToast],
  );

  const undoConfirmationRequest = useCallback(
    async (id: string): Promise<ConfirmationRequest> => {
      const updated = await runAction(
        `confirmation-${id}`,
        () => bomiService.undoConfirmationResolution(id),
        "확인 요청 처리를 되돌렸습니다.",
      );
      setConfirmationRequests((current) =>
        current.map((request) => (request.id === id ? updated : request)),
      );
      void refreshConfirmationEffects();
      return updated;
    },
    [refreshConfirmationEffects, runAction],
  );

  const addMedication = useCallback(
    async (input: CreateMedicationInput): Promise<Medication> => {
      const created = await runAction(
        "medication-new",
        () => bomiService.createMedication(input),
        "복약 정보가 추가되었습니다.",
      );
      setMedications((current) => [...current, created]);
      void refreshDashboard();
      return created;
    },
    [refreshDashboard, runAction],
  );

  const updateMedication = useCallback(
    async (
      id: string,
      input: UpdateMedicationInput,
    ): Promise<Medication> => {
      const updated = await runAction(
        `medication-${id}`,
        () => bomiService.updateMedication(id, input),
        "복약 정보가 수정되었습니다.",
      );
      setMedications((current) =>
        current.map((medication) =>
          medication.id === id ? updated : medication,
        ),
      );
      void refreshDashboard();
      return updated;
    },
    [refreshDashboard, runAction],
  );

  const toggleMedicationStatus = useCallback(
    async (id: string): Promise<Medication> => {
      const updated = await runAction(
        `medication-${id}`,
        () => bomiService.toggleMedicationStatus(id),
        "복약 사용 상태가 변경되었습니다.",
      );
      setMedications((current) =>
        current.map((medication) =>
          medication.id === id ? updated : medication,
        ),
      );
      void refreshDashboard();
      return updated;
    },
    [refreshDashboard, runAction],
  );

  const deleteMedication = useCallback(
    async (id: string): Promise<void> => {
      await runAction(
        `medication-${id}`,
        () => bomiService.deleteMedication(id),
        "복약 정보가 삭제되었습니다.",
      );
      setMedications((current) =>
        current.filter((medication) => medication.id !== id),
      );
      void refreshDashboard();
    },
    [refreshDashboard, runAction],
  );

  const toggleMedicationReminder = useCallback(
    async (id: string): Promise<Medication> => {
      const updated = await runAction(
        `medication-${id}`,
        () => bomiService.toggleMedicationReminder(id),
        "복약 알림 설정이 변경되었습니다.",
      );
      setMedications((current) =>
        current.map((medication) =>
          medication.id === id ? updated : medication,
        ),
      );
      void refreshDashboard();
      return updated;
    },
    [refreshDashboard, runAction],
  );

  /**
   * 산책 시작·종료 요청.
   *
   * 성공 응답이어도 accepted 가 false 일 수 있어(예: 종료할 산책이 없음, 로봇이
   * SAFE_STOP) reasonCode 를 사람 말로 바꿔 알린다. 백엔드가 거절한 것을 화면이
   * 성공처럼 보여주면 발표자가 로봇을 계속 기다리게 된다.
   *
   * 요청 뒤 대시보드를 한 번 당겨온다 — 1초 폴링이 곧 따라잡지만, 버튼을 누른
   * 사람에게는 즉시 반응이 보여야 한다.
   */
  const requestWalk = useCallback(
    async (action: WalkAction): Promise<WalkRequestResult> => {
      const deviceId = dashboard?.robot.deviceId;
      if (!deviceId) {
        const message = "보미의 기기 정보를 확인할 수 없어 산책을 요청하지 못했습니다.";
        showToast(message, "ERROR");
        throw new Error(message);
      }
      const result = await runAction(
        `walk-${action.toLowerCase()}`,
        () => bomiService.requestWalk(action, deviceId),
      );
      if (result.accepted) {
        showToast(
          action === "START" ? "산책을 시작했습니다." : "산책을 종료했습니다.",
        );
      } else {
        showToast(WALK_REJECT_COPY[result.reasonCode ?? ""] ?? "산책 요청이 처리되지 않았습니다.", "INFO");
      }
      void refreshDashboard();
      return result;
    },
    [dashboard?.robot.deviceId, refreshDashboard, runAction, showToast],
  );

  const addSchedule = useCallback(
    async (input: CreateScheduleInput): Promise<Schedule> => {
      const created = await runAction(
        "schedule-new",
        () => bomiService.createSchedule(input),
        "새 일정이 추가되었습니다.",
      );
      setSchedules((current) =>
        [...current, created].sort((left, right) =>
          left.startsAt.localeCompare(right.startsAt),
        ),
      );
      void refreshDashboard();
      return created;
    },
    [refreshDashboard, runAction],
  );

  const updateSchedule = useCallback(
    async (
      id: string,
      input: UpdateScheduleInput,
    ): Promise<Schedule> => {
      const updated = await runAction(
        `schedule-${id}`,
        () => bomiService.updateSchedule(id, input),
        "일정이 수정되었습니다.",
      );
      setSchedules((current) =>
        current
          .map((schedule) => (schedule.id === id ? updated : schedule))
          .sort((left, right) => left.startsAt.localeCompare(right.startsAt)),
      );
      void refreshDashboard();
      return updated;
    },
    [refreshDashboard, runAction],
  );

  const resetDemoData = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    setDataErrors({});
    try {
      const data = await bomiService.resetMockData();
      setDashboard(data.dashboard);
      setElderProfile(data.elderProfile);
      setConversationPreferences(data.conversationPreferences);
      setConfirmationRequests(data.confirmationRequests);
      setMedications(data.medications);
      setMedicationResponses(data.medicationResponses);
      setSchedules(data.schedules);
      setDataErrors(data.errors ?? {});
      showToast("데모 데이터를 초기 상태로 되돌렸습니다.", "INFO");
    } catch (requestError: unknown) {
      setError(messageFromError(requestError));
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const clearError = useCallback(() => setError(null), []);
  const clearToast = useCallback(() => setToast(null), []);

  const value = useMemo<BomiContextValue>(
    () => ({
      dashboard,
      elderProfile,
      conversationPreferences,
      confirmationRequests,
      medications,
      medicationResponses,
      schedules,
      isLoading,
      isSaving,
      pendingActionId,
      error,
      dataErrors,
      toast,
      isMockMode: USE_MOCK_API,
      apiBaseUrl: API_BASE_URL,
      refresh,
      saveElderProfile,
      addConversationPreference,
      updateConversationPreference,
      deleteConversationPreference,
      toggleConversationPreference,
      resolveConfirmationRequest,
      undoConfirmationRequest,
      addMedication,
      updateMedication,
      toggleMedicationStatus,
      deleteMedication,
      toggleMedicationReminder,
      addSchedule,
      requestWalk,
      updateSchedule,
      resetDemoData,
      clearError,
      clearToast,
    }),
    [
      dashboard,
      elderProfile,
      conversationPreferences,
      confirmationRequests,
      medications,
      medicationResponses,
      schedules,
      isLoading,
      isSaving,
      pendingActionId,
      error,
      dataErrors,
      toast,
      refresh,
      saveElderProfile,
      addConversationPreference,
      updateConversationPreference,
      deleteConversationPreference,
      toggleConversationPreference,
      resolveConfirmationRequest,
      undoConfirmationRequest,
      addMedication,
      updateMedication,
      toggleMedicationStatus,
      deleteMedication,
      toggleMedicationReminder,
      addSchedule,
      requestWalk,
      updateSchedule,
      resetDemoData,
      clearError,
      clearToast,
    ],
  );

  return <BomiContext.Provider value={value}>{children}</BomiContext.Provider>;
}

export function useBomi(): BomiContextValue {
  const context = useContext(BomiContext);
  if (!context) {
    throw new Error("useBomi는 BomiProvider 내부에서만 사용할 수 있습니다.");
  }
  return context;
}
