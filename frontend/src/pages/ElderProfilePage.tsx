import { Badge, Button, Card, ErrorState, LoadingState, PageHeader } from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  AppUserStatus,
  ConsentStatus,
  OnboardingStatus,
} from '../types/domain'
import { formatDateTime } from '../utils/date'

const ONBOARDING_LABELS: Record<OnboardingStatus, string> = {
  NOT_STARTED: '시작 전',
  IN_PROGRESS: '진행 중',
  COMPLETED: '완료',
  DECLINED: '거부',
}

const STATUS_LABELS: Record<AppUserStatus, string> = {
  ACTIVE: '활성',
  SUSPENDED: '정지',
  WITHDRAWN: '탈퇴',
}

const CONSENT_LABELS: Record<ConsentStatus, string> = {
  NOT_ASKED: '미요청',
  GRANTED: '동의',
  DENIED: '거부',
  REVOKED: '철회',
}

const SPEECH_RATE_LABELS: Record<string, string> = {
  SLOW: '느리게',
  NORMAL: '보통',
  FAST: '빠르게',
}

const SPEECH_VOLUME_LABELS: Record<string, string> = {
  QUIET: '작게',
  NORMAL: '보통',
  LOUD: '크게',
}

function consentTone(status: ConsentStatus): 'success' | 'warning' | 'neutral' {
  if (status === 'GRANTED') return 'success'
  if (status === 'DENIED' || status === 'REVOKED') return 'warning'
  return 'neutral'
}

// 조회 전용 화면: app_user 기반 기본 정보만 표시한다.
// 건강정보·생년월일·성별 등은 스키마에 없어 표시하지 않으며, 편집은 제공하지 않는다.
export function ElderProfilePage() {
  const { elderProfile, isLoading, error, refresh } = useBomi()

  if (isLoading && !elderProfile) {
    return <LoadingState label="어르신 정보를 불러오는 중입니다" rows={5} />
  }

  if (!elderProfile) {
    return (
      <ErrorState
        title="어르신 정보를 불러오지 못했습니다"
        description={error ?? '잠시 후 다시 시도해 주세요.'}
        onRetry={() => void refresh()}
      />
    )
  }

  const { elder, conversationSettings } = elderProfile

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="돌봄 대상"
        title="어르신 정보"
        description="보미에 등록된 어르신의 기본 정보와 대화 설정입니다."
        metadata={<span>마지막 갱신 {formatDateTime(elder.updatedAt)}</span>}
        actions={
          <Button variant="secondary" onClick={() => void refresh()} isLoading={isLoading}>
            새로고침
          </Button>
        }
      />

      <Card heading="기본 정보">
        <dl className="detail-grid">
          <div>
            <dt>이름</dt>
            <dd>{elder.name}</dd>
          </div>
          <div>
            <dt>호칭</dt>
            <dd>{elder.preferredName}</dd>
          </div>
          <div>
            <dt>온보딩 상태</dt>
            <dd>{ONBOARDING_LABELS[elder.onboardingStatus]}</dd>
          </div>
          <div>
            <dt>계정 상태</dt>
            <dd>{STATUS_LABELS[elder.status]}</dd>
          </div>
        </dl>
      </Card>

      <Card heading="동의 상태" description="보미가 어르신 정보를 활용하기 위한 동의 항목입니다.">
        <ul className="consent-list">
          <li>
            <span>개인화</span>
            <Badge tone={consentTone(elder.personalizationConsentStatus)}>
              {CONSENT_LABELS[elder.personalizationConsentStatus]}
            </Badge>
          </li>
          <li>
            <span>건강 데이터</span>
            <Badge tone={consentTone(elder.healthDataConsentStatus)}>
              {CONSENT_LABELS[elder.healthDataConsentStatus]}
            </Badge>
          </li>
          <li>
            <span>일정</span>
            <Badge tone={consentTone(elder.scheduleConsentStatus)}>
              {CONSENT_LABELS[elder.scheduleConsentStatus]}
            </Badge>
          </li>
          <li>
            <span>보호자 공유</span>
            <Badge tone={consentTone(elder.guardianSharingConsentStatus)}>
              {CONSENT_LABELS[elder.guardianSharingConsentStatus]}
            </Badge>
          </li>
        </ul>
      </Card>

      <Card heading="대화 설정" description="로봇이 어르신과 대화할 때 적용하는 설정입니다.">
        <dl className="detail-grid">
          <div>
            <dt>말하기 속도</dt>
            <dd>
              {SPEECH_RATE_LABELS[conversationSettings.speechRate] ??
                conversationSettings.speechRate}
            </dd>
          </div>
          <div>
            <dt>음량</dt>
            <dd>
              {SPEECH_VOLUME_LABELS[conversationSettings.speechVolume] ??
                conversationSettings.speechVolume}
            </dd>
          </div>
          <div>
            <dt>반복 설명 필요</dt>
            <dd>{conversationSettings.needsRepeatedExplanation ? '필요' : '불필요'}</dd>
          </div>
        </dl>
      </Card>
    </div>
  )
}
