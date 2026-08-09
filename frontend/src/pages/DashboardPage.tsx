import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  MedicationResponseStatus,
  RobotMode,
  Schedule,
} from '../types/domain'
import { formatDateTime, formatRelativeTime, formatTime } from '../utils/date'

interface DashboardPageProps {
  onNavigate: (path: string) => void
}

const ROBOT_MODE_COPY: Record<RobotMode, string> = {
  IDLE: '돌봄 대기 중',
  SCENARIO_ACTIVE: '돌봄 수행 중',
  REST_GUARD: '휴식 지킴 중',
  SAFE_STOP: '안전 정지 · 확인 필요',
}

const MEDICATION_RESPONSE_COPY: Record<MedicationResponseStatus, string> = {
  CONFIRMED: '복용했다고 응답했어요.',
  DECLINED: '복용하지 않았다고 응답했어요.',
  UPCOMING: '복용 예정이에요.',
  NO_RESPONSE: '아직 응답이 확인되지 않았어요.',
  MISSED: '아직 응답이 확인되지 않았어요.',
  UNKNOWN: '응답 상태를 확인 중이에요.',
}

const isStale = (value: string | undefined, hours = 6): boolean => {
  if (!value) return false
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp > hours * 60 * 60 * 1000
}

function ScheduleRow({ schedule }: { schedule: Schedule }) {
  return (
    <li className="care-row">
      <time dateTime={schedule.startsAt} className="care-row__time">
        {formatTime(schedule.startsAt)}
      </time>
      <span className="care-row__marker" aria-hidden="true" />
      <div className="care-row__content">
        <strong>{schedule.title}</strong>
        <span>
          {[schedule.location, schedule.relatedPersonName].filter(Boolean).join(' · ') ||
            '세부 장소는 등록되지 않았어요.'}
        </span>
      </div>
      <div className="care-row__badges">
        <Badge tone={schedule.recordType === 'APPOINTMENT' ? 'info' : 'neutral'}>
          {schedule.recordType === 'APPOINTMENT' ? '진료' : '개인 일정'}
        </Badge>
        {schedule.status === 'UNKNOWN' ? (
          <Badge tone="warning">상태 확인 중</Badge>
        ) : null}
      </div>
    </li>
  )
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const {
    dashboard,
    medications,
    isLoading,
    error,
    dataErrors,
    refresh,
  } = useBomi()
  const dashboardError = dataErrors.dashboard ?? error

  if (isLoading && !dashboard) {
    return <LoadingState label="정보를 확인하고 있어요" rows={6} />
  }

  if (!dashboard) {
    return (
      <ErrorState
        title="오늘의 돌봄 정보를 불러오지 못했어요"
        description={dashboardError ?? '잠시 후 다시 확인해 주세요.'}
        retryLabel="다시 확인하기"
        onRetry={() => void refresh()}
      />
    )
  }

  const {
    elder,
    robot,
    safetyAlerts,
    homeEnvironment,
    todaySchedules,
    medicationResponses,
    confirmationRequests,
    recentActivities,
  } = dashboard
  const pendingConfirmations = confirmationRequests.filter(
    (request) => request.status === 'PENDING',
  )
  const activeSchedules = todaySchedules
    .filter((schedule) => schedule.status !== 'CANCELLED')
    .sort((left, right) => left.startsAt.localeCompare(right.startsAt))
  const nextSchedule = activeSchedules.find(
    (schedule) => schedule.status === 'UPCOMING',
  )
  const nextMedication = medicationResponses.find(
    (response) => response.status === 'UPCOMING',
  ) ?? medicationResponses.find(
    (response) =>
      response.status === 'NO_RESPONSE' || response.status === 'MISSED',
  )
  const nextMedicationName = nextMedication
    ? medications.find((medication) => medication.id === nextMedication.medicationId)?.name
    : undefined
  const lastObservedAt = elder.lastObservedAt ?? homeEnvironment.lastObservedAt
  const observationIsStale = isStale(lastObservedAt)
  const hasUrgentAlert = safetyAlerts !== null && safetyAlerts.length > 0

  const careSummary = hasUrgentAlert
    ? '보미가 즉시 확인이 필요한 알림을 보냈어요.'
    : pendingConfirmations.length > 0
      ? `보미가 새 정보 ${pendingConfirmations.length}개를 확인해 달라고 했어요.`
      : recentActivities === null
        ? '최근 돌봄 기록은 현재 확인할 수 없어요.'
        : recentActivities.length > 0
        ? `보호자에게 공유된 돌봄 기록 ${recentActivities.length}건이 있어요.`
        : '오늘 보호자에게 공유된 돌봄 기록은 아직 없어요.'

  return (
    <div className="page-stack today-page">
      <PageHeader
        eyebrow="오늘"
        title={`${elder.displayName}의 오늘`}
        description="관찰된 기록을 기준으로 꼭 필요한 내용만 전해드려요."
        metadata={
          lastObservedAt ? (
            <span>
              마지막 관찰 · {formatDateTime(lastObservedAt)}
              {observationIsStale ? ' · 이후 새 기록 없음' : ''}
            </span>
          ) : (
            <span>마지막 관찰 시각을 확인할 수 없어요.</span>
          )
        }
        actions={
          <Button variant="secondary" onClick={() => void refresh()} isLoading={isLoading}>
            새로고침
          </Button>
        }
      />

      {safetyAlerts === null ? (
        <section className="alert-availability alert-availability--error" role="alert">
          <div>
            <strong>긴급 알림 정보를 확인하지 못했어요.</strong>
            <span>알림이 없다고 판단하지 않고 다시 조회해 주세요.</span>
          </div>
          <Button variant="secondary" size="small" onClick={() => void refresh()}>
            다시 확인하기
          </Button>
        </section>
      ) : hasUrgentAlert ? (
        <section className="urgent-care-alert" role="alert" aria-labelledby="urgent-alert-title">
          <div className="urgent-care-alert__icon" aria-hidden="true">!</div>
          <div className="urgent-care-alert__copy">
            <p>즉시 안전 확인 요청</p>
            <h2 id="urgent-alert-title">지금 직접 확인이 필요해요.</h2>
            <ul>
              {safetyAlerts.map((alert) => (
                <li key={alert.id}>
                  <span>{alert.message}</span>
                  {alert.occurredAt ? (
                    <time dateTime={alert.occurredAt}>
                      {formatRelativeTime(alert.occurredAt)}
                    </time>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
          {/*
            전화 버튼을 뺐다. app_user 에 phone 컬럼이 없어(마이그레이션 V1~V20 전수 확인)
            매퍼가 채울 값 자체가 없었고, 실서버에서는 한 번도 뜬 적이 없는 분기였다.
            없는 연락처로 "전화하기"를 그리는 것보다 직접 확인하라고 말하는 편이 정직하다.
          */}
          <p className="urgent-care-alert__contact-note" role="note">
            평소 사용하던 연락 수단으로 어르신께 직접 확인해 주세요.
          </p>
        </section>
      ) : (
        <section className="alert-availability" aria-label="긴급 알림 조회 결과">
          <span className="alert-availability__mark" aria-hidden="true">✓</span>
          <div>
            <strong>현재 도착한 긴급 알림은 없어요.</strong>
            <span>
              {lastObservedAt
                ? `마지막 관찰 · ${formatRelativeTime(lastObservedAt)}`
                : '관찰 시각은 현재 확인할 수 없어요.'}
            </span>
          </div>
        </section>
      )}

      <section className="today-primary-grid" aria-label="오늘의 핵심 돌봄 정보">
        <Card
          className="today-summary-card"
          heading="오늘의 돌봄 요약"
          description={lastObservedAt ? `근거 기록 · ${formatDateTime(lastObservedAt)}` : '근거 시각 미확인'}
        >
          <p className="today-summary-card__statement">{careSummary}</p>
          <p className="today-summary-card__note">
            기록이 없다는 것이 활동이 없었다는 뜻은 아니에요.
          </p>
        </Card>

        <Card
          className="next-care-card"
          heading="다음 돌봄"
          actions={
            <Button variant="quiet" size="small" onClick={() => onNavigate('/care-plan')}>
              돌봄 계획 보기
            </Button>
          }
        >
          {nextSchedule || nextMedication ? (
            <ul className="next-care-list">
              {nextSchedule ? (
                <li>
                  <span>일정</span>
                  <strong>{formatTime(nextSchedule.startsAt)} · {nextSchedule.title}</strong>
                </li>
              ) : null}
              {nextMedication ? (
                <li>
                  <span>복약 응답</span>
                  <strong>
                    {formatTime(nextMedication.scheduledAt)} · {nextMedicationName ?? '복약 알림'}
                  </strong>
                  <small>{MEDICATION_RESPONSE_COPY[nextMedication.status]}</small>
                </li>
              ) : null}
            </ul>
          ) : (
            <p className="inline-empty">현재 확인할 수 있는 다음 일정이나 복약 알림이 없어요.</p>
          )}
        </Card>
      </section>

      <Card
        className="guardian-action-card"
        heading="보호자가 확인할 일"
        description={
          pendingConfirmations.length > 0
            ? `확인할 일이 ${pendingConfirmations.length}개 있어요. 확인 후 돌봄 계획에 반영됩니다.`
            : '지금 확인할 일은 없어요.'
        }
        actions={
          pendingConfirmations.length > 0 ? (
            <Badge tone="warning">{pendingConfirmations.length}개</Badge>
          ) : (
            <Badge tone="success">확인 완료</Badge>
          )
        }
      >
        {pendingConfirmations.length > 0 ? (
          <>
            <ul className="confirmation-preview">
              {pendingConfirmations.slice(0, 3).map((request) => (
                <li key={request.id}>
                  <span>{request.kind === 'SCHEDULE' ? '일정' : request.kind === 'MEDICATION_CONFLICT' ? '복약' : request.kind === 'HEALTH' ? '건강' : '생활 정보'}</span>
                  <strong>{request.title}</strong>
                  <p>{request.summary}</p>
                </li>
              ))}
            </ul>
            <Button onClick={() => onNavigate('/confirmation-requests')}>
              확인할 일 살펴보기
            </Button>
          </>
        ) : (
          <p className="inline-empty">새로운 확인 요청이 도착하면 이곳에 먼저 알려드릴게요.</p>
        )}
      </Card>

      <section className="today-secondary-grid">
        <Card
          heading="보미가 함께한 오늘"
          description="보호자 공유가 허용된 의미 있는 기록만 보여드려요."
          actions={
            <Button variant="quiet" size="small" onClick={() => onNavigate('/records')}>
              생활 기록 보기
            </Button>
          }
        >
          {recentActivities === null ? (
            <div className="unavailable-panel">
              <Badge tone="neutral">아직 연결되지 않음</Badge>
              <strong>보호자 공유 기록을 현재 확인할 수 없어요.</strong>
              <p>공유 범위가 확인되는 API 계약이 준비되기 전에는 기록 없음으로 표시하지 않아요.</p>
            </div>
          ) : recentActivities.length > 0 ? (
            <ol className="care-timeline">
              {recentActivities.slice(0, 4).map((activity) => (
                <li key={activity.id}>
                  <time dateTime={activity.occurredAt}>{formatTime(activity.occurredAt)}</time>
                  <span aria-hidden="true" />
                  <div>
                    <strong>{activity.title}</strong>
                    <p>{activity.summary}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState
              compact
              title="아직 기록된 돌봄 활동이 없어요"
              description="기록이 없다는 것이 활동이 없었다는 뜻은 아니에요."
            />
          )}
        </Card>

        <Card
          heading="보미와 집"
          description="등록 상태, 현재 모드와 마지막 환경 관측을 구분해 보여드려요."
          actions={
            <Button variant="quiet" size="small" onClick={() => onNavigate('/bomi-home')}>
              자세히 보기
            </Button>
          }
        >
          <dl className="bomi-home-summary">
            <div>
              <dt>보미 등록</dt>
              <dd>{robot.id && robot.registrationActive ? '어르신 댁에 등록되어 있어요.' : '등록 상태를 확인 중이에요.'}</dd>
            </div>
            <div>
              <dt>현재 모드</dt>
              <dd>{robot.currentMode ? ROBOT_MODE_COPY[robot.currentMode] : '현재 모드를 확인할 수 없어요.'}</dd>
            </div>
            <div>
              <dt>실내 환경</dt>
              <dd>
                {homeEnvironment.temperatureC !== undefined
                  ? `온도 ${homeEnvironment.temperatureC}℃${homeEnvironment.humidityPercent !== undefined ? ` · 습도 ${homeEnvironment.humidityPercent}%` : ''}`
                  : '현재 확인할 수 없어요.'}
              </dd>
              {homeEnvironment.lastObservedAt ? (
                <small>
                  마지막 측정 {formatDateTime(homeEnvironment.lastObservedAt)}
                  {isStale(homeEnvironment.lastObservedAt) ? ' · 이후 새 기록 없음' : ''}
                </small>
              ) : null}
            </div>
            <div>
              <dt>집 상태</dt>
              <dd>현재 집 상태를 확인 중이에요.</dd>
              <small>확정된 재실 정보가 보호자 API에 연결되기 전에는 추정하지 않아요.</small>
            </div>
          </dl>
        </Card>
      </section>

      <Card heading="오늘의 일정" description="등록된 일정만 시간순으로 보여드려요.">
        {activeSchedules.length > 0 ? (
          <ol className="care-list">
            {activeSchedules.map((schedule) => (
              <ScheduleRow key={schedule.id} schedule={schedule} />
            ))}
          </ol>
        ) : (
          <p className="inline-empty">오늘 확인된 일정이 없어요.</p>
        )}
      </Card>
    </div>
  )
}
