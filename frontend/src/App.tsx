import { useEffect } from 'react'
import { MockDataNotice, Toast } from './components'
import { useRoute } from './hooks'
import { AppLayout } from './layouts'
import {
  ConfirmationRequestsPage,
  ConversationPreferencesPage,
  DashboardPage,
  ElderProfilePage,
  HealthPage,
  NotFoundPage,
  SchedulesPage,
} from './pages'
import { useBomi } from './state/BomiContext'
import { formatRelativeTime } from './utils/date'

const LOCAL_TOAST_ROUTES = new Set([
  '/elder/profile',
  '/conversation-preferences',
  '/confirmation-requests',
])

function App() {
  const { pathname, navigate } = useRoute()
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

  useEffect(() => {
    if (pathname === '/') {
      navigate('/dashboard', { replace: true })
    }
  }, [navigate, pathname])

  const renderPage = () => {
    switch (pathname) {
      case '/':
      case '/dashboard':
        return <DashboardPage onNavigate={navigate} />
      case '/elder/profile':
        return <ElderProfilePage />
      case '/conversation-preferences':
        return <ConversationPreferencesPage />
      case '/confirmation-requests':
        return <ConfirmationRequestsPage />
      case '/health':
        return <HealthPage initialTab="health" onNavigate={navigate} />
      case '/medications':
        return <HealthPage initialTab="medications" onNavigate={navigate} />
      case '/schedules':
        return <SchedulesPage />
      default:
        return <NotFoundPage onNavigate={navigate} />
    }
  }

  const pendingConfirmationCount = confirmationRequests.filter(
    (request) => request.status === 'PENDING',
  ).length
  const robotOnline = dashboard?.robot.connectionStatus === 'ONLINE'
  const sensorConnected =
    dashboard?.homeEnvironment.sensorConnectionStatus === 'CONNECTED'
  const systemNormal = robotOnline && sensorConnected

  return (
    <AppLayout
      pathname={pathname}
      onNavigate={navigate}
      selectedElderName={elderProfile?.elder.preferredName ?? '돌봄 대상 없음'}
      lastUpdatedLabel={
        dashboard?.generatedAt ? formatRelativeTime(dashboard.generatedAt) : '갱신 전'
      }
      systemStatus={systemNormal ? 'normal' : dashboard ? 'attention' : 'offline'}
      systemStatusLabel={
        systemNormal ? '시스템 정상' : dashboard ? '일부 연결 확인' : '연결 확인 중'
      }
      notificationCount={pendingConfirmationCount}
      guardianName="김보호"
      guardianRole="주 보호자"
      onRefresh={() => void refresh()}
      onNotificationsOpen={() => navigate('/confirmation-requests')}
      mockNotice={
        isMockMode ? (
          <MockDataNotice
            message="백엔드 연동 전 예시 데이터로 동작합니다. 저장·수정 작업은 브라우저 세션 안에서만 유지됩니다."
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

export default App
