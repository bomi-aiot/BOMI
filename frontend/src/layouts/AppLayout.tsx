import { type ReactNode } from 'react';

/**
 * 문의 메일 주소.
 *
 * 사이드바 아래에 "도움이 필요하신가요? 돌봄 서비스 문의는 운영팀에 알려주세요" 라는
 * 안내가 있었지만 누를 수 없었다 — 문의하라고 적어 두고 문의할 방법은 주지 않은 셈이다.
 * 링크 하나면 되는 일이라 mailto 로 연결한다.
 */
const SUPPORT_EMAIL = 'wdg0434@gmail.com';

/** 종 아이콘. 아이콘 폰트를 새로 들이지 않으려고 인라인 SVG 로 둔다. */
function BellIcon() {
  return (
    <svg
      className="notification-button__icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M18 8a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" />
      <path d="M13.7 20a2 2 0 0 1-3.4 0" />
    </svg>
  );
}

export interface AppLayoutProps {
  children: ReactNode;
  selectedElderName?: string;
  lastObservationLabel?: string;
  notificationCount?: number;
  guardianName?: string;
  guardianRole?: string;
  onRefresh?: () => void;
  onNotificationsOpen?: () => void;
  mockNotice?: ReactNode;
}

type AppHeaderProps = Pick<
  AppLayoutProps,
  | 'selectedElderName'
  | 'lastObservationLabel'
  | 'notificationCount'
  | 'guardianName'
  | 'guardianRole'
  | 'onRefresh'
  | 'onNotificationsOpen'
>;

export function AppHeader({
  selectedElderName = '봄순 어르신',
  lastObservationLabel = '관찰 시각 없음',
  notificationCount = 0,
  guardianName,
  guardianRole,
  onRefresh,
  onNotificationsOpen,
}: AppHeaderProps) {
  // 보호자 이름을 못 받았을 때 "보호자"라는 일반명사로 채우지 않는다. 그 자리에
  // 그럴듯한 글자를 넣으면, 실제로는 아무도 연결돼 있지 않다는 사실이 가려진다.
  const hasGuardian = Boolean(guardianName?.trim());
  const displayName = guardianName?.trim() ?? '보호자 미연결';
  const guardianInitial = hasGuardian ? displayName.slice(0, 1) : '?';

  return (
    <header className="app-header">
      <div className="app-header__leading">
        <div className="app-brand" aria-label="BOMI 보호자 센터">
          <span className="app-brand__mark" aria-hidden="true">
            B
          </span>
          <span className="app-brand__copy">
            <strong className="app-brand__name">BOMI</strong>
            <span className="app-brand__subtitle">보호자 센터</span>
          </span>
        </div>
        <div className="elder-selector" aria-label={`돌봄 대상: ${selectedElderName}`}>
          <span className="elder-selector__label">돌봄 대상</span>
          <strong className="elder-selector__name">{selectedElderName}</strong>
        </div>
      </div>

      <div className="app-header__status">
        <div className="refresh-status">
          <span className="refresh-status__label">마지막 관찰</span>
          <span className="refresh-status__time">{lastObservationLabel}</span>
          {onRefresh ? (
            <button
              className="refresh-status__button"
              type="button"
              onClick={onRefresh}
              aria-label="정보 새로고침"
            >
              새로고침
            </button>
          ) : null}
        </div>
      </div>

      <div className="app-header__account">
        {/*
          "확인" 이라는 글자를 종 아이콘으로 바꾸고, 실제로 눌리게 했다.
            예전에는 화면 넷이 따로 있어서 이 버튼이 /confirmation-requests 로
            이동시켰는데, 이미 그 화면이면 아무 일도 일어나지 않았다 — 숫자만 떠 있고
            눌러도 반응이 없는 버튼이었다. 이제 같은 페이지의 '확인할 일' 구역으로
            스크롤한다. 어디에 있든 항상 반응한다.
        */}
        <button
          className="notification-button"
          type="button"
          onClick={onNotificationsOpen}
          disabled={!onNotificationsOpen}
          aria-label={
            notificationCount > 0
              ? `확인할 일 ${notificationCount}건 보기`
              : '확인할 일 보기'
          }
        >
          <BellIcon />
          {notificationCount > 0 ? (
            <span className="notification-button__count">
              {notificationCount > 99 ? '99+' : notificationCount}
            </span>
          ) : null}
        </button>
        <div className="guardian-profile">
          <span className="guardian-profile__avatar" aria-hidden="true">
            {guardianInitial}
          </span>
          <span className="guardian-profile__copy">
            <strong className="guardian-profile__name">{displayName}</strong>
            {hasGuardian && guardianRole ? (
              <span className="guardian-profile__role">{guardianRole}</span>
            ) : null}
          </span>
        </div>
      </div>
    </header>
  );
}

/**
 * 한 장짜리 보호자 화면의 뼈대.
 *
 * 사이드바를 없앴다 — 그 안의 버튼 넷이 가리키던 화면을 모두 본문 한 장에 쌓았기
 * 때문이다(GuardianOnePage). 메뉴가 사라지면서 모바일 서랍과 하단 탭도 함께 사라진다.
 * 셋 다 "어느 화면으로 갈까"만 물어보던 장치였고, 이제 갈 곳이 하나다.
 */
export function AppLayout({
  children,
  selectedElderName,
  lastObservationLabel,
  notificationCount = 0,
  guardianName,
  guardianRole,
  onRefresh,
  onNotificationsOpen,
  mockNotice,
}: AppLayoutProps) {
  return (
    <div className="app-shell app-shell--flat">
      <a className="skip-link" href="#main-content">
        본문으로 바로가기
      </a>

      <div className="app-shell__body">
        <AppHeader
          selectedElderName={selectedElderName}
          lastObservationLabel={lastObservationLabel}
          notificationCount={notificationCount}
          guardianName={guardianName}
          guardianRole={guardianRole}
          onRefresh={onRefresh}
          onNotificationsOpen={onNotificationsOpen}
        />

        {mockNotice ? (
          <div className="app-shell__notice">{mockNotice}</div>
        ) : null}

        <main className="app-main" id="main-content" tabIndex={-1}>
          {children}

          <footer className="app-support">
            <p className="app-support__title">도움이 필요하신가요?</p>
            <p className="app-support__body">
              돌봄 서비스 문의는{' '}
              <a
                className="app-support__link"
                href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(
                  'BOMI 보호자 센터 문의',
                )}`}
              >
                운영팀에 메일로 알려주세요
              </a>
              .
            </p>
          </footer>
        </main>
      </div>
    </div>
  );
}
