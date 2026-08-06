import { Badge, Button, Card, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type { RobotMode } from '../types/domain'
import { formatDateTime } from '../utils/date'

const MODE_COPY: Record<RobotMode, string> = {
  IDLE: '돌봄 대기 중',
  SCENARIO_ACTIVE: '돌봄 수행 중',
  REST_GUARD: '휴식 지킴 중',
  SAFE_STOP: '안전 정지 · 확인 필요',
  HOMECOMING: '귀가 맞이 중',
}

const isStale = (value: string | undefined, hours = 6): boolean => {
  if (!value) return false
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp > hours * 60 * 60 * 1000
}

export function BomiHomePage() {
  const { dashboard, isLoading, error, dataErrors, refresh } = useBomi()
  const dashboardError = dataErrors.dashboard ?? error
  if (isLoading && !dashboard) return <LoadingState label="보미와 집 정보를 확인하고 있어요" rows={5} />
  if (!dashboard) return <ErrorState description={dashboardError ?? undefined} onRetry={() => void refresh()} />

  const { robot, homeEnvironment } = dashboard
  const modeLabel = robot.currentMode ? MODE_COPY[robot.currentMode] : '현재 모드를 확인할 수 없어요.'
  const environmentIsStale = isStale(homeEnvironment.lastObservedAt)

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
          <span>{robot.id && robot.registrationActive ? '보미가 어르신 댁에 등록되어 있어요.' : '보미의 등록 상태를 확인 중이에요.'}</span>
        </div>
        <Badge tone={robot.currentMode === 'SAFE_STOP' ? 'danger' : robot.currentMode ? 'info' : 'neutral'}>
          {robot.currentMode === 'SAFE_STOP' ? '직접 확인 필요' : '모드 정보'}
        </Badge>
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

        <Card heading="집 상태" description="현관 사건 하나만으로 외출·귀가를 판단하지 않아요.">
          <div className="unknown-state-panel">
            <Badge tone="neutral">확인 중</Badge>
            <strong>현재 집 상태를 확인 중이에요.</strong>
            <p>확정된 재실 상태와 관찰 시각을 제공하는 Guardian DTO가 아직 연결되지 않았어요.</p>
          </div>
        </Card>

        <Card heading="최근 돌봄 수행" description="시나리오 내부 명령이나 원문은 표시하지 않아요.">
          <div className="unknown-state-panel">
            <Badge tone="neutral">아직 연결되지 않음</Badge>
            <strong>최근 수행 결과를 현재 확인할 수 없어요.</strong>
            <p>안전한 시나리오 상태·결과 API가 준비되면 이곳에 표시됩니다.</p>
          </div>
        </Card>

        <Card heading="제공하지 않는 정보" description="수집하거나 계약되지 않은 값을 만들어 보여주지 않아요.">
          <ul className="not-collected-list">
            <li>배터리·충전 상태</li>
            <li>실시간 위치·이동 경로</li>
            <li>영상·심박·낙상 확정</li>
          </ul>
        </Card>
      </section>
    </div>
  )
}
