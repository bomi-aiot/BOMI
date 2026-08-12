import { useMemo, useState } from 'react'
import {
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
  StructuredValue,
} from '../types/domain'
import { formatDateTime, formatSpokenDateTime } from '../utils/date'

type KindFilter = 'ALL' | ConfirmationKind
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


const STATUS_LABELS: Record<ConfirmationRequestStatus, string> = {
  PENDING: '확인 대기',
  CONFIRMED: '확정',
  EDITED: '수정 후 확정',
  REJECTED: '반영 안 함',
  REASK_REQUESTED: '다시 질문 요청',
  EXPIRED: '확인 기한 종료',
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
  // content 는 어르신이 실제로 한 말이고, 로봇이 보내는 유일한 키다. 이 줄이 없어서
  // 아래 VISIBLE_VALUE_KEYS 가 그 값을 걸러냈고 — 매퍼의 허용 목록과 합쳐 두 겹으로
  // 걸렀다 — 카드의 값 패널이 항상 빈 상자였다. 라벨을 "내용"으로 두는 이유는
  // 이것이 요약도 해석도 아닌 원문이기 때문이다.
  content: '내용',
  note: '말씀하신 내용',
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

// 큰 인용문으로 이미 보여 준 키. 값 패널에서는 빼서 같은 문장을 두 번 읽히지 않는다.
const QUOTE_KEYS = new Set(['content', 'note'])

/** 어르신이 실제로 한 말. 없으면 undefined — 지어내지 않는다. */
function spokenText(request: ConfirmationRequest): string | undefined {
  const value = request.proposedValue
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  for (const key of ['note', 'content']) {
    const candidate = (value as Record<string, StructuredValue>)[key]
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate.trim()
    }
  }
  return undefined
}

function visibleRows(
  value: StructuredValue,
  omitKeys?: ReadonlySet<string>,
): [string, StructuredValue][] {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value).filter(
    ([key]) => VISIBLE_VALUE_KEYS.has(key) && !omitKeys?.has(key),
  )
}

/**
 * 인용문 말고 <b>더</b> 있는 값만 보여 준다. 더할 것이 없으면 아무것도 그리지 않는다.
 *
 * 예전에는 값이 한 줄도 없어도 제목만 붙은 빈 상자를 그렸다. 그래서 허용 목록에서 키
 * 하나가 빠진 것을 아무도 눈치채지 못했다 — 빈 상자는 "못 읽었다"가 아니라 "볼 것이
 * 없다"로 읽힌다. 지금은 정말 볼 것이 없으면 상자 자체가 사라지고, 화면에 보여 줄 것이
 * 하나도 없는 경우에만 카드가 그 사실을 문장으로 말한다(아래 confirmation-card 참고).
 */
function StructuredValuePanel({
  label,
  value,
  omitKeys,
}: {
  label: string
  value: StructuredValue
  omitKeys?: ReadonlySet<string>
}) {
  const rows = visibleRows(value, omitKeys)
  if (rows.length === 0) return null

  return (
    <section className="value-panel">
      <h3 className="value-panel__title">{label}</h3>
      <dl className="value-panel__list">
        {rows.map(([key, item]) => (
          <div key={key}>
            <dt>{VALUE_KEY_LABELS[key] ?? key}</dt>
            <dd>{formatScalarValue(key, item)}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

/**
 * 버튼에 "무엇이 일어나는가"를 적는다.
 *
 * 예전 문구는 "확인하고 반영하기 / 반영하지 않기" 였다. 무엇이 어디에 반영되는지가
 * 문장에 없어서, 보호자는 누르기 전에 알 수 없고 누른 뒤에도 알 수 없었다.
 * 복약 충돌만 다르게 쓰는 이유 — 그쪽의 확정은 복약 시간을 바꾸지 않고 "보호자가
 * 봤다"는 사실만 남긴다. 거기에 "남기기"라고 적으면 하지 않는 일을 약속하게 된다.
 */
const ACTION_LABELS: Record<
  ConfirmationKind,
  { confirm: string; reject: string }
> = {
  HEALTH: { confirm: '남기기', reject: '남기지 않기' },
  SCHEDULE: { confirm: '일정에 넣기', reject: '넣지 않기' },
  INTEREST: { confirm: '기억해 두기', reject: '기억하지 않기' },
  MEDICATION_CONFLICT: { confirm: '확인했어요', reject: '넘어가기' },
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
      counts.ALL += 1
      counts[request.kind] += 1
    })

    return counts
  }, [confirmationRequests])

  // 고른 종류가 목록에서 사라지면(마지막 한 건을 처리했을 때) 전체로 되돌린다.
  // 그러지 않으면 탭 줄이 사라진 뒤에도 필터만 남아, 되돌릴 방법 없는 빈 화면이 된다.
  const activeKindFilter: KindFilter =
    kindFilter !== 'ALL' && kindCounts[kindFilter] === 0 ? 'ALL' : kindFilter

  const filteredRequests = useMemo(
    () =>
      confirmationRequests.filter(
        (request) =>
          activeKindFilter === 'ALL' || request.kind === activeKindFilter,
      ),
    [confirmationRequests, activeKindFilter],
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

  /**
   * 카드에서 바로 처리한다.
   *
   * 왜 확인 모달을 없앴는가
   *   버튼 하나를 누르는 데 모달 → 메모 입력 → 확인까지 세 단계였다. 그런데 처리 결과에는
   *   이미 되돌리기 토스트가 붙어 있다 — 잘못 눌러도 한 번 더 누르면 원래대로다. 되돌릴 수
   *   있는 일에 확인 창을 세우면, 정작 되돌릴 수 없는 일에 뜨는 확인 창도 같이 무시된다.
   *   메모 칸도 함께 걷어냈다. 처리한 항목은 목록에서 곧 사라지므로 아무도 그 메모를 다시
   *   읽지 않는다 — 쓰기만 하고 읽히지 않는 입력란이었다.
   *
   *   복약 충돌만 예외다. 그쪽은 의료 정보라 되돌리기로 충분하지 않고, 확정이 무엇을
   *   하지 <b>않는지</b>(복약 시간을 바꾸지 않는다)를 반드시 읽혀야 한다.
   */
  const resolve = async (
    request: ConfirmationRequest,
    resolution: DirectResolution,
  ): Promise<void> => {
    if (request.kind === 'MEDICATION_CONFLICT') {
      openResolutionDialog(request, resolution)
      return
    }

    try {
      await resolveConfirmationRequest(request.id, resolution)
      setUndoToast({
        open: true,
        message: RESOLUTION_COPY[resolution].completedMessage,
        tone: 'success',
        requestId: request.id,
      })
    } catch (requestError: unknown) {
      setUndoToast({
        open: true,
        message: messageFromError(requestError),
        tone: 'danger',
      })
    }
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

  /*
    탭은 "지금 목록에 들어 있는 종류"로만 만든다.

    왜 — 고정 5개였을 때 그중 셋(관심사·일정·복약 충돌)은 데이터가 없어서가 아니라
    <b>도달할 수 없어서</b> 언제나 0이었다. 관심사·일정 계열은 서버가 사람 확인 없이
    자동 반영하고(FactRiskPolicy.isSafeForAutoMaterialization), 복약 충돌은 로봇의
    분류표에 MEDICATION 자체가 없어 생성 경로가 없다. 그래서 이 화면에 실제로 올 수
    있는 것은 건강 한 종류뿐인데, 화면은 언제나 0을 세 개 띄우고 있었다 — 모바일에서는
    그 빈 탭들이 첫 화면의 절반을 먹었다.

    목록에서 파생시키면 백엔드 정책이 바뀌어 다른 종류가 올라오기 시작하는 날
    탭도 저절로 생긴다. 종류를 상수로 지우는 것보다 이쪽이 안전하다.

    종류가 하나뿐이면 탭 줄 자체를 그리지 않는다. 고를 것이 없는 필터는 정보가
    아니라 잡음이다.
  */
  const presentKinds = (
    ['INTEREST', 'SCHEDULE', 'HEALTH', 'MEDICATION_CONFLICT'] as const
  ).filter((kind) => kindCounts[kind] > 0)

  const kindTabs: readonly {
    value: KindFilter
    label: string
  }[] =
    presentKinds.length > 1
      ? [
          { value: 'ALL', label: '전체' },
          ...presentKinds.map((kind) => ({
            value: kind as KindFilter,
            label: KIND_LABELS[kind],
          })),
        ]
      : []

  const resolutionCopy = resolutionDialog
    ? RESOLUTION_COPY[resolutionDialog.resolution]
    : null
  const undoRequestId = undoToast.requestId

  return (
    <div className="page-stack confirmation-requests-page">
      {/*
        설명문을 목록이 비었을 때로 옮겼다(EmptyState). "대화에서 새롭게 파악한 정보는
        보호자가 확인한 뒤에만 확정 정보로 사용합니다"는 이 화면의 정책이지 오늘의
        할 일이 아니다. 매일 들어오는 사람에게 같은 정책 문장을 카드 위에 다시 읽히면,
        정작 그 아래 어르신의 말을 읽을 자리를 밀어낸다.
      */}
      <PageHeader
        title="확인할 일"
        metadata={
          <span>
            {pendingCount > 0
              ? `보미가 들은 이야기 ${pendingCount}건이 확인을 기다려요`
              : '지금은 확인할 일이 없어요'}
          </span>
        }
      />

      {/*
        "처리 상태" 드롭다운을 뺐다.
          세 선택지 중 둘("처리 완료"·"전체")은 언제나 빈 화면이었다. 이 화면이 받는
          목록은 서버가 대기 계열 3상태만 담아 보내기 때문이다
          (ConfirmationRequestService.PENDING_STATUSES). 처리한 건은 1초 폴링이
          곧바로 목록에서 지운다 — 조회할 방법 자체가 없다. 고를 수 없는 선택지를
          띄워 두면 보호자는 자기가 뭘 잘못 눌렀다고 생각한다.
          처리 직후의 되돌리기는 그대로 토스트가 맡는다.
      */}
      {kindTabs.length > 0 ? (
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
                    activeKindFilter === tab.value
                      ? ' confirmation-tabs__item--active'
                      : ''
                  }`}
                  type="button"
                  aria-pressed={activeKindFilter === tab.value}
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
          </div>
        </Card>
      ) : null}

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
          title="확인할 요청이 없습니다"
          description={
            activeKindFilter === 'ALL'
              ? '보미가 대화에서 새로 들은 이야기는 보호자가 확인한 뒤에만 기록으로 남아요. 새로 들은 이야기가 생기면 여기에 올라옵니다.'
              : '이 종류의 확인할 일이 없어요.'
          }
          action={
            activeKindFilter !== 'ALL' ? (
              <Button variant="secondary" onClick={() => setKindFilter('ALL')}>
                전체 보기
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
            const quote = spokenText(request)
            // 인용문도 없고 덧붙일 값도 없다 = 화면이 이 건의 내용을 하나도 못 읽었다.
            // 그 사실을 조용히 넘기지 않는다.
            const hasNothingToShow =
              quote === undefined &&
              visibleRows(request.proposedValue, QUOTE_KEYS).length === 0

            return (
              <li key={request.id}>
                <Card
                  compact
                  as="article"
                  className={`confirmation-card confirmation-card--${request.kind
                    .toLocaleLowerCase()
                    .replace('_', '-')}`}
                >
                  {/*
                    배지 세 개(종류·상태·민감도)를 뺐다.
                      셋 다 보호자가 무엇을 할지 바꾸지 않는다. 종류는 바로 아래 질문
                      문장이 이미 말하고("건강 관찰로 남길까요?"), 상태는 이 목록에
                      들어 있다는 사실이 곧 '확인 대기'이며, 민감도는 — 이게 핵심인데 —
                      정말 위험한 값(HIGH·조율 필요)일 때는 확정 버튼 자체가 사라지고
                      그 이유가 문장으로 뜬다. 즉 위험은 이미 배지가 아니라 버튼의
                      유무로 전해지고 있었고, 배지는 장식이었다.
                      조율 상태만은 행동을 바꾸므로 아래 guardrail 문장에 남긴다.
                  */}
                  <p className="confirmation-card__when">
                    {formatSpokenDateTime(request.createdAt)}
                    {request.origin === 'CONVERSATION'
                      ? ' · 보미와 이야기하다가'
                      : request.origin === 'ONBOARDING'
                        ? ' · 처음 등록할 때'
                        : ''}
                  </p>

                  {/*
                    어르신이 한 말을 카드의 주인공으로 올린다.
                      예전에는 같은 문장이 두 번 나왔다 — 서버 요약("'…'라고 말씀하셨습니다")과
                      값 패널("내용: …")이 같은 원문을 담고 있었기 때문이다. 원문이 있으면
                      그것만 큰 글씨로 인용하고, 요약은 접는다. 원문을 못 읽었을 때만
                      요약이 대신 나선다.
                  */}
                  {quote ? (
                    <blockquote className="confirmation-card__quote">
                      {quote}
                    </blockquote>
                  ) : (
                    <p className="confirmation-card__summary">
                      {request.summary}
                    </p>
                  )}

                  {hasNothingToShow ? (
                    <p className="value-panel__unreadable">
                      내용을 화면에 표시하지 못했어요. 남기기 전에 어르신께 직접
                      확인해 주세요.
                    </p>
                  ) : null}

                  {/* 원문 말고 더 있는 값(제목·일시·약 이름 등)만 덧붙인다. */}
                  <StructuredValuePanel
                    label="함께 확인할 내용"
                    value={request.proposedValue}
                    omitKeys={QUOTE_KEYS}
                  />
                  {request.currentValue !== undefined ? (
                    <StructuredValuePanel
                      label="지금 기록된 내용"
                      value={request.currentValue}
                      omitKeys={QUOTE_KEYS}
                    />
                  ) : null}

                  {request.kind === 'MEDICATION_CONFLICT' ? (
                    <MedicationSafetyNotice compact />
                  ) : null}

                  {isPending ? (
                    <>
                      <p className="confirmation-card__ask">
                        {request.question}
                      </p>
                      {canDirectlyResolve ? (
                        <div className="confirmation-card__actions">
                          <Button
                            size="small"
                            onClick={() => void resolve(request, 'CONFIRM')}
                            isLoading={isProcessing}
                            disabled={pendingActionId !== null && !isProcessing}
                          >
                            {ACTION_LABELS[request.kind].confirm}
                          </Button>
                          <Button
                            size="small"
                            variant="ghost"
                            onClick={() => void resolve(request, 'REJECT')}
                            disabled={pendingActionId !== null}
                          >
                            {ACTION_LABELS[request.kind].reject}
                          </Button>
                        </div>
                      ) : (
                        <p className="confirmation-card__guardrail" role="note">
                          {request.waitingReason
                            ? WAITING_REASON_COPY[request.waitingReason]
                            : showCoordination
                              ? COORDINATION_LABELS[request.coordinationStatus] +
                                ' 상태예요. 그 확인이 끝나야 남길 수 있어요.'
                              : '지금은 바로 남길 수 없어요. 어르신과 한 번 더 확인해 주세요.'}
                        </p>
                      )}
                      {/*
                        세 번째 선택지는 버튼에서 링크로 내렸다. 버튼 셋을 나란히 두면
                        무엇이 기본 동작인지 사라진다 — 보호자가 매번 셋을 다 읽어야 했다.
                      */}
                      {request.canRequestRecheck !== false ? (
                        <p className="confirmation-card__recheck">
                          잘 모르겠으면{' '}
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => void resolve(request, 'REASK')}
                            disabled={pendingActionId !== null}
                          >
                            보미가 다시 여쭤볼게요
                          </button>
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <div className="confirmation-card__resolution">
                      <strong>{STATUS_LABELS[request.status]}</strong>
                      {request.resolvedAt ? (
                        <span>{formatSpokenDateTime(request.resolvedAt)}</span>
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
