import { BomiHomePage } from './BomiHomePage'
import { ConfirmationRequestsPage } from './ConfirmationRequestsPage'
import { HealthPage } from './HealthPage'
import { SchedulesPage } from './SchedulesPage'

/**
 * 보호자 화면 전부를 한 페이지에 담는다.
 *
 * 왜 화면을 합쳤는가
 *   사이드바에 버튼 넷이 있었고, 보호자가 아침에 알고 싶은 것("별일 없었나")을 알려면
 *   그 넷을 차례로 눌러 봐야 했다. 넷 다 한 어르신의 오늘을 다른 각도에서 보는 것이라
 *   서로 배타적이지도 않다 — 나눌 이유가 화면 구조 말고는 없었다. 메뉴를 없애고 한 장에
 *   세로로 쌓으면, 스크롤 한 번이 클릭 넷을 대신한다.
 *
 * 순서가 곧 우선순위다
 *   1. 확인할 일 — 보호자가 <b>해야 할 일</b>. 유일하게 조치를 요구하는 구역이라 맨 위다.
 *      헤더의 종 아이콘도 여기로 데려온다.
 *   2. 보미와 집 — 지금 상태. 안전 알림이 여기 있다.
 *   3. 복약 · 4. 일정 — 관리·설정에 가깝다. 매일 볼 필요는 없어서 아래로 내린다.
 *
 * 각 구역은 기존 페이지 컴포넌트를 그대로 재사용한다. 안에서 쓰는 PageHeader 가
 * 구역 제목 노릇을 하고, 크기는 .one-page__section 아래에서 CSS 로만 줄인다 —
 * 컴포넌트 넷에 "나 지금 구역이야" 라는 프로퍼티를 심는 것보다 되돌리기 쉽다.
 */
export const ONE_PAGE_SECTIONS = {
  confirmations: 'section-confirmations',
  bomi: 'section-bomi',
  medications: 'section-medications',
  schedules: 'section-schedules',
} as const

interface GuardianOnePageProps {
  onNavigate: (path: string) => void
}

export function GuardianOnePage({ onNavigate }: GuardianOnePageProps) {
  return (
    <div className="one-page">
      <section
        className="one-page__section"
        id={ONE_PAGE_SECTIONS.confirmations}
        aria-label="확인할 일"
      >
        <ConfirmationRequestsPage />
      </section>

      <section
        className="one-page__section"
        id={ONE_PAGE_SECTIONS.bomi}
        aria-label="보미와 집"
      >
        <BomiHomePage />
      </section>

      <section
        className="one-page__section"
        id={ONE_PAGE_SECTIONS.medications}
        aria-label="복약 관리"
      >
        <HealthPage onNavigate={onNavigate} />
      </section>

      <section
        className="one-page__section"
        id={ONE_PAGE_SECTIONS.schedules}
        aria-label="일정 관리"
      >
        <SchedulesPage />
      </section>
    </div>
  )
}
