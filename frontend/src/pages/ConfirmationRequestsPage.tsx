import {
  useMemo,
  useState,
  type ChangeEvent,
} from 'react'
import {
  Badge,
  Button,
  Card,
  ConfirmModal,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Toast,
} from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  ConfirmationKind,
  ConfirmationRequest,
  ConfirmationRequestStatus,
  ConfirmationResolution,
  CoordinationStatus,
  RiskLevel,
  StructuredValue,
} from '../types/domain'
import { formatDateTime } from '../utils/date'

type KindFilter = 'ALL' | ConfirmationKind
type StatusFilter = 'PENDING' | 'RESOLVED' | 'ALL'
type DirectResolution = Exclude<ConfirmationResolution, 'EDIT'>

interface ResolutionDialogState {
  request: ConfirmationRequest
  resolution: DirectResolution
}

interface UndoToastState {
  open: boolean
  message: string
  tone: 'success' | 'danger' | 'info'
  requestId?: string
}

const KIND_LABELS: Record<ConfirmationKind, string> = {
  INTEREST: '관심사',
  SCHEDULE: '일정',
  HEALTH: '건강 상태',
  MEDICATION_CONFLICT: '복약 충돌',
}

const KIND_TONES: Record<
  ConfirmationKind,
  'info' | 'success' | 'warning' | 'danger'
> = {
  INTEREST: 'info',
  SCHEDULE: 'success',
  HEALTH: 'warning',
  MEDICATION_CONFLICT: 'danger',
}

const STATUS_LABELS: Record<ConfirmationRequestStatus, string> = {
  PENDING: '확인 대기',
  CONFIRMED: '확정',
  EDITED: '수정 후 확정',
  REJECTED: '반영 안 함',
  REASK_REQUESTED: '다시 질문 요청',
  EXPIRED: '확인 기한 종료',
}

const STATUS_TONES: Record<
  ConfirmationRequestStatus,
  'info' | 'success' | 'warning' | 'neutral'
> = {
  PENDING: 'warning',
  CONFIRMED: 'success',
  EDITED: 'success',
  REJECTED: 'neutral',
  REASK_REQUESTED: 'info',
  EXPIRED: 'neutral',
}

const RISK_LABELS: Record<RiskLevel, string> = {
  NORMAL: '일반',
  SENSITIVE: '민감',
  HIGH: '높음',
}

const RISK_TONES: Record<RiskLevel, 'neutral' | 'warning' | 'danger'> = {
  NORMAL: 'neutral',
  SENSITIVE: 'warning',
  HIGH: 'danger',
}

const COORDINATION_LABELS: Record<CoordinationStatus, string> = {
  NOT_REQUIRED: '',
  COORDINATION_REQUIRED: '조율 필요',
  WAITING_PRIMARY_GUARDIAN: '주 보호자 확인 대기',
  WAITING_SENIOR: '어르신 확인 대기',
  AGREED: '조율 완료',
  DISAGREED: '조율 불일치',
  SENIOR_UNREACHABLE: '어르신 연결 안 됨',
  GUARDIAN_OVERRIDE_CONFIRMED: '보호자 우선 확정',
  COMPLETED: '조율 종료',
}

const VALUE_KEY_LABELS: Record<string, string> = {
  content: '내용',
  memoryType: '정보 종류',
  title: '제목',
  keywords: '키워드',
  recordType: '기록 종류',
  startsAt: '일시',
  medicationName: '약 이름',
  localTime: '복용 시각',
  localTimes: '복용 시각',
  statusLevel: '상태',
}

const WAITING_REASON_COPY: Record<
  NonNullable<ConfirmationRequest['waitingReason']>,
  string
> = {
  CLARIFICATION: '제안 내용이 충분하지 않아 바로 확정할 수 없어요. 어르신께 다시 확인해 주세요.',
  COORDINATION: '조율이 완료될 때까지 바로 확정할 수 없어요. 필요한 사람에게 다시 확인해 주세요.',
  CAPTURED: '정보 후보를 정리 중이에요. 확정 가능한 상태가 될 때까지 기다려 주세요.',
  EXPIRED: '확인 기한이 지나 자동 종료됐어요. 보호자가 반영하지 않은 것으로 기록하지 않았습니다.',
}

const VISIBLE_VALUE_KEYS = new Set(Object.keys(VALUE_KEY_LABELS))

const VALUE_ENUM_LABELS: Record<string, string> = {
  HOBBY: '취미·관심사',
  PREFERENCE: '선호',
  APPOINTMENT: '병원 일정',
  PERSONAL_SCHEDULE: '개인 일정',
  HEALTH_OBSERVATION: '건강 관찰',
  NORMAL: '특이 상태 미표기 · 확인 전',
  ATTENTION: '관찰 필요',
  DANGER: '위험',
}

const RESOLUTION_COPY: Record<
  DirectResolution,
  {
    title: string
    description: string
    confirmLabel: string
    tone: 'default' | 'danger'
    completedMessage: string
  }
> = {
  CONFIRM: {
    title: '제안 내용을 확정할까요?',
    description:
      '확정하면 이후 대화와 알림에서 이 내용을 참고할 수 있습니다.',
    confirmLabel: '확정',
    tone: 'default',
    completedMessage: '제안 내용을 확정했습니다.',
  },
  REJECT: {
    title: '이 제안을 반영하지 않을까요?',
    description:
      '현재 제안은 저장하지 않으며, 기존에 확정된 정보는 그대로 유지합니다.',
    confirmLabel: '반영 안 함',
    tone: 'danger',
    completedMessage: '제안을 반영하지 않도록 처리했습니다.',
  },
  REASK: {
    title: '로봇이 다시 질문하도록 할까요?',
    description:
      '다음 자연스러운 대화 맥락에서 어르신께 한 번 더 확인합니다.',
    confirmLabel: '다시 질문 요청',
    tone: 'default',
    completedMessage: '로봇에게 다시 질문하도록 요청했습니다.',
  },
}

const messageFromError = (error: unknown): string =>
  error instanceof Error
    ? error.message
    : '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'

const formatScalarValue = (key: string, value: StructuredValue): string => {
  if (value === null) return '미입력'
  if (Array.isArray(value)) {
    return value.map((item) => formatScalarValue(key, item)).join(', ')
  }
  if (typeof value === 'object') {
    return '표시할 수 없는 형식'
  }
  if (typeof value === 'boolean') return value ? '예' : '아니요'

  const text = String(value)
  if (VALUE_ENUM_LABELS[text]) return VALUE_ENUM_LABELS[text]

  if (key === 'startsAt') {
    const parsed = new Date(text)
    if (!Number.isNaN(parsed.getTime())) return formatDateTime(parsed)
  }

  return text
}

function StructuredValuePanel({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: StructuredValue
  tone?: 'neutral' | 'proposed'
}) {
  const isRecord =
    value !== null && typeof value === 'object' && !Array.isArray(value)

  return (
    <section className={`value-panel value-panel--${tone}`}>
      <h3 className="value-panel__title">{label}</h3>
      {isRecord ? (
        <dl className="value-panel__list">
          {Object.entries(value)
            .filter(([key]) => VISIBLE_VALUE_KEYS.has(key))
            .map(([key, item]) => (
            <div key={key}>
              <dt>{VALUE_KEY_LABELS[key] ?? key}</dt>
              <dd>{formatScalarValue(key, item)}</dd>
            </div>
            ))}
        </dl>
      ) : (
        <p>{formatScalarValue('value', value)}</p>
      )}
    </section>
  )
}

function MedicationSafetyNotice({ compact = false }: { compact?: boolean }) {
  return (
    <aside
      className={`medication-safety-notice${
        compact ? ' medication-safety-notice--compact' : ''
      }`}
      role="note"
      aria-label="복약 안전 안내"
    >
      <strong>복약 정보는 자동으로 변경되지 않습니다.</strong>
      <p>
        어르신께 다시 확인한 뒤 의료진 또는 처방 문서로 확인하고, 보호자가
        복약 관리 화면에서 직접 수정해 주세요.
      </p>
    </aside>
  )
}

export function ConfirmationRequestsPage() {
  const {
    confirmationRequests,
    isLoading,
    error,
    dataErrors,
    pendingActionId,
    refresh,
    resolveConfirmationRequest,
    undoConfirmationRequest,
  } = useBomi()
  const pageError = dataErrors.confirmationRequests ?? error

  const [kindFilter, setKindFilter] = useState<KindFilter>('ALL')
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>('PENDING')
  const [resolutionDialog, setResolutionDialog] =
    useState<ResolutionDialogState | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [undoToast, setUndoToast] = useState<UndoToastState>({
    open: false,
    message: '',
    tone: 'success',
  })

  const pendingCount = confirmationRequests.filter(
    (request) => request.status === 'PENDING',
  ).length

  const kindCounts = useMemo(() => {
    const counts: Record<KindFilter, number> = {
      ALL: 0,
      INTEREST: 0,
      SCHEDULE: 0,
      HEALTH: 0,
      MEDICATION_CONFLICT: 0,
    }

    confirmationRequests.forEach((request) => {
      if (statusFilter === 'PENDING' && request.status !== 'PENDING') return
      if (statusFilter === 'RESOLVED' && request.status === 'PENDING') return
      counts.ALL += 1
      counts[request.kind] += 1
    })

    return counts
  }, [confirmationRequests, statusFilter])

  const filteredRequests = useMemo(
    () =>
      confirmationRequests.filter((request) => {
        const matchesKind =
          kindFilter === 'ALL' || request.kind === kindFilter
        const matchesStatus =
          statusFilter === 'ALL' ||
          (statusFilter === 'PENDING' && request.status === 'PENDING') ||
          (statusFilter === 'RESOLVED' && request.status !== 'PENDING')

        return matchesKind && matchesStatus
      }),
    [confirmationRequests, kindFilter, statusFilter],
  )

  const openResolutionDialog = (
    request: ConfirmationRequest,
    resolution: DirectResolution,
  ): void => {
    setResolutionDialog({ request, resolution })
    setResolutionNote('')
    setDialogError(null)
  }

  const closeResolutionDialog = (): void => {
    if (
      resolutionDialog &&
      pendingActionId === `confirmation-${resolutionDialog.request.id}`
    ) {
      return
    }
    setResolutionDialog(null)
    setResolutionNote('')
    setDialogError(null)
  }

  const handleResolution = async (): Promise<void> => {
    if (!resolutionDialog) return

    const { request, resolution } = resolutionDialog
    const copy = RESOLUTION_COPY[resolution]

    try {
      await resolveConfirmationRequest(request.id, resolution, {
        note: resolutionNote.trim() || undefined,
      })
      setResolutionDialog(null)
      setUndoToast({
        open: true,
        message: copy.completedMessage,
        tone: 'success',
        requestId: request.id,
      })
    } catch (requestError: unknown) {
      setDialogError(messageFromError(requestError))
    }
  }

  const handleUndo = async (requestId: string): Promise<void> => {
    try {
      await undoConfirmationRequest(requestId)
      setUndoToast({
        open: true,
        message: '처리를 되돌리고 확인 대기 상태로 복원했습니다.',
        tone: 'info',
      })
    } catch (requestError: unknown) {
      setUndoToast({
        open: true,
        message: messageFromError(requestError),
        tone: 'danger',
      })
    }
  }

  if (isLoading && confirmationRequests.length === 0) {
    return (
      <LoadingState label="AI 확인 요청을 불러오는 중입니다" rows={5} />
    )
  }

  if (pageError && confirmationRequests.length === 0) {
    return (
      <ErrorState
        title="AI 확인 요청을 불러오지 못했습니다"
        description={pageError}
        onRetry={() => void refresh()}
      />
    )
  }

  const kindTabs: readonly {
    value: KindFilter
    label: string
  }[] = [
    { value: 'ALL', label: '전체' },
    { value: 'INTEREST', label: KIND_LABELS.INTEREST },
    { value: 'SCHEDULE', label: KIND_LABELS.SCHEDULE },
    { value: 'HEALTH', label: KIND_LABELS.HEALTH },
    {
      value: 'MEDICATION_CONFLICT',
      label: KIND_LABELS.MEDICATION_CONFLICT,
    },
  ]

  const resolutionCopy = resolutionDialog
    ? RESOLUTION_COPY[resolutionDialog.resolution]
    : null
  const undoRequestId = undoToast.requestId

  return (
    <div className="page-stack confirmation-requests-page">
      <PageHeader
        eyebrow="AI 제안 검토"
        title="확인 요청"
        description="대화에서 새롭게 파악한 정보는 보호자가 확인한 뒤에만 확정 정보로 사용합니다."
        metadata={<span>확인 대기 {pendingCount}건</span>}
      />

      <Card compact>
        <div className="confirmation-toolbar">
          <div
            className="confirmation-tabs"
            aria-label="확인 요청 종류"
          >
            {kindTabs.map((tab) => (
              <button
                key={tab.value}
                className={`confirmation-tabs__item${
                  kindFilter === tab.value
                    ? ' confirmation-tabs__item--active'
                    : ''
                }`}
                type="button"
                aria-pressed={kindFilter === tab.value}
                onClick={() => setKindFilter(tab.value)}
              >
                <span>{tab.label}</span>
                <span
                  className="confirmation-tabs__count"
                  aria-label={`${kindCounts[tab.value]}건`}
                >
                  {kindCounts[tab.value]}
                </span>
              </button>
            ))}
          </div>
          <label className="form-field confirmation-toolbar__status">
            <span className="form-field__label">처리 상태</span>
            <select
              value={statusFilter}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setStatusFilter(event.target.value as StatusFilter)
              }
            >
              <option value="PENDING">확인 대기</option>
              <option value="RESOLVED">처리 완료</option>
              <option value="ALL">전체</option>
            </select>
          </label>
        </div>
      </Card>

      {pageError ? (
        <div className="page-inline-alert" role="alert">
          <span>{pageError}</span>
          <Button variant="quiet" size="small" onClick={() => void refresh()}>
            다시 불러오기
          </Button>
        </div>
      ) : null}

      {filteredRequests.length === 0 ? (
        <EmptyState
          title={
            statusFilter === 'PENDING'
              ? '확인할 요청이 없습니다'
              : '조건에 맞는 처리 내역이 없습니다'
          }
          description={
            statusFilter === 'PENDING'
              ? '새로운 제안이 생기면 이곳에 표시됩니다.'
              : '종류나 처리 상태 필터를 바꾸어 확인해 주세요.'
          }
          action={
            statusFilter !== 'PENDING' || kindFilter !== 'ALL' ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setKindFilter('ALL')
                  setStatusFilter('PENDING')
                }}
              >
                확인 대기 전체 보기
              </Button>
            ) : undefined
          }
          symbol="확인"
        />
      ) : (
        <ul className="confirmation-list" aria-label="AI 확인 요청 목록">
          {filteredRequests.map((request) => {
            const isPending = request.status === 'PENDING'
            const canDirectlyResolve =
              request.canResolve === true &&
              request.riskLevel !== 'HIGH' &&
              request.coordinationStatus === 'NOT_REQUIRED'
            const isProcessing =
              pendingActionId === `confirmation-${request.id}`
            const showCoordination =
              request.coordinationStatus !== 'NOT_REQUIRED'

            return (
              <li key={request.id}>
                <Card
                  as="article"
                  className={`confirmation-card confirmation-card--${request.kind
                    .toLocaleLowerCase()
                    .replace('_', '-')}`}
                  heading={request.title}
                  actions={
                    <div className="confirmation-card__status">
                      <Badge tone={KIND_TONES[request.kind]}>
                        {KIND_LABELS[request.kind]}
                      </Badge>
                      <Badge tone={STATUS_TONES[request.status]} dot>
                        {STATUS_LABELS[request.status]}
                      </Badge>
                      <Badge tone={RISK_TONES[request.riskLevel]}>
                        {RISK_LABELS[request.riskLevel]}
                      </Badge>
                      {showCoordination ? (
                        <Badge tone="info">
                          {COORDINATION_LABELS[request.coordinationStatus]}
                        </Badge>
                      ) : null}
                    </div>
                  }
                >
                  <p className="confirmation-card__summary">
                    {request.summary}
                  </p>
                  <aside className="confirmation-evidence" role="note">
                    <span className="confirmation-evidence__label">
                      확인 배경
                    </span>
                    <p>{request.evidence}</p>
                  </aside>

                  <div
                    className={`confirmation-comparison${
                      request.currentValue === undefined
                        ? ' confirmation-comparison--single'
                        : ''
                    }`}
                  >
                    {request.currentValue !== undefined ? (
                      <StructuredValuePanel
                        label="현재 저장된 내용"
                        value={request.currentValue}
                      />
                    ) : null}
                    <StructuredValuePanel
                      label="AI가 제안한 내용"
                      value={request.proposedValue}
                      tone="proposed"
                    />
                  </div>

                  {request.kind === 'MEDICATION_CONFLICT' ? (
                    <MedicationSafetyNotice compact />
                  ) : null}

                  <div className="confirmation-card__question">
                    <span>확인 질문</span>
                    <strong>{request.question}</strong>
                  </div>

                  <div className="confirmation-card__meta">
                    <span>제안 시각 {formatDateTime(request.createdAt)}</span>
                    <span>
                      정보 출처{' '}
                      {request.source === 'AI'
                        ? 'AI 분석'
                        : request.source === 'ROBOT'
                          ? '로봇 대화'
                          : request.source}
                    </span>
                  </div>

                  {isPending ? (
                    <div className="confirmation-card__actions">
                      {canDirectlyResolve ? (
                        <>
                          <Button
                            size="small"
                            onClick={() =>
                              openResolutionDialog(request, 'CONFIRM')
                            }
                            isLoading={isProcessing}
                            disabled={pendingActionId !== null && !isProcessing}
                          >
                            확인하고 반영하기
                          </Button>
                          <Button
                            variant="ghost"
                            size="small"
                            onClick={() =>
                              openResolutionDialog(request, 'REJECT')
                            }
                            disabled={pendingActionId !== null}
                          >
                            반영하지 않기
                          </Button>
                        </>
                      ) : (
                        <p className="confirmation-card__guardrail" role="note">
                          {request.waitingReason
                            ? WAITING_REASON_COPY[request.waitingReason]
                            : request.riskLevel === 'HIGH'
                              ? '민감도가 높은 정보라 바로 확정할 수 없어요. 어르신과 안전한 확인 절차를 거쳐 주세요.'
                              : '이 정보는 바로 확정할 수 없어요. 필요한 확인 절차를 먼저 진행해 주세요.'}
                        </p>
                      )}
                      {request.canRequestRecheck !== false ? (
                        <Button
                          variant="secondary"
                          size="small"
                          onClick={() =>
                            openResolutionDialog(request, 'REASK')
                          }
                          disabled={pendingActionId !== null}
                        >
                          어르신께 다시 확인하기
                        </Button>
                      ) : null}
                    </div>
                  ) : (
                    <div className="confirmation-card__resolution">
                      <strong>{STATUS_LABELS[request.status]}</strong>
                      <span>
                        {request.resolvedAt
                          ? formatDateTime(request.resolvedAt)
                          : '처리 시각 미기록'}
                      </span>
                      {request.resolutionNote ? (
                        <p>{request.resolutionNote}</p>
                      ) : null}
                      {request.waitingReason === 'EXPIRED' ? (
                        <p>{WAITING_REASON_COPY.EXPIRED}</p>
                      ) : null}
                    </div>
                  )}
                </Card>
              </li>
            )
          })}
        </ul>
      )}

      <ConfirmModal
        open={resolutionDialog !== null}
        title={resolutionCopy?.title ?? '확인 요청 처리'}
        description={
          resolutionDialog?.request.kind === 'MEDICATION_CONFLICT' &&
          resolutionDialog.resolution === 'CONFIRM'
            ? '복약 시간은 변경하지 않고, 보호자가 내용을 확인했다는 결과만 저장합니다.'
            : (resolutionCopy?.description ?? '')
        }
        confirmLabel={resolutionCopy?.confirmLabel ?? '확인'}
        tone={resolutionCopy?.tone ?? 'default'}
        isLoading={
          resolutionDialog !== null &&
          pendingActionId ===
            `confirmation-${resolutionDialog.request.id}`
        }
        onClose={closeResolutionDialog}
        onConfirm={() => void handleResolution()}
      >
        {resolutionDialog?.request.kind === 'MEDICATION_CONFLICT' ? (
          <MedicationSafetyNotice />
        ) : null}
        <label className="form-field resolution-note">
          <span className="form-field__label">처리 메모 (선택)</span>
          <textarea
            value={resolutionNote}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
              setResolutionNote(event.target.value)
            }
            rows={3}
            placeholder="판단 근거나 어르신께 다시 물어볼 내용을 적어 주세요."
          />
        </label>
        {dialogError ? (
          <p className="form-error" role="alert">
            {dialogError}
          </p>
        ) : null}
      </ConfirmModal>

      <Toast
        open={undoToast.open}
        message={undoToast.message}
        tone={undoToast.tone}
        actionLabel={undoToast.requestId ? '되돌리기' : undefined}
        onAction={
          undoRequestId
            ? () => void handleUndo(undoRequestId)
            : undefined
        }
        onDismiss={() =>
          setUndoToast((current) => ({ ...current, open: false }))
        }
      />
    </div>
  )
}
