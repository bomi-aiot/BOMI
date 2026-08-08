import { Badge, Button, Card, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type { RobotMode, ScenarioType } from '../types/domain'
import { formatDateTime, formatRelativeTime } from '../utils/date'

const MODE_COPY: Record<RobotMode, string> = {
  IDLE: '돌봄 대기 중',
  SCENARIO_ACTIVE: '돌봄 수행 중',
  REST_GUARD: '휴식 지킴 중',
  SAFE_STOP: '안전 정지 · 확인 필요',
}

/**
 * 시나리오 종류별 배너 문구.
 *
 * 모드만 쓰면 현관 인사·"보미야" 호출·복약 알림·산책이 전부 '돌봄 수행 중' 하나로
 * 뭉개진다. 보호자에게 "지금 무엇을 하고 있는지"는 "무언가 하고 있다"와 전혀 다른
 * 정보라 종류를 우선해 보여준다.
 *
 * FALL_RESPONSE·MANUAL_INTERACTION 은 백엔드에 값만 예약돼 있고 흐름이 없어서
 * 일부러 비워 둔다 — 없는 기능에 이름을 붙이면 있는 것처럼 보인다. 빠진 값은
 * 아래 modeLabel 이 모드 라벨로 폴백한다.
 */
const SCENARIO_COPY: Partial<Record<ScenarioType, string>> = {
  HOMECOMING: '귀가 맞이 중',
  WAKE_WORD_CALL: '부르심에 가는 중',
  MEDICATION_REMINDER: '복약 알림 중',
  WELLNESS_CHECK: '안부 확인 중',
  WALK: '산책 동행 중',
}

const isStale = (value: string | undefined, hours = 6): boolean => {
  if (!value) return false
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp > hours * 60 * 60 * 1000
}

export function BomiHomePage() {
  const { dashboard, isLoading, error, dataErrors, refresh, requestWalk, pendingActionId } = useBomi()
  const dashboardError = dataErrors.dashboard ?? error
  if (isLoading && !dashboard) return <LoadingState label="보미와 집 정보를 확인하고 있어요" rows={5} />
  if (!dashboard) return <ErrorState description={dashboardError ?? undefined} onRetry={() => void refresh()} />

  const { robot, homeEnvironment, safetyAlerts } = dashboard

  // 우선순위가 곧 의미다.
  //   1. SAFE_STOP 은 무엇을 하던 중이었든 이긴다 — 안전 상태가 시나리오 이름에
  //      가려지면 보호자가 조치가 필요한 상황을 놓친다.
  //   2. 진행 중인 시나리오가 있으면 그 종류를 보여준다.
  //   3. 없으면(또는 백엔드가 아직 이 필드를 안 주면) 기존 모드 라벨로 폴백한다.
  const scenarioLabel = robot.activeScenarioType
    ? SCENARIO_COPY[robot.activeScenarioType]
    : undefined
  const modeLabel =
    robot.currentMode === 'SAFE_STOP'
      ? MODE_COPY.SAFE_STOP
      : (scenarioLabel ??
        (robot.currentMode ? MODE_COPY[robot.currentMode] : '현재 모드를 확인할 수 없어요.'))
  const scenarioElapsed =
    robot.currentMode !== 'SAFE_STOP' && scenarioLabel && robot.activeScenarioStartedAt
      ? formatRelativeTime(robot.activeScenarioStartedAt)
      : undefined
  const environmentIsStale = isStale(homeEnvironment.lastObservedAt)
  // safetyAlerts 는 null(조회 실패)과 []( 성공했고 알림 없음)을 구분한다.
  // 조회 실패를 "알림 없음"으로 보여주면 보호자가 안심해 버린다 — 셋을 다르게 그린다.
  const hasUrgentAlert = Boolean(safetyAlerts && safetyAlerts.length > 0)

  // 산책 버튼은 지금 상태에서 의미 있는 동작 하나만 보여준다.
  //   산책 중이면 종료만, 대기 중이면 시작만. 둘 다 띄우면 발표자가 잘못 누른다.
  // SAFE_STOP·다른 시나리오 진행 중에는 어차피 백엔드가 거절하므로(IDLE_ONLY)
  // 버튼을 비활성화해 헛클릭을 막는다.
  const isWalking = robot.activeScenarioType === 'WALK'
  const walkAction = isWalking ? 'STOP' : 'START'
  const walkBusy = pendingActionId === `walk-${walkAction.toLowerCase()}`
  const walkDisabled =
    walkBusy ||
    !robot.deviceId ||
    (!isWalking && (robot.currentMode === 'SAFE_STOP' || Boolean(robot.activeScenarioType)))

  return (
    <div className="page-stack bomi-home-page">
      <PageHeader
        eyebrow="보미와 집"
        title="보미가 지금 맡은 돌봄"
        description="등록 정보, 현재 모드와 실제 관측값을 서로 다른 의미로 보여드려요."
        actions={<Button variant="secondary" onClick={() => void refresh()}>새로고침</Button>}
      />

      <section className="bomi-status-hero">
        <div className="bomi-status-hero__orb" aria-hidden="true"><span>B</span></div>
        <div>
          <p>현재 모드</p>
          <h2>{modeLabel}</h2>
          <span>
            {scenarioElapsed ? `${scenarioElapsed} 시작 · ` : ''}
            {robot.id && robot.registrationActive ? '보미가 어르신 댁에 등록되어 있어요.' : '보미의 등록 상태를 확인 중이에요.'}
          </span>
        </div>
        <div className="bomi-status-hero__actions">
          <Button
            variant={isWalking ? 'secondary' : 'primary'}
            disabled={walkDisabled}
            onClick={() => void requestWalk(walkAction)}
          >
            {walkBusy ? '요청 중…' : isWalking ? '산책 종료' : '산책 시작'}
          </Button>
          <Badge tone={robot.currentMode === 'SAFE_STOP' ? 'danger' : robot.currentMode ? 'info' : 'neutral'}>
            {robot.currentMode === 'SAFE_STOP' ? '직접 확인 필요' : '모드 정보'}
          </Badge>
        </div>
      </section>

      <section className="bomi-detail-grid">
        <Card heading="실내 환경" description="측정값과 마지막 측정 시각만 표시해요.">
          <dl className="environment-readings">
            <div><dt>온도</dt><dd>{homeEnvironment.temperatureC !== undefined ? `${homeEnvironment.temperatureC}℃` : '현재 확인할 수 없어요.'}</dd></div>
            <div><dt>습도</dt><dd>{homeEnvironment.humidityPercent !== undefined ? `${homeEnvironment.humidityPercent}%` : '현재 확인할 수 없어요.'}</dd></div>
          </dl>
          <p className="observation-note">
            {homeEnvironment.lastObservedAt
              ? `마지막 측정 ${formatDateTime(homeEnvironment.lastObservedAt)}${environmentIsStale ? ' · 이후 새 기록 없음' : ''}`
              : '마지막 측정 시각을 확인할 수 없어요.'}
          </p>
        </Card>

        {/*
          긴급 안전 알림. 보미가 통증·자해 신호를 감지해 보호자에게 올린 것이
          여기 뜬다(care_record GUARDIAN_ALERT). 1초 폴링으로 갱신되므로
          어르신이 말한 지 몇 초 안에 이 카드가 붉게 바뀐다.
        */}
        <Card
          className={hasUrgentAlert ? 'safety-alert-card safety-alert-card--urgent' : 'safety-alert-card'}
          heading="안전 알림"
          description="보미가 보호자에게 바로 알려야 한다고 판단한 것만 올라와요."
        >
          {safetyAlerts === null ? (
            <div className="unknown-state-panel">
              <Badge tone="neutral">확인 실패</Badge>
              <strong>긴급 알림을 확인하지 못했어요.</strong>
              <p>알림이 없다고 판단하지 않고 다시 조회해 주세요.</p>
            </div>
          ) : hasUrgentAlert ? (
            <div className="safety-alert-card__body" role="alert">
              <Badge tone="danger">즉시 확인 필요</Badge>
              <strong>지금 직접 확인이 필요해요.</strong>
              <ul className="safety-alert-list">
                {safetyAlerts.map((alert) => (
                  <li key={alert.id}>
                    <span>{alert.message}</span>
                    {alert.occurredAt ? (
                      <time dateTime={alert.occurredAt}>{formatRelativeTime(alert.occurredAt)}</time>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="safety-alert-card__body">
              <Badge tone="success">이상 없음</Badge>
              <strong>현재 도착한 긴급 알림은 없어요.</strong>
              <p>기록이 없다는 것이 아무 일도 없었다는 뜻은 아니에요.</p>
            </div>
          )}
        </Card>

      </section>
    </div>
  )
}
