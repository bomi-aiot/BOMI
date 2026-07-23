import { Badge, Button, Card, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  MedicationResponseStatus,
  Schedule,
  StatusLevel,
} from '../types/domain'

interface DashboardPageProps {
  onNavigate: (path: string) => void
}

const dateTimeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: 'short',
  day: 'numeric',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

const timeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
})

const statusTone = (status: StatusLevel): 'success' | 'warning' | 'danger' | 'neutral' => {
  if (status === 'NORMAL') return 'success'
  if (status === 'ATTENTION') return 'warning'
  if (status === 'DANGER') return 'danger'
  return 'neutral'
}

const medicationStatusLabel: Record<MedicationResponseStatus, string> = {
  CONFIRMED: '복용 확인',
  NO_RESPONSE: '응답 없음',
  UPCOMING: '예정',
  MISSED: '미복용',
  DECLINED: '복용 안 함',
}

const medicationStatusTone: Record<
  MedicationResponseStatus,
  'success' | 'warning' | 'info' | 'danger' | 'neutral'
> = {
  CONFIRMED: 'success',
  NO_RESPONSE: 'warning',
  UPCOMING: 'info',
  MISSED: 'danger',
  DECLINED: 'neutral',
}

function ScheduleRow({ schedule }: { schedule: Schedule }) {
  return (
    <li className="timeline-row">
      <time dateTime={schedule.startsAt} className="timeline-row__time">
        {timeFormatter.format(new Date(schedule.startsAt))}
      </time>
      <span className="timeline-row__marker" aria-hidden="true" />
      <div className="timeline-row__content">
        <strong>{schedule.title}</strong>
        <span>
          {[schedule.location, schedule.relatedPersonName].filter(Boolean).join(' · ') ||
            '장소 정보 없음'}
        </span>
      </div>
      <Badge tone={schedule.recordType === 'APPOINTMENT' ? 'info' : 'neutral'}>
        {schedule.recordType === 'APPOINTMENT' ? '진료' : '개인 일정'}
      </Badge>
    </li>
  )
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const { dashboard, isLoading, error, refresh } = useBomi()

  if (isLoading && !dashboard) {
    return <LoadingState label="오늘의 돌봄 정보를 불러오는 중입니다" rows={5} />
  }

  if (!dashboard) {
    return (
      <ErrorState
        title="대시보드 정보를 불러오지 못했습니다"
        description={error ?? '잠시 후 다시 시도해 주세요.'}
        onRetry={() => void refresh()}
      />
    )
  }

  const {
    elder,
    robot,
    homeEnvironment,
    todayIncidentCount,
    todaySchedules,
    medicationResponses,
    medicationProgress,
    confirmationRequests,
    recentActivities,
  } = dashboard

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="오늘의 돌봄 요약"
        title={`${elder.displayName}, 오늘도 편안하게 지내고 계세요`}
        description="보미가 수집한 오늘의 생활 정보와 보호자가 확인할 항목을 한눈에 모았습니다."
        metadata={
          <span>
            마지막 확인 {dateTimeFormatter.format(new Date(elder.lastCheckedAt))}
          </span>
        }
        actions={
          <Button variant="secondary" onClick={() => void refresh()} isLoading={isLoading}>
            새로고침
          </Button>
        }
      />

      <section className="summary-grid" aria-label="오늘의 핵심 상태">
        <article className="summary-card summary-card--green">
          <div className="summary-card__topline">
            <span className="summary-card__icon" aria-hidden="true">봄</span>
            <Badge tone={statusTone(elder.statusLevel)} dot>
              {elder.statusLabel}
            </Badge>
          </div>
          <p className="summary-card__label">어르신 상태</p>
          <strong className="summary-card__value">편안히 생활 중</strong>
          <span className="summary-card__detail">오늘 대화와 활동에서 특이사항이 없어요.</span>
        </article>

        <article className="summary-card summary-card--blue">
          <div className="summary-card__topline">
            <span className="summary-card__icon" aria-hidden="true">B</span>
            <Badge tone={robot.connectionStatus === 'ONLINE' ? 'success' : 'neutral'} dot>
              {robot.connectionStatus === 'ONLINE' ? '온라인' : '오프라인'}
            </Badge>
          </div>
          <p className="summary-card__label">돌봄 로봇</p>
          <strong className="summary-card__value">{robot.batteryLevel}%</strong>
          <span className="summary-card__detail">
            {robot.displayName} · {robot.currentMode === 'IDLE' ? '대기 중' : '돌봄 수행 중'}
          </span>
        </article>

        <article className="summary-card summary-card--orange">
          <div className="summary-card__topline">
            <span className="summary-card__icon" aria-hidden="true">!</span>
            <Badge tone={todayIncidentCount > 0 ? 'warning' : 'success'}>
              {todayIncidentCount > 0 ? '확인 필요' : '안정'}
            </Badge>
          </div>
          <p className="summary-card__label">오늘 발생한 이벤트</p>
          <strong className="summary-card__value">{todayIncidentCount}건</strong>
          <span className="summary-card__detail">
            {todayIncidentCount > 0 ? '보호자 확인을 기다리는 항목이 있어요.' : '긴급한 이벤트가 없어요.'}
          </span>
        </article>

        <article className="summary-card summary-card--lavender">
          <div className="summary-card__topline">
            <span className="summary-card__icon" aria-hidden="true">집</span>
            <Badge
              tone={homeEnvironment.sensorConnectionStatus === 'CONNECTED' ? 'success' : 'neutral'}
              dot
            >
              {homeEnvironment.sensorConnectionStatus === 'CONNECTED' ? '센서 연결' : '연결 끊김'}
            </Badge>
          </div>
          <p className="summary-card__label">집 안 환경</p>
          <strong className="summary-card__value">
            {homeEnvironment.temperatureC ?? '—'}℃
          </strong>
          <span className="summary-card__detail">
            습도 {homeEnvironment.humidityPercent ?? '—'}% · {homeEnvironment.label}
          </span>
        </article>
      </section>

      <div className="dashboard-columns">
        <div className="page-stack page-stack--compact">
          <Card
            heading="오늘 일정"
            description={`${todaySchedules.length}개의 일정이 예정되어 있어요.`}
            actions={
              <Button variant="quiet" size="small" onClick={() => onNavigate('/schedules')}>
                전체 보기
              </Button>
            }
          >
            {todaySchedules.length > 0 ? (
              <ol className="timeline-list">
                {todaySchedules.map((schedule) => (
                  <ScheduleRow key={schedule.id} schedule={schedule} />
                ))}
              </ol>
            ) : (
              <p className="inline-empty">오늘 예정된 일정이 없습니다.</p>
            )}
          </Card>

          <Card
            heading="오늘 복약"
            description={`${medicationProgress.confirmed}/${medicationProgress.total}회 복용을 확인했어요.`}
            actions={
              <Button variant="quiet" size="small" onClick={() => onNavigate('/medications')}>
                복약 관리
              </Button>
            }
          >
            <div
              className="progress-track"
              role="progressbar"
              aria-label="오늘 복약 진행률"
              aria-valuemin={0}
              aria-valuemax={medicationProgress.total}
              aria-valuenow={medicationProgress.confirmed}
            >
              <span
                style={{
                  width: `${
                    medicationProgress.total
                      ? (medicationProgress.confirmed / medicationProgress.total) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
            <ul className="compact-list">
              {medicationResponses.map((response) => (
                <li key={response.id}>
                  <div>
                    <strong>
                      {response.responseText?.split('·')[0]?.trim() ?? '복약 알림'}
                    </strong>
                    <span>{timeFormatter.format(new Date(response.scheduledAt))}</span>
                  </div>
                  <Badge tone={medicationStatusTone[response.status]}>
                    {medicationStatusLabel[response.status]}
                  </Badge>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="page-stack page-stack--compact">
          <Card
            className="attention-card"
            heading="보미가 확인을 기다려요"
            description="대화에서 새롭게 파악한 정보는 보호자가 확인해야 반영됩니다."
            actions={<Badge tone="warning">{dashboard.pendingConfirmationCount}건</Badge>}
          >
            <ul className="request-preview-list">
              {confirmationRequests.slice(0, 3).map((request) => (
                <li key={request.id}>
                  <span className="request-preview-list__kind">
                    {request.kind === 'MEDICATION_CONFLICT'
                      ? '복약'
                      : request.kind === 'SCHEDULE'
                        ? '일정'
                        : request.kind === 'HEALTH'
                          ? '건강'
                          : '관심사'}
                  </span>
                  <div>
                    <strong>{request.title}</strong>
                    <p>{request.summary}</p>
                  </div>
                </li>
              ))}
            </ul>
            <Button fullWidth onClick={() => onNavigate('/confirmation-requests')}>
              확인 요청 검토하기
            </Button>
          </Card>

          <Card
            heading="최근 대화에서 알게 된 것"
            description="다음 대화가 자연스럽도록 보미가 기억한 내용입니다."
          >
            <ul className="activity-list">
              {recentActivities.map((activity) => (
                <li key={activity.id}>
                  <span className="activity-list__dot" aria-hidden="true" />
                  <div>
                    <strong>{activity.title}</strong>
                    <p>{activity.summary}</p>
                    <time dateTime={activity.occurredAt}>
                      {dateTimeFormatter.format(new Date(activity.occurredAt))}
                    </time>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Card heading="빠른 작업" description="자주 쓰는 관리 기능으로 바로 이동합니다.">
        <div className="quick-action-grid">
          <button type="button" onClick={() => onNavigate('/elder/profile')}>
            <span aria-hidden="true">01</span>
            <strong>어르신 정보 수정</strong>
            <small>기본·건강·관심사 정보</small>
          </button>
          <button type="button" onClick={() => onNavigate('/conversation-preferences')}>
            <span aria-hidden="true">02</span>
            <strong>맞춤 대화 정보</strong>
            <small>보미가 기억할 내용 관리</small>
          </button>
          <button type="button" onClick={() => onNavigate('/medications')}>
            <span aria-hidden="true">03</span>
            <strong>복약 관리</strong>
            <small>약과 알림 상태 확인</small>
          </button>
          <button type="button" onClick={() => onNavigate('/schedules')}>
            <span aria-hidden="true">04</span>
            <strong>일정 등록</strong>
            <small>병원·개인 약속 추가</small>
          </button>
        </div>
      </Card>
    </div>
  )
}
