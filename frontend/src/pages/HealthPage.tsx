import { useState, type FormEvent } from 'react'
import {
  Badge,
  Button,
  Card,
  ConfirmModal,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
} from '../components'
import { useBomi } from '../state/BomiContext'
import type { Medication, MedicationResponseStatus } from '../types/domain'
import { formatTime } from '../utils/date'

interface HealthPageProps {
  onNavigate: (path: string) => void
}

interface MedicationFormValue {
  name: string
  dosage: string
  purpose: string
  instructions: string
  activeIngredient: string
  localTime: string
  reminderEnabled: boolean
}

const emptyMedicationForm: MedicationFormValue = {
  name: '',
  dosage: '',
  purpose: '',
  instructions: '',
  activeIngredient: '',
  localTime: '09:00',
  reminderEnabled: true,
}

const responseLabel: Record<MedicationResponseStatus, string> = {
  CONFIRMED: '복용했다고 응답했어요',
  NO_RESPONSE: '아직 응답이 확인되지 않았어요',
  UPCOMING: '복용 예정이에요',
  MISSED: '아직 응답이 확인되지 않았어요',
  DECLINED: '복용하지 않았다고 응답했어요',
  UNKNOWN: '응답 상태를 확인 중이에요',
}

/**
 * 알림이 꺼진 복약 슬롯에 쓰는 문구.
 *
 * 왜 필요한가 — 백엔드는 복약 스케줄의 오늘 시각을 전부 펼쳐 응답 목록으로 내려보내되,
 * 부모 기록의 reminderEnabled 는 보지 않는다. 반면 실제로 알림을 보내는 스케줄러는
 * 그 값이 꺼져 있으면 슬롯을 건너뛴다(MedicationReminderScheduler.remindIfDue).
 * 그래서 이 화면은 같은 약을 두고 위에서는 "알림 꺼짐", 아래 표에서는 "복용 예정이에요"
 * 라고 말하고 있었다 — 보호자는 보미가 물어볼 거라고 믿고 기다리게 된다.
 *
 * 응답 목록에 medicationId 가 실려 오고 이 화면은 복약 목록을 이미 들고 있으므로,
 * 계약을 바꾸지 않고 화면에서 두 사실을 맞출 수 있다.
 */
const REMINDER_OFF_LABEL = '알림이 꺼져 있어 보미가 묻지 않아요'

const responseTone: Record<
  MedicationResponseStatus,
  'success' | 'warning' | 'info' | 'danger' | 'neutral'
> = {
  CONFIRMED: 'success',
  NO_RESPONSE: 'warning',
  UPCOMING: 'info',
  MISSED: 'warning',
  DECLINED: 'neutral',
  UNKNOWN: 'neutral',
}

export function HealthPage({ onNavigate }: HealthPageProps) {
  const {
    elderProfile,
    medications,
    medicationResponses,
    isLoading,
    pendingActionId,
    error,
    dataErrors,
    refresh,
    addMedication,
    updateMedication,
    toggleMedicationReminder,
    deleteMedication,
  } = useBomi()
  const profileError = dataErrors.elderProfile ?? error
  const medicationDataError = dataErrors.medications
  const responseDataError = dataErrors.medicationResponses
  const [medicationModalOpen, setMedicationModalOpen] = useState(false)
  const [editingMedication, setEditingMedication] = useState<Medication | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Medication | null>(null)
  const [form, setForm] = useState<MedicationFormValue>(emptyMedicationForm)
  const [formError, setFormError] = useState('')
  const medicationActionId = editingMedication
    ? `medication-${editingMedication.id}`
    : 'medication-new'
  const isMedicationSubmitting = pendingActionId === medicationActionId

  // 이 슬롯에 대해 보미가 실제로 물어보는가. 복약 목록을 못 불러온 경우(undefined)에는
  // 아무 말도 하지 않는다 — 모르는 것을 "알림이 꺼졌다"고 단정하면 안 된다.
  const reminderSilentFor = (medicationId: string): boolean => {
    const medication = medications.find((item) => item.id === medicationId)
    if (!medication) return false
    return (
      medication.status !== 'ACTIVE' ||
      !medication.reminderEnabled ||
      !medication.schedules.some((schedule) => schedule.isActive)
    )
  }

  const todayTotal = medicationResponses.length
  const todayConfirmed = medicationResponses.filter(
    (item) => item.status === 'CONFIRMED',
  ).length
  const todaySilent = medicationResponses.filter(
    (item) =>
      item.status !== 'CONFIRMED' &&
      item.status !== 'DECLINED' &&
      reminderSilentFor(item.medicationId),
  ).length
  // MISSED 와 NO_RESPONSE 를 함께 센다 — 백엔드는 MISSED 만 보내고 FE 목 데이터는
  // NO_RESPONSE 를 쓴다. 한쪽만 세면 어느 한 환경에서 이 줄이 조용히 사라진다.
  // 알림이 꺼진 슬롯은 빼야 한다. 묻지 않았으니 응답이 없는 게 당연하다.
  const todayUnanswered = medicationResponses.filter(
    (item) =>
      (item.status === 'MISSED' || item.status === 'NO_RESPONSE') &&
      !reminderSilentFor(item.medicationId),
  ).length

  const openCreateModal = () => {
    setEditingMedication(null)
    setForm(emptyMedicationForm)
    setFormError('')
    setMedicationModalOpen(true)
  }

  const openEditModal = (medication: Medication) => {
    setEditingMedication(medication)
    setForm({
      name: medication.name,
      dosage: medication.dosage,
      purpose: medication.purpose ?? '',
      instructions: medication.instructions ?? '',
      activeIngredient: medication.activeIngredient ?? '',
      localTime: medication.schedules[0]?.localTimes[0] ?? '09:00',
      reminderEnabled: medication.reminderEnabled,
    })
    setFormError('')
    setMedicationModalOpen(true)
  }

  const handleMedicationSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!form.name.trim() || !form.dosage.trim() || !form.localTime) {
      setFormError('약 이름, 복용량, 복용 시간을 입력해 주세요.')
      return
    }

    setFormError('')
    try {
      if (editingMedication) {
        await updateMedication(editingMedication.id, {
          name: form.name.trim(),
          dosage: form.dosage.trim(),
          purpose: form.purpose.trim() || undefined,
          instructions: form.instructions.trim() || undefined,
          activeIngredient: form.activeIngredient.trim() || undefined,
          localTime: form.localTime,
          reminderEnabled: form.reminderEnabled,
        })
      } else {
        await addMedication({
          name: form.name.trim(),
          dosage: form.dosage.trim(),
          purpose: form.purpose.trim() || undefined,
          instructions: form.instructions.trim() || undefined,
          activeIngredient: form.activeIngredient.trim() || undefined,
          localTime: form.localTime,
          reminderEnabled: form.reminderEnabled,
          reminderLeadMinutes: 10,
        })
      }
      setMedicationModalOpen(false)
    } catch {
      setFormError('복약 정보를 저장하지 못했습니다. 입력 내용을 확인해 주세요.')
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMedication(deleteTarget.id)
      setDeleteTarget(null)
    } catch {
      // 전역 오류와 토스트가 구체적인 실패 사유를 안내한다.
    }
  }

  if (isLoading && !elderProfile) {
    return <LoadingState label="복약 정보를 불러오는 중입니다" rows={6} />
  }

  if (profileError && !elderProfile) {
    return <ErrorState description={profileError} onRetry={() => void refresh()} />
  }

  if (!elderProfile) {
    return (
      <EmptyState
        title="먼저 어르신 정보를 등록해 주세요"
        description="복약 정보는 돌봄 대상 등록 후 관리할 수 있습니다."
        action={<Button onClick={() => onNavigate('/elder/profile')}>어르신 등록하기</Button>}
      />
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="복약 관리"
        description="보미가 시간에 맞춰 여쭤보고, 어르신 대답을 여기에 모아드려요."
        actions={<Button onClick={openCreateModal}>복약 정보 추가</Button>}
      />

      <div className="medical-notice" role="note">
        <strong>의료 정보는 참고용입니다.</strong>
        <p>
          BOMI는 질환을 진단하거나 복약을 임의로 변경하지 않습니다. 약의 종류·용량·시간이
          달라졌다면 의료진 또는 약사와 먼저 확인해 주세요.
        </p>
      </div>

      {/*
        요약 숫자 네 개를 한 문장으로 줄였다.
          예전에는 활성 복약 정보 · 오늘 응답 확인 · 응답 없음 · 알림 켜짐 네 개가
          같은 크기로 나란히 있었다. 그중 둘(활성 복약 정보, 알림 켜짐)은 보호자가
          방금 자기 손으로 등록한 설정값이라 아침에 확인할 이유가 없고, 나머지 둘은
          서로의 여집합이라 한쪽만 알면 된다. 넷을 같은 크기로 두면 무엇이 오늘의
          소식인지 사라진다.

          보호자가 이 화면을 여는 이유는 하나다 — "오늘 약은 챙기셨나?"
          그 답을 한 줄로 먼저 말하고, 조치가 필요한 것(응답 없음)만 그 아래에
          예외적으로 덧붙인다. 0이면 아무 말도 하지 않는다 — 0을 굳이 보여 주면
          매일 읽어야 할 숫자가 다시 늘어난다.
      */}
      <section className="today-medication-summary" aria-label="오늘 복약 현황">
        {responseDataError ? (
          <p className="today-medication-summary__headline">
            오늘 복약 상황을 불러오지 못했어요.
          </p>
        ) : todayTotal === 0 ? (
          <p className="today-medication-summary__headline">
            오늘 예정된 복약이 없어요.
          </p>
        ) : (
          <>
            <p className="today-medication-summary__headline">
              오늘 복약 {todayTotal}번 중{' '}
              <strong>{todayConfirmed}번</strong> 확인됐어요.
            </p>
            {todayUnanswered > 0 ? (
              <p className="today-medication-summary__detail today-medication-summary__detail--warn">
                {todayUnanswered}번은 알림 시간이 지나도록 응답이 확인되지
                않았어요. 응답이 없다고 안 드신 것은 아니에요.
              </p>
            ) : null}
            {todaySilent > 0 ? (
              <p className="today-medication-summary__detail">
                {todaySilent}번은 알림이 꺼져 있어 보미가 여쭤보지 않아요.
              </p>
            ) : null}
          </>
        )}
      </section>

      {medicationDataError ? (
        <ErrorState
          title="복약 정보를 불러오지 못했어요"
          description={medicationDataError}
          onRetry={() => void refresh()}
        />
      ) : medications.length > 0 ? (
        <section className="medication-grid" aria-label="등록된 복약 정보">
          {medications.map((medication) => (
            <article
              className={`medication-card${
                medication.status !== 'ACTIVE' ? ' medication-card--paused' : ''
              }`}
              key={medication.id}
            >
              <div className="medication-card__header">
                <div>
                  <Badge
                    tone={
                      medication.status === 'ACTIVE'
                        ? 'success'
                        : medication.status === 'UNKNOWN'
                          ? 'warning'
                          : 'neutral'
                    }
                    dot
                  >
                    {medication.status === 'ACTIVE'
                      ? '복약 관리 중'
                      : medication.status === 'PAUSED'
                        ? '일시 중지'
                        : medication.status === 'ENDED'
                          ? '종료'
                          : '상태 확인 중'}
                  </Badge>
                  <h2 className="medication-card__title">{medication.name}</h2>
                </div>
                {/*
                  확인 상태 배지를 뺐다. care_record 에 verification_status 컬럼이 없고
                  MedicationDto 도 그 값을 싣지 않아, 매퍼가 'UNVERIFIED' 를 상수로 채우고
                  있었다 — 무엇을 등록하든 모든 약이 노란 "확인 필요"로 보였다.
                  DB 에 없는 상태를 화면이 단정하는 것이 배지가 없는 것보다 나쁘다.
                */}
              </div>
              <p className="medication-card__description">
                {medication.dosage}
                {medication.purpose ? ` · ${medication.purpose}` : ''}
              </p>
              <div className="medication-card__schedule">
                {medication.schedules.flatMap((schedule) =>
                  schedule.localTimes.map((time) => (
                    <span key={`${schedule.id}-${time}`}>{time} 복용</span>
                  )),
                )}
                <span>
                  {medication.status !== 'ACTIVE'
                    ? '알림 동작 안 함'
                    : medication.reminderEnabled &&
                        medication.schedules.some((schedule) => schedule.isActive)
                      ? '알림 설정됨'
                      : '알림 꺼짐'}
                </span>
              </div>
              <div className="medication-card__actions">
                <Button
                  variant="quiet"
                  size="small"
                  onClick={() => openEditModal(medication)}
                >
                  수정
                </Button>
                <Button
                  variant="secondary"
                  size="small"
                  isLoading={pendingActionId === `medication-${medication.id}`}
                  onClick={() => void toggleMedicationReminder(medication.id)}
                >
                  알림 {medication.reminderEnabled ? '끄기' : '켜기'}
                </Button>
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => setDeleteTarget(medication)}
                >
                  삭제
                </Button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <EmptyState
          title="등록된 복약 정보가 없습니다"
          description="처방전 또는 약 봉투를 확인한 뒤 보호자가 직접 등록해 주세요."
          action={<Button onClick={openCreateModal}>첫 복약 정보 추가</Button>}
          symbol="+"
        />
      )}

      <Card
        heading="오늘의 복약 응답"
        description="응답 없음은 미복용을 의미하지 않습니다. 필요할 때 어르신께 직접 확인해 주세요."
      >
        {responseDataError ? (
          <ErrorState compact description={responseDataError} onRetry={() => void refresh()} />
        ) : medicationResponses.length > 0 ? (
          <div
            className="medication-table-scroll"
            role="region"
            aria-label="오늘의 복약 응답 표"
            tabIndex={0}
          >
            <table className="medication-response-table">
              <caption className="sr-only">복약별 예정 시간과 어르신 응답</caption>
              <thead>
                <tr>
                  <th scope="col">복약</th>
                  <th scope="col">예정 시간</th>
                  <th scope="col">응답 상태</th>
                  <th scope="col">응답 시간</th>
                </tr>
              </thead>
              <tbody>
                {medicationResponses.map((response) => {
                  // 응답이 이미 있으면 알림 설정과 무관하게 그 응답이 사실이다.
                  // (보호자가 뒤늦게 알림을 껐어도 오늘 받은 응답은 남아야 한다.)
                  const answered =
                    response.status === 'CONFIRMED' ||
                    response.status === 'DECLINED'
                  const silent =
                    !answered && reminderSilentFor(response.medicationId)

                  return (
                    <tr key={response.id}>
                      <td>{medications.find((item) => item.id === response.medicationId)?.name ?? '복약 정보 미확인'}</td>
                      <td>{formatTime(response.scheduledAt)}</td>
                      <td>
                        <Badge tone={silent ? 'neutral' : responseTone[response.status]}>
                          {silent ? REMINDER_OFF_LABEL : responseLabel[response.status]}
                        </Badge>
                      </td>
                      <td>{response.respondedAt ? formatTime(response.respondedAt) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState compact title="오늘 전송된 복약 알림이 없습니다" />
        )}
      </Card>

      <Modal
        open={medicationModalOpen}
        title={editingMedication ? '복약 정보 수정' : '복약 정보 추가'}
        description="약 봉투 또는 처방 내용을 확인하고 입력해 주세요."
        onClose={() => {
          if (!isMedicationSubmitting) setMedicationModalOpen(false)
        }}
        closeOnBackdrop={!isMedicationSubmitting}
        closeOnEscape={!isMedicationSubmitting}
        closeDisabled={isMedicationSubmitting}
        size="medium"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setMedicationModalOpen(false)}
              disabled={isMedicationSubmitting}
            >
              취소
            </Button>
            <Button
              type="submit"
              form="medication-form"
              isLoading={isMedicationSubmitting}
            >
              {editingMedication ? '수정 저장' : '추가하기'}
            </Button>
          </>
        }
      >
        <form
          id="medication-form"
          className="form-grid"
          onSubmit={(event) => void handleMedicationSubmit(event)}
        >
          <label className="field">
            <span>약 이름 <em>필수</em></span>
            <input
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="예: 혈압약"
              required
            />
          </label>
          <label className="field">
            <span>복용량 <em>필수</em></span>
            <input
              value={form.dosage}
              onChange={(event) =>
                setForm((current) => ({ ...current, dosage: event.target.value }))
              }
              placeholder="예: 1정"
              required
            />
          </label>
          <label className="field">
            <span>복용 시간 <em>필수</em></span>
            <input
              type="time"
              value={form.localTime}
              onChange={(event) =>
                setForm((current) => ({ ...current, localTime: event.target.value }))
              }
              required
            />
          </label>
          <label className="field">
            <span>복용 목적</span>
            <input
              value={form.purpose}
              onChange={(event) =>
                setForm((current) => ({ ...current, purpose: event.target.value }))
              }
              placeholder="예: 혈압 조절"
            />
          </label>
          <label className="field">
            <span>성분명</span>
            <input
              value={form.activeIngredient}
              onChange={(event) =>
                setForm((current) => ({ ...current, activeIngredient: event.target.value }))
              }
            />
          </label>
          <label className="field field--wide">
            <span>복용 방법</span>
            <textarea
              value={form.instructions}
              onChange={(event) =>
                setForm((current) => ({ ...current, instructions: event.target.value }))
              }
              rows={3}
              placeholder="예: 아침 식사 후 물과 함께 복용"
            />
          </label>
          <label className="switch-field field--wide">
            <input
              type="checkbox"
              checked={form.reminderEnabled}
              onChange={(event) =>
                setForm((current) => ({ ...current, reminderEnabled: event.target.checked }))
              }
            />
            <span>
              <strong>보미 음성 복약 알림 사용</strong>
              <small>설정한 시간에 어르신께 복약 여부를 물어봅니다.</small>
            </span>
          </label>
          {formError ? (
            <p className="form-error field--wide" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      </Modal>

      <ConfirmModal
        open={Boolean(deleteTarget)}
        title="복약 정보를 삭제할까요?"
        description={`${deleteTarget?.name ?? '선택한 약'}의 알림과 향후 일정도 함께 제거됩니다. 실제 복약 중단 여부와는 무관합니다.`}
        confirmLabel="삭제"
        tone="danger"
        isLoading={Boolean(deleteTarget && pendingActionId === `medication-${deleteTarget.id}`)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  )
}
