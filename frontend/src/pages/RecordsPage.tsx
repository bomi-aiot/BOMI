import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import { formatDateTime } from '../utils/date'

interface RecordsPageProps {
  onNavigate: (path: string) => void
}

export function RecordsPage({ onNavigate }: RecordsPageProps) {
  const {
    dashboard,
    conversationPreferences,
    isLoading,
    error,
    dataErrors,
    refresh,
  } = useBomi()
  const dashboardError = dataErrors.dashboard ?? error
  const recordsError = dataErrors.conversationPreferences ?? error

  if (isLoading && !dashboard) {
    return <LoadingState label="생활 기록을 확인하고 있어요" rows={5} />
  }
  if (!dashboard) {
    return <ErrorState description={dashboardError ?? undefined} onRetry={() => void refresh()} />
  }

  const sharedTopics = conversationPreferences.filter(
    (memory) =>
      memory.lifecycleStatus === 'ACTIVE' &&
      memory.memoryType !== 'CONVERSATION_SUMMARY' &&
      memory.memoryType !== 'EMOTIONAL_EVENT' &&
      (memory.visibility === 'SHARED_WITH_PRIMARY' ||
        memory.visibility === 'SHARED_WITH_GUARDIANS'),
  )

  return (
    <div className="page-stack records-page">
      <PageHeader
        eyebrow="생활 기록"
        title="하루의 흐름을 기록으로 살펴보세요."
        description="대화 원문이 아니라 보호자 공유가 허용된 돌봄 기록만 보여드려요."
      />

      {recordsError ? (
        <div className="page-inline-alert" role="alert">
          <span>{recordsError}</span>
          <Button variant="quiet" size="small" onClick={() => void refresh()}>다시 시도</Button>
        </div>
      ) : null}

      <Card heading="최근 돌봄 기록" description="관찰 시각과 함께 확인할 수 있는 기록이에요.">
        {dashboard.recentActivities === null ? (
          <div className="unavailable-panel">
            <Badge tone="neutral">아직 연결되지 않음</Badge>
            <strong>보호자 공유 기록을 현재 확인할 수 없어요.</strong>
            <p>공유 범위가 명시된 기록 계약이 준비되기 전에는 빈 기록으로 판단하지 않아요.</p>
          </div>
        ) : dashboard.recentActivities.length > 0 ? (
          <ol className="record-feed">
            {dashboard.recentActivities.map((activity) => (
              <li key={activity.id}>
                <div className="record-feed__time">
                  <time dateTime={activity.occurredAt}>{formatDateTime(activity.occurredAt)}</time>
                  <Badge tone="neutral">공유됨</Badge>
                </div>
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
            title="아직 보호자에게 공유할 생활 기록이 없어요"
            description="기록이 없다는 것이 활동이 없었다는 뜻은 아니에요."
          />
        )}
      </Card>

      <section className="records-grid">
        <Card
          heading="공유된 생활 주제"
          description="ACTIVE이면서 보호자 공유 범위가 확인된 정보만 표시해요."
          actions={<Button variant="quiet" size="small" onClick={() => onNavigate('/conversation-preferences')}>전체 보기</Button>}
        >
          {sharedTopics.length > 0 ? (
            <ul className="shared-topic-list">
              {sharedTopics.slice(0, 5).map((memory) => (
                <li key={memory.id}>
                  <strong>{memory.title}</strong>
                  <span>{memory.content}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="inline-empty">공유가 허용된 생활 주제가 아직 없어요.</p>
          )}
        </Card>

        <Card heading="생활 추세" description="일·주 단위 변화는 수집 가능 여부까지 확인돼야 해요.">
          <div className="unavailable-panel">
            <Badge tone="neutral">아직 연결되지 않음</Badge>
            <strong>생활 추세는 현재 보호자 API에서 확인할 수 없어요.</strong>
            <p>미측정 값을 0으로 바꾸거나 평소와 다르다고 추정하지 않아요.</p>
          </div>
        </Card>
      </section>
    </div>
  )
}
