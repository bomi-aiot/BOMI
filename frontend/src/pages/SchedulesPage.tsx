import { useMemo, useState, type FormEvent } from 'react'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
} from '../components'
import { useBomi } from '../state/BomiContext'
import type { Schedule, ScheduleType } from '../types/domain'
import {
  formatDateWithWeekday,
  formatTime,
  fromKoreanDateTimeLocalInput,
  isToday,
  toDateInputValue,
  toDateTimeLocalInputValue,
} from '../utils/date'

interface ScheduleFormValue {
  recordType: ScheduleType
  title: string
  startsAt: string
  location: string
  relatedPersonName: string
  description: string
  reminderEnabled: boolean
  reminderLeadMinutes: number
  followUpEnabled: boolean
  followUpQuestion: string
}

const createDefaultForm = (): ScheduleFormValue => {
  const start = new Date()
  start.setHours(start.getHours() + 1, 0, 0, 0)
  return {
    recordType: 'PERSONAL_SCHEDULE',
    title: '',
    startsAt: toDateTimeLocalInputValue(start),
    location: '',
    relatedPersonName: '',
    description: '',
    reminderEnabled: true,
    reminderLeadMinutes: 60,
    followUpEnabled: true,
    followUpQuestion: '일정은 잘 다녀오셨어요? 기분은 어떠셨어요?',
  }
}

const scheduleTypeLabel: Record<ScheduleType, string> = {
  APPOINTMENT: '병원·진료',
  PERSONAL_SCHEDULE: '개인 일정',
}

export function SchedulesPage() {
  const {
    elderProfile,
    schedules,
    isLoading,
    error,
    dataErrors,
    pendingActionId,
    refresh,
    addSchedule,
    updateSchedule,
  } = useBomi()
  const profileError = dataErrors.elderProfile ?? error
  const scheduleDataError = dataErrors.schedules
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [form, setForm] = useState<ScheduleFormValue>(createDefaultForm)
  const [formError, setFormError] = useState('')
  const [filter, setFilter] = useState<'UPCOMING' | 'ALL'>('UPCOMING')
  const scheduleActionId = editing ? `schedule-${editing.id}` : 'schedule-new'
  const isScheduleSubmitting = pendingActionId === scheduleActionId

  const visibleSchedules = useMemo(
    () =>
      schedules.filter((schedule) =>
        filter === 'UPCOMING' ? schedule.status === 'UPCOMING' : true,
      ),
    [filter, schedules],
  )

  const groupedSchedules = useMemo(() => {
    const groups = new Map<string, Schedule[]>()
    visibleSchedules.forEach((schedule) => {
      const key = toDateInputValue(schedule.startsAt)
      const current = groups.get(key) ?? []
      current.push(schedule)
      groups.set(key, current)
    })
    return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right))
  }, [visibleSchedules])

  const openCreate = () => {
    setEditing(null)
    setForm(createDefaultForm())
    setFormError('')
    setModalOpen(true)
  }

  const openEdit = (schedule: Schedule) => {
    setEditing(schedule)
    setForm({
      recordType: schedule.recordType,
      title: schedule.title,
      startsAt: toDateTimeLocalInputValue(schedule.startsAt),
      location: schedule.location ?? '',
      relatedPersonName: schedule.relatedPersonName ?? '',
      description: schedule.description ?? '',
      reminderEnabled: schedule.reminderEnabled,
      reminderLeadMinutes: schedule.reminderLeadMinutes,
      followUpEnabled: schedule.followUpEnabled,
      followUpQuestion: schedule.followUpQuestion ?? '',
    })
    setFormError('')
    setModalOpen(true)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!form.title.trim() || !form.startsAt) {
      setFormError('일정 이름과 시작 시간을 입력해 주세요.')
      return
    }

    setFormError('')
    let startsAt: string
    try {
      startsAt = fromKoreanDateTimeLocalInput(form.startsAt)
    } catch {
      setFormError('유효한 시작 날짜와 시간을 입력해 주세요.')
      return
    }
    const payload = {
      recordType: form.recordType,
      title: form.title.trim(),
      startsAt,
      description: form.description.trim() || undefined,
      location: form.location.trim() || undefined,
      relatedPersonName: form.relatedPersonName.trim() || undefined,
      reminderEnabled: form.reminderEnabled,
      reminderLeadMinutes: form.reminderLeadMinutes,
      followUpEnabled: form.followUpEnabled,
      followUpQuestion:
        form.followUpEnabled && form.followUpQuestion.trim()
          ? form.followUpQuestion.trim()
          : undefined,
    }

    try {
      if (editing) {
        await updateSchedule(editing.id, payload)
      } else if (elderProfile) {
        await addSchedule({
          elderId: elderProfile.elder.id,
          ...payload,
          sourceType: 'GUARDIAN',
          verificationStatus: 'GUARDIAN_CONFIRMED',
        })
      }
      setModalOpen(false)
    } catch {
      setFormError('일정을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }
  }

  if (isLoading && !elderProfile) {
    return <LoadingState label="일정을 불러오는 중입니다" rows={5} />
  }

  if (profileError && !elderProfile) {
    return <ErrorState description={profileError} onRetry={() => void refresh()} />
  }

  if (!elderProfile) {
    return (
      <EmptyState
        title="돌봄 대상이 등록되지 않았습니다"
        description="어르신 프로필을 먼저 등록한 뒤 일정을 관리해 주세요."
      />
    )
  }

  if (scheduleDataError && schedules.length === 0) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="약속을 잊지 않도록"
          title="일정 관리"
          description="등록된 병원 예약과 개인 약속을 관리해요."
        />
        <ErrorState
          title="일정을 불러오지 못했어요"
          description={scheduleDataError}
          onRetry={() => void refresh()}
        />
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="약속을 잊지 않도록"
        title="일정 관리"
        description="등록된 병원 예약과 개인 약속, 알림·사후 질문 설정을 관리해요."
        actions={<Button onClick={openCreate}>새 일정 추가</Button>}
      />

      <div className="toolbar">
        <div className="segmented-control" aria-label="일정 보기 필터">
          <button
            type="button"
            aria-pressed={filter === 'UPCOMING'}
            onClick={() => setFilter('UPCOMING')}
          >
            예정 일정
          </button>
          <button
            type="button"
            aria-pressed={filter === 'ALL'}
            onClick={() => setFilter('ALL')}
          >
            전체 일정
          </button>
        </div>
        <div className="toolbar__actions">
          <Badge tone="info">
            오늘 {schedules.filter((schedule) => isToday(schedule.startsAt)).length}개
          </Badge>
          <Badge tone="neutral">
            예정 {schedules.filter((schedule) => schedule.status === 'UPCOMING').length}개
          </Badge>
        </div>
      </div>

      {groupedSchedules.length > 0 ? (
        groupedSchedules.map(([date, dateSchedules]) => (
          <section className="schedule-day" key={date}>
            <div className="schedule-day__heading">
              <h2>{isToday(`${date}T12:00:00+09:00`) ? '오늘' : formatDateWithWeekday(date)}</h2>
              <span>{dateSchedules.length}개 일정</span>
            </div>
            <div className="schedule-day__list">
              {dateSchedules.map((schedule) => (
                <article className="schedule-card" key={schedule.id}>
                  <time className="schedule-card__time" dateTime={schedule.startsAt}>
                    {formatTime(schedule.startsAt)}
                  </time>
                  <div className="schedule-card__body">
                    <div className="schedule-card__header">
                      <div>
                        <Badge
                          tone={schedule.recordType === 'APPOINTMENT' ? 'info' : 'neutral'}
                        >
                          {scheduleTypeLabel[schedule.recordType]}
                        </Badge>
                        <h3 className="schedule-card__title">{schedule.title}</h3>
                      </div>
                      <Badge
                        tone={
                          schedule.status === 'COMPLETED'
                            ? 'success'
                            : schedule.status === 'CANCELLED'
                              ? 'neutral'
                              : schedule.status === 'UNKNOWN'
                                ? 'warning'
                                : 'info'
                        }
                        dot
                      >
                        {schedule.status === 'COMPLETED'
                          ? '완료'
                          : schedule.status === 'CANCELLED'
                            ? '취소'
                            : schedule.status === 'UNKNOWN'
                              ? '상태 확인 중'
                              : '예정'}
                      </Badge>
                    </div>
                    {schedule.description ? (
                      <p className="schedule-card__description">{schedule.description}</p>
                    ) : null}
                    <div className="schedule-card__meta">
                      {schedule.location ? <span>장소: {schedule.location}</span> : null}
                      {schedule.relatedPersonName ? (
                        <span>함께하는 사람: {schedule.relatedPersonName}</span>
                      ) : null}
                      <span>
                        알림:{' '}
                        {schedule.reminderEnabled
                          ? `${schedule.reminderLeadMinutes}분 전`
                          : '사용 안 함'}
                      </span>
                      {schedule.followUpEnabled ? <span>사후 안부 질문 사용</span> : null}
                    </div>
                  </div>
                  <div className="schedule-card__actions">
                    <Button variant="quiet" size="small" onClick={() => openEdit(schedule)}>
                      수정
                    </Button>
                    {schedule.status === 'UPCOMING' ? (
                      <>
                        <Button
                          variant="secondary"
                          size="small"
                          isLoading={pendingActionId === `schedule-${schedule.id}`}
                          onClick={() =>
                            void updateSchedule(schedule.id, { status: 'COMPLETED' })
                          }
                        >
                          완료
                        </Button>
                        <Button
                          variant="ghost"
                          size="small"
                          isLoading={pendingActionId === `schedule-${schedule.id}`}
                          onClick={() =>
                            void updateSchedule(schedule.id, { status: 'CANCELLED' })
                          }
                        >
                          취소
                        </Button>
                      </>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))
      ) : (
        <EmptyState
          title={filter === 'UPCOMING' ? '예정된 일정이 없습니다' : '등록된 일정이 없습니다'}
          description="새 일정을 추가하면 보미가 어르신께 미리 알려드릴 수 있습니다."
          action={<Button onClick={openCreate}>일정 추가하기</Button>}
          symbol="+"
        />
      )}

      <Modal
        open={modalOpen}
        title={editing ? '일정 수정' : '새 일정 추가'}
        description="어르신이 이해하기 쉬운 이름과 정확한 시간을 입력해 주세요."
        size="large"
        onClose={() => {
          if (!isScheduleSubmitting) setModalOpen(false)
        }}
        closeOnBackdrop={!isScheduleSubmitting}
        closeOnEscape={!isScheduleSubmitting}
        closeDisabled={isScheduleSubmitting}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setModalOpen(false)}
              disabled={isScheduleSubmitting}
            >
              취소
            </Button>
            <Button
              type="submit"
              form="schedule-form"
              isLoading={isScheduleSubmitting}
            >
              {editing ? '수정 저장' : '일정 추가'}
            </Button>
          </>
        }
      >
        <form id="schedule-form" className="form-grid" onSubmit={(event) => void handleSubmit(event)}>
          <label className="field">
            <span>일정 종류</span>
            <select
              value={form.recordType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  recordType: event.target.value as ScheduleType,
                }))
              }
            >
              <option value="PERSONAL_SCHEDULE">개인 일정</option>
              <option value="APPOINTMENT">병원·진료</option>
            </select>
          </label>
          <label className="field">
            <span>시작 일시 <em>필수</em></span>
            <input
              type="datetime-local"
              value={form.startsAt}
              onChange={(event) =>
                setForm((current) => ({ ...current, startsAt: event.target.value }))
              }
              required
            />
          </label>
          <label className="field field--wide">
            <span>일정 이름 <em>필수</em></span>
            <input
              value={form.title}
              onChange={(event) =>
                setForm((current) => ({ ...current, title: event.target.value }))
              }
              placeholder="예: 정형외과 진료, 손자 김미소 방문"
              required
            />
          </label>
          <label className="field">
            <span>장소</span>
            <input
              value={form.location}
              onChange={(event) =>
                setForm((current) => ({ ...current, location: event.target.value }))
              }
              placeholder="예: 한마음 정형외과"
            />
          </label>
          <label className="field">
            <span>관련된 사람</span>
            <input
              value={form.relatedPersonName}
              onChange={(event) =>
                setForm((current) => ({ ...current, relatedPersonName: event.target.value }))
              }
              placeholder="예: 김미소 손자"
            />
          </label>
          <label className="field field--wide">
            <span>메모</span>
            <textarea
              rows={3}
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({ ...current, description: event.target.value }))
              }
              placeholder="보미가 안내할 때 참고할 내용을 적어 주세요."
            />
          </label>
          <label className="switch-field">
            <input
              type="checkbox"
              checked={form.reminderEnabled}
              onChange={(event) =>
                setForm((current) => ({ ...current, reminderEnabled: event.target.checked }))
              }
            />
            <span>
              <strong>일정 미리 알림</strong>
              <small>보미가 음성으로 일정을 알려드립니다.</small>
            </span>
          </label>
          <label className="field">
            <span>얼마나 미리 알려드릴까요?</span>
            <select
              value={form.reminderLeadMinutes}
              disabled={!form.reminderEnabled}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  reminderLeadMinutes: Number(event.target.value),
                }))
              }
            >
              <option value={10}>10분 전</option>
              <option value={30}>30분 전</option>
              <option value={60}>1시간 전</option>
              <option value={120}>2시간 전</option>
              <option value={1440}>하루 전</option>
            </select>
          </label>
          <label className="switch-field field--wide">
            <input
              type="checkbox"
              checked={form.followUpEnabled}
              onChange={(event) =>
                setForm((current) => ({ ...current, followUpEnabled: event.target.checked }))
              }
            />
            <span>
              <strong>일정 이후 자연스럽게 안부 묻기</strong>
              <small>완료 여부와 그때의 기분을 다음 대화에서 물어봅니다.</small>
            </span>
          </label>
          {form.followUpEnabled ? (
            <label className="field field--wide">
              <span>사후 질문</span>
              <input
                value={form.followUpQuestion}
                onChange={(event) =>
                  setForm((current) => ({ ...current, followUpQuestion: event.target.value }))
                }
              />
            </label>
          ) : null}
          {formError ? (
            <p className="form-error field--wide" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      </Modal>
    </div>
  )
}
