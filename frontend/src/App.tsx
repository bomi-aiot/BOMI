import { useEffect } from 'react'
import { MockDataNotice, Toast } from './components'
import { useRoute } from './hooks'
import { AppLayout } from './layouts'
import {
  ConversationPreferencesPage,
  ElderProfilePage,
  GuardianOnePage,
  LandingPage,
  NotFoundPage,
  ONE_PAGE_SECTIONS,
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
  '/elder/profile': '어르신 설정 | BOMI 보호자 센터',
  '/conversation-preferences': '공유된 생활 정보 | BOMI 보호자 센터',
}
const ONE_PAGE_TITLE = 'BOMI 보호자 센터'

/** 주소가 가리키는 구역. 한 장짜리 화면에서 라우트가 하는 유일한 일이다. */
const ROUTE_SECTIONS: Record<string, string> = {
  '/confirmation-requests': ONE_PAGE_SECTIONS.confirmations,
  '/bomi-home': ONE_PAGE_SECTIONS.bomi,
  '/health': ONE_PAGE_SECTIONS.medications,
  '/medications': ONE_PAGE_SECTIONS.medications,
  '/schedules': ONE_PAGE_SECTIONS.schedules,
}

/**
 * 구역으로 데려간다.
 *
 * 화면이 하나가 됐으므로 "이동"은 페이지 전환이 아니라 스크롤이다. 헤더의 종 아이콘과
 * 위급 토스트의 "지금 확인하기"가 모두 이 경로를 쓴다 — 예전에는 navigate() 로 다른
 * 화면을 열었고, 그래서 이미 그 화면에 있으면 아무 일도 일어나지 않았다.
 */
const scrollToSection = (sectionId: string): void => {
  const target = document.getElementById(sectionId)
  if (!target) return
  // 부드러운 스크롤을 쓰지 않는다 — 1초 폴링이 그 사이에 다시 렌더하면 애니메이션이
  // 취소되고 화면이 제자리에 멈춘다. 실제로 그렇게 눌러도 아무 일이 없었다.
  // scrollIntoView + scroll-margin 조합은 새로고침 시 브라우저의 자동
  // 스크롤 복원에 다시 덮여쓰였다. 실제 sticky 헤더 높이를 측정해
  // 절대 좌표로 이동하면 화면 크기가 달라져도 카드가 헤더 뒤로 숨지 않는다.
  const header = document.querySelector<HTMLElement>('.app-header')
  const headerHeight = header?.getBoundingClientRect().height ?? 0
  const targetTop = target.getBoundingClientRect().top + window.scrollY
  window.scrollTo({
    top: Math.max(0, targetTop - headerHeight - 20),
    behavior: 'auto',
  })
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
    isLoading,
    isMockMode,
    apiBaseUrl,
    refresh,
    undoConfirmationRequest,
    clearToast,
  } = useBomi()

  useEffect(() => {
    if (isLoading) return

    const section = ROUTE_SECTIONS[pathname]
    if (!section) return

    // 브라우저의 스크롤 복원은 첫 렌더의 scrollIntoView 뒤에
    // 돌아올 수 있다. 데이터까지 그려진 뒤 다시 맞춰야 고정 헤더 뒤로
    // 카드 상단이 숨지 않고, 확인 영역 전체가 한 화면에 들어온다.
    const frame = window.requestAnimationFrame(() => scrollToSection(section))
    return () => window.cancelAnimationFrame(frame)
  }, [isLoading, pathname])

  const isEmergencyToast = toast?.tone === 'EMERGENCY'

  /*
    화면 하나로 합쳤다.
      메뉴가 사라졌으므로 라우트도 "무엇을 그릴까"가 아니라 "어디로 스크롤할까"만
      결정한다. 기존 주소(/medications, /confirmation-requests …)를 살려 두는 이유는
      북마크와 시연 대본이 그 주소를 쓰고 있기 때문이다 — 주소는 그대로 두고
      도착지만 같은 페이지의 다른 구역으로 바꾼다.

      대본 밖 화면(오늘·생활 기록·돌봄 계획·어르신 설정·공유된 생활 정보)은
      네비게이션에서 이미 빠져 있었고, 이제 한 장으로 합치면서 진입점도 사라진다.
      컴포넌트는 지우지 않고 남겨 둔다 — 스프린트가 끝나면 되살릴 화면들이다.
  */
  const renderPage = () => {
    switch (pathname) {
      case '/elder/profile':
        return <ElderProfilePage />
      case '/conversation-preferences':
        return <ConversationPreferencesPage />
      case '/dashboard':
      case '/records':
      case '/care-plan':
      case '/bomi-home':
      case '/confirmation-requests':
      case '/health':
      case '/medications':
      case '/schedules':
        return <GuardianOnePage onNavigate={navigate} />
      default:
        return <NotFoundPage onNavigate={navigate} />
    }
  }

  const pendingConfirmationCount = confirmationRequests.filter(
    (request) => request.status === 'PENDING',
  ).length
  const lastObservedAt =
    dashboard?.elder.lastObservedAt ?? dashboard?.homeEnvironment.lastObservedAt

  return (
    <AppLayout
      selectedElderName={elderProfile?.elder.preferredName ?? '돌봄 대상 없음'}
      lastObservationLabel={
        lastObservedAt ? formatRelativeTime(lastObservedAt) : '관찰 시각 없음'
      }
      /*
        상단 상태 배지('알림 조회됨')를 뺐다.
          "조회됨"은 개발자가 자기 코드를 설명한 말이지 보호자의 상태가 아니다. 게다가
          같은 사실을 아래 안전 알림 카드가 이미 문장으로 말하고 있어서, 헤더의 배지는
          같은 말을 알아듣기 어려운 형태로 한 번 더 하는 자리였다. 위급 상황에서는
          위급 토스트와 붉은 안전 알림 카드가 맡는다.
      */
      guardianName={dashboard?.guardian?.name}
      guardianRole={
        dashboard?.guardian?.priority === 'PRIMARY' ? '1차 보호자' : undefined
      }
      notificationCount={pendingConfirmationCount}
      onRefresh={() => void refresh()}
      onNotificationsOpen={() => scrollToSection(ONE_PAGE_SECTIONS.confirmations)}
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
      {/*
        LOCAL_TOAST_ROUTES 는 그 화면이 자기 토스트를 따로 그리므로 전역 토스트를
        접어 두는 목록이다. 위급 알림만은 그 규칙에서 빼야 한다 — 어르신 설정
        화면을 열어 둔 채로 위급이 도착했는데 아무것도 안 뜨는 것이 최악이다.
      */}
      {toast && (isEmergencyToast || !LOCAL_TOAST_ROUTES.has(pathname)) ? (
        <Toast
          open
          emphasis={isEmergencyToast ? 'critical' : 'normal'}
          title={
            isEmergencyToast
              ? '위급 상황'
              : toast.tone === 'ERROR'
                ? '처리하지 못했습니다'
                : toast.tone === 'INFO'
                  ? '안내'
                  : '완료'
          }
          message={toast.message}
          tone={
            isEmergencyToast || toast.tone === 'ERROR'
              ? 'danger'
              : toast.tone === 'INFO'
                ? 'info'
                : 'success'
          }
          // 위급은 5초로 사라지면 안 된다. 자리를 비운 사이 지나가 버리면
          // 알린 적이 없는 것과 같다. 20초 두고, 그동안 안전 알림 카드가
          // 같은 내용을 계속 들고 있다.
          durationMs={isEmergencyToast ? 20000 : undefined}
          actionLabel={isEmergencyToast ? '지금 확인하기' : toast.actionLabel}
          onAction={
            isEmergencyToast
              ? () => scrollToSection(ONE_PAGE_SECTIONS.bomi)
              : toast.actionRequestId
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
    const previous = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    return () => {
      window.history.scrollRestoration = previous
    }
  }, [])

  useEffect(() => {
    document.title =
      ROUTE_TITLES[pathname] ??
      (ROUTE_SECTIONS[pathname] || pathname === '/dashboard'
        ? ONE_PAGE_TITLE
        : '페이지를 찾을 수 없음 | BOMI')

    const frame = window.requestAnimationFrame(() => {
      // 주소가 특정 구역을 가리키면 그 구역으로 데려간다. 첫 렌더에서는 데이터가
      // 아직 없어 높이가 흔들리므로, 부드러운 스크롤 대신 즉시 이동시킨다.
      const section = ROUTE_SECTIONS[pathname]
      const target = section ? document.getElementById(section) : null
      if (target) {
        target.scrollIntoView({ block: 'start' })
        return
      }
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
