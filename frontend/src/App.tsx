import { useEffect } from 'react'
import { MockDataNotice, Toast } from './components'
import { useRoute } from './hooks'
import { AppLayout } from './layouts'
import {
  BomiHomePage,
  CarePlanPage,
  ConfirmationRequestsPage,
  ConversationPreferencesPage,
  DashboardPage,
  ElderProfilePage,
  HealthPage,
  LandingPage,
  NotFoundPage,
  RecordsPage,
  SchedulesPage,
} from './pages'
import { BomiProvider, useBomi } from './state/BomiContext'
import { formatRelativeTime } from './utils/date'

const LOCAL_TOAST_ROUTES = new Set([
  '/elder/profile',
  '/conversation-preferences',
  '/confirmation-requests',
])

const ROUTE_TITLES: Record<string, string> = {
  '/': 'BOMI | 집의 하루가 안심으로 이어지는 길',
  '/dashboard': '오늘 | BOMI 보호자 센터',
  '/records': '생활 기록 | BOMI 보호자 센터',
  '/care-plan': '돌봄 계획 | BOMI 보호자 센터',
  '/confirmation-requests': '확인할 일 | BOMI 보호자 센터',
  '/bomi-home': '보미와 집 | BOMI 보호자 센터',
  '/elder/profile': '어르신 설정 | BOMI 보호자 센터',
  '/conversation-preferences': '공유된 생활 정보 | BOMI 보호자 센터',
  '/health': '복약 관리 | BOMI 보호자 센터',
  '/medications': '복약 관리 | BOMI 보호자 센터',
  '/schedules': '일정 관리 | BOMI 보호자 센터',
}

interface GuardianExperienceProps {
  pathname: string
  navigate: (path: string) => void
}

function GuardianExperience({ pathname, navigate }: GuardianExperienceProps) {
  const {
    dashboard,
    elderProfile,
    confirmationRequests,
    toast,
    isMockMode,
    apiBaseUrl,
    refresh,
    undoConfirmationRequest,
    clearToast,
  } = useBomi()

  const renderPage = () => {
    switch (pathname) {
      case '/dashboard':
        return <DashboardPage onNavigate={navigate} />
      case '/records':
        return <RecordsPage onNavigate={navigate} />
      case '/care-plan':
        return <CarePlanPage onNavigate={navigate} />
      case '/bomi-home':
        return <BomiHomePage />
      case '/elder/profile':
        return <ElderProfilePage />
      case '/conversation-preferences':
        return <ConversationPreferencesPage />
      case '/confirmation-requests':
        return <ConfirmationRequestsPage />
      case '/health':
      case '/medications':
        return <HealthPage onNavigate={navigate} />
      case '/schedules':
        return <SchedulesPage />
      default:
        return <NotFoundPage onNavigate={navigate} />
    }
  }

  const pendingConfirmationCount = confirmationRequests.filter(
    (request) => request.status === 'PENDING',
  ).length
  const safetyStatus =
    !dashboard || dashboard.safetyAlerts === null
      ? 'attention'
      : dashboard?.safetyAlerts && dashboard.safetyAlerts.length > 0
        ? 'danger'
        : 'normal'
  const lastObservedAt =
    dashboard?.elder.lastObservedAt ?? dashboard?.homeEnvironment.lastObservedAt

  return (
    <AppLayout
      pathname={pathname}
      onNavigate={navigate}
      selectedElderName={elderProfile?.elder.preferredName ?? '돌봄 대상 없음'}
      lastObservationLabel={
        lastObservedAt ? formatRelativeTime(lastObservedAt) : '관찰 시각 없음'
      }
      alertStatus={safetyStatus}
      alertStatusLabel={
        safetyStatus === 'danger'
          ? '즉시 확인 필요'
          : safetyStatus === 'attention'
            ? '알림 확인 필요'
            : dashboard
              ? '알림 조회됨'
              : '알림 확인 중'
      }
      notificationCount={pendingConfirmationCount}
      onRefresh={() => void refresh()}
      onNotificationsOpen={() => navigate('/confirmation-requests')}
      mockNotice={
        isMockMode ? (
          <MockDataNotice
            message="예시 데이터입니다. 실제 관찰·알림으로 해석하지 마세요. 저장·수정은 이 브라우저 세션에서만 유지됩니다."
            apiBaseUrl={apiBaseUrl}
          />
        ) : undefined
      }
    >
      {renderPage()}
      {toast && !LOCAL_TOAST_ROUTES.has(pathname) ? (
        <Toast
          open
          title={
            toast.tone === 'ERROR'
              ? '처리하지 못했습니다'
              : toast.tone === 'INFO'
                ? '안내'
                : '완료'
          }
          message={toast.message}
          tone={toast.tone === 'ERROR' ? 'danger' : toast.tone === 'INFO' ? 'info' : 'success'}
          actionLabel={toast.actionLabel}
          onAction={
            toast.actionRequestId
              ? () => void undoConfirmationRequest(toast.actionRequestId as string)
              : undefined
          }
          onDismiss={clearToast}
        />
      ) : null}
    </AppLayout>
  )
}

function App() {
  const { pathname, navigate } = useRoute()

  useEffect(() => {
    document.title = ROUTE_TITLES[pathname] ?? '페이지를 찾을 수 없음 | BOMI'
    const frame = window.requestAnimationFrame(() => {
      const main = document.getElementById(
        pathname === '/' ? 'landing-main' : 'main-content',
      )
      main?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [pathname])

  if (pathname === '/') {
    return <LandingPage onNavigate={navigate} />
  }

  return (
    <BomiProvider>
      <GuardianExperience pathname={pathname} navigate={navigate} />
    </BomiProvider>
  )
}

export default App
