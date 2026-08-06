import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type { MedicationResponseStatus } from '../types/domain'
import { formatDateTime, formatTime } from '../utils/date'

interface CarePlanPageProps {
  onNavigate: (path: string) => void
}

const RESPONSE_LABELS: Record<MedicationResponseStatus, string> = {
  CONFIRMED: '복용했다고 응답했어요.',
  DECLINED: '복용하지 않았다고 응답했어요.',
  UPCOMING: '복용 예정이에요.',
  NO_RESPONSE: '아직 응답이 확인되지 않았어요.',
  MISSED: '아직 응답이 확인되지 않았어요.',
  UNKNOWN: '응답 상태를 확인 중이에요.',
}

export function CarePlanPage({ onNavigate }: CarePlanPageProps) {
  const {
    dashboard,
    medications,
    medicationResponses,
    schedules,
    isLoading,
    error,
    dataErrors,
    refresh,
  } = useBomi()
  const dashboardError = dataErrors.dashboard ?? error
  const medicationDataError = dataErrors.medications
  const responseDataError = dataErrors.medicationResponses
  const scheduleDataError = dataErrors.schedules

  if (isLoading && !dashboard) return <LoadingState label="돌봄 계획을 확인하고 있어요" rows={6} />
  if (!dashboard) return <ErrorState description={dashboardError ?? undefined} onRetry={() => void refresh()} />

  const upcomingSchedules = schedules
    .filter((schedule) => schedule.status === 'UPCOMING')
    .sort((left, right) => left.startsAt.localeCompare(right.startsAt))
  const schedulesPendingStatus = schedules.filter(
    (schedule) => schedule.status === 'UNKNOWN',
  )
  const currentMedications = medications.filter(
    (medication) => medication.status !== 'ENDED',
  )

  return (
    <div className="page-stack care-plan-page">
      <PageHeader
        eyebrow="돌봄 계획"
        title="보미가 챙길 복약과 일정을 관리해요."
        description="등록된 계획과 로봇이 받은 응답을 구분해서 확인하세요."
      />

      <section className="care-plan-grid">
        <Card
          heading="복약"
          description="응답 기록은 실제 복용을 의학적으로 확인한 값이 아니에요."
          actions={<Button variant="quiet" size="small" onClick={() => onNavigate('/medications')}>복약 관리</Button>}
        >
          {medicationDataError ? (
            <ErrorState compact description={medicationDataError} onRetry={() => void refresh()} />
          ) : currentMedications.length > 0 ? (
            <ul className="plan-list">
              {currentMedications.map((medication) => {
                const response = medicationResponses.find((item) => item.medicationId === medication.id)
                return (
                  <li key={medication.id}>
                    <div><strong>{medication.name}</strong><span>{medication.dosage || '복용량 미확인'}</span></div>
                    <p>
                      {responseDataError
                        ? '오늘 복약 응답을 불러오지 못했어요.'
                        : response
                          ? `${formatTime(response.scheduledAt)} · ${RESPONSE_LABELS[response.status]}`
                          : '오늘 응답 정보가 아직 보미와 연결되지 않았어요.'}
                    </p>
                  </li>
                )
              })}
            </ul>
          ) : (
            <EmptyState compact title="등록된 복약 계획이 없어요" />
          )}
        </Card>

        <Card
          heading="일정"
          description="병원·개인 일정과 예정 시각을 보여드려요."
          actions={<Button variant="quiet" size="small" onClick={() => onNavigate('/schedules')}>일정 관리</Button>}
        >
          {scheduleDataError ? (
            <ErrorState compact description={scheduleDataError} onRetry={() => void refresh()} />
          ) : upcomingSchedules.length > 0 ? (
            <ul className="plan-list">
              {upcomingSchedules.slice(0, 6).map((schedule) => (
                <li key={schedule.id}>
                  <div><strong>{schedule.title}</strong><Badge tone={schedule.recordType === 'APPOINTMENT' ? 'info' : 'neutral'}>{schedule.recordType === 'APPOINTMENT' ? '진료' : '개인 일정'}</Badge></div>
                  <p>{formatDateTime(schedule.startsAt)}{schedule.location ? ` · ${schedule.location}` : ''}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact title="예정된 일정이 없어요" />
          )}
          {schedulesPendingStatus.length > 0 ? (
            <div className="status-unknown-note" role="note">
              <Badge tone="warning">상태 확인 중</Badge>
              <p>
                일정 {schedulesPendingStatus.length}개의 상태가 확인되지 않아 다음 계획으로 계산하지 않았어요.
              </p>
            </div>
          ) : null}
        </Card>
      </section>

      <Card heading="확인 전 정보" description="보미가 새로 들은 내용은 확인하기 전까지 계획에 자동 반영하지 않아요.">
        <div className="confirmation-callout">
          <div><strong>확인할 일이 {dashboard.pendingConfirmationCount}개 있어요.</strong><p>일정·복약 충돌·건강 정보 후보를 확정된 계획과 분리했습니다.</p></div>
          <Button onClick={() => onNavigate('/confirmation-requests')}>확인할 일 보기</Button>
        </div>
      </Card>
    </div>
  )
}
