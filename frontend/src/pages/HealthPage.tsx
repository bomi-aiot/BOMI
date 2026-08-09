import { useMemo, useState, type FormEvent } from 'react'
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

  const activeMedicationCount = useMemo(
    () => medications.filter((medication) => medication.status === 'ACTIVE').length,
    [medications],
  )
  const activeReminderCount = useMemo(
    () =>
      medications.filter(
        (medication) =>
          medication.status === 'ACTIVE' &&
          medication.reminderEnabled &&
          medication.schedules.some((schedule) => schedule.isActive),
      ).length,
    [medications],
  )

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
        eyebrow="안전한 일상 지원"
        title="복약 관리"
        description="복약 정보와 복약 알림 상태를 관리합니다."
        actions={<Button onClick={openCreateModal}>복약 정보 추가</Button>}
      />

      <div className="medical-notice" role="note">
        <strong>의료 정보는 참고용입니다.</strong>
        <p>
          BOMI는 질환을 진단하거나 복약을 임의로 변경하지 않습니다. 약의 종류·용량·시간이
          달라졌다면 의료진 또는 약사와 먼저 확인해 주세요.
        </p>
      </div>

      <section className="summary-grid" aria-label="복약 현황 요약">
        <article className="summary-card summary-card--green">
          <p className="summary-card__label">활성 복약 정보</p>
          <strong className="summary-card__value">{medicationDataError ? '—' : `${activeMedicationCount}개`}</strong>
          <span className="summary-card__detail">{medicationDataError ? '복약 정보를 불러오지 못했어요' : '현재 관리 중으로 등록된 정보'}</span>
        </article>
        <article className="summary-card summary-card--blue">
          <p className="summary-card__label">오늘 응답 확인</p>
          <strong className="summary-card__value">
            {responseDataError ? '—' : `${medicationResponses.filter((item) => item.status === 'CONFIRMED').length}회`}
          </strong>
          <span className="summary-card__detail">{responseDataError ? '복약 응답을 불러오지 못했어요' : '로봇이 받은 응답 기록'}</span>
        </article>
        <article className="summary-card summary-card--orange">
          <p className="summary-card__label">응답 없음</p>
          <strong className="summary-card__value">
            {responseDataError ? '—' : `${medicationResponses.filter((item) => item.status === 'NO_RESPONSE').length}회`}
          </strong>
          <span className="summary-card__detail">{responseDataError ? '복약 응답을 불러오지 못했어요' : '응답이 아직 확인되지 않은 기록'}</span>
        </article>
        <article className="summary-card summary-card--lavender">
          <p className="summary-card__label">알림 켜짐</p>
          <strong className="summary-card__value">
            {medicationDataError ? '—' : `${activeReminderCount}개`}
          </strong>
          <span className="summary-card__detail">활성 복약 중 알림이 설정된 항목</span>
        </article>
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
                {medicationResponses.map((response) => (
                  <tr key={response.id}>
                    <td>{medications.find((item) => item.id === response.medicationId)?.name ?? '복약 정보 미확인'}</td>
                    <td>{formatTime(response.scheduledAt)}</td>
                    <td>
                      <Badge tone={responseTone[response.status]}>
                        {responseLabel[response.status]}
                      </Badge>
                    </td>
                    <td>{response.respondedAt ? formatTime(response.respondedAt) : '—'}</td>
                  </tr>
                ))}
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
