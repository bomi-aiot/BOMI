import { useEffect, useRef, useState, type ReactNode } from 'react';
import { StatusBadge, type StatusLevel } from '../components/Badge';
import type { AppRoutePath } from '../hooks/useRoute';

export interface NavigationItem {
  label: string;
  shortLabel: string;
  marker: string;
  path?: AppRoutePath;
  disabled?: boolean;
  notificationCount?: number;
}

export interface NavigationGroup {
  label: string;
  items: readonly NavigationItem[];
}

export const NAVIGATION_GROUPS = [
  {
    label: '돌봄 관리',
    items: [
      {
        label: '대시보드',
        shortLabel: '홈',
        marker: '홈',
        path: '/dashboard',
      },
      {
        label: '어르신 프로필',
        shortLabel: '어르신',
        marker: '어',
        path: '/elder/profile',
      },
      {
        label: '대화 정보',
        shortLabel: '대화',
        marker: '대',
        path: '/conversation-preferences',
      },
      {
        label: 'AI 확인 요청',
        shortLabel: '확인',
        marker: '확',
        path: '/confirmation-requests',
      },
      {
        label: '건강 기록',
        shortLabel: '건강',
        marker: '건',
        path: '/health',
      },
      {
        label: '복약 관리',
        shortLabel: '복약',
        marker: '약',
        path: '/medications',
      },
      {
        label: '일정 관리',
        shortLabel: '일정',
        marker: '일',
        path: '/schedules',
      },
    ],
  },
  {
    label: '운영 관리',
    items: [
      {
        label: '로봇·기기',
        shortLabel: '로봇',
        marker: '로',
        disabled: true,
      },
      {
        label: '이벤트 이력',
        shortLabel: '이벤트',
        marker: '이',
        disabled: true,
      },
      {
        label: '건강 분석',
        shortLabel: '분석',
        marker: '분',
        disabled: true,
      },
      {
        label: '시스템 관리',
        shortLabel: '시스템',
        marker: '시',
        disabled: true,
      },
      {
        label: '설정',
        shortLabel: '설정',
        marker: '설',
        disabled: true,
      },
    ],
  },
] as const satisfies readonly NavigationGroup[];

const MOBILE_NAV_ITEMS: readonly NavigationItem[] = [
  {
    label: '대시보드',
    shortLabel: '홈',
    marker: '홈',
    path: '/dashboard',
  },
  {
    label: '어르신 프로필',
    shortLabel: '어르신',
    marker: '어',
    path: '/elder/profile',
  },
  {
    label: 'AI 확인 요청',
    shortLabel: '확인',
    marker: '확',
    path: '/confirmation-requests',
  },
  {
    label: '건강 기록',
    shortLabel: '건강',
    marker: '건',
    path: '/health',
  },
  {
    label: '일정 관리',
    shortLabel: '일정',
    marker: '일',
    path: '/schedules',
  },
];

export interface AppLayoutProps {
  children: ReactNode;
  pathname: string;
  onNavigate: (path: string) => void;
  selectedElderName?: string;
  lastUpdatedLabel?: string;
  systemStatus?: StatusLevel;
  systemStatusLabel?: string;
  notificationCount?: number;
  guardianName?: string;
  guardianRole?: string;
  onElderSelect?: () => void;
  onRefresh?: () => void;
  onNotificationsOpen?: () => void;
  mockNotice?: ReactNode;
}

interface NavigationProps {
  pathname: string;
  onNavigate: (path: string) => void;
  onItemSelected?: () => void;
}

function Brand() {
  return (
    <div className="app-brand" aria-label="BOMI 보호자 센터">
      <span className="app-brand__mark" aria-hidden="true">
        B
      </span>
      <span className="app-brand__copy">
        <strong className="app-brand__name">BOMI</strong>
        <span className="app-brand__subtitle">보호자 센터</span>
      </span>
    </div>
  );
}

function Navigation({
  pathname,
  onNavigate,
  onItemSelected,
}: NavigationProps) {
  const handleNavigate = (path: AppRoutePath): void => {
    onNavigate(path);
    onItemSelected?.();
  };

  return (
    <nav className="sidebar-nav" aria-label="주요 메뉴">
      {NAVIGATION_GROUPS.map((group) => {
        const items: readonly NavigationItem[] = group.items;

        return (
          <section className="sidebar-nav__group" key={group.label}>
            <h2 className="sidebar-nav__group-label">{group.label}</h2>
            <ul className="sidebar-nav__list">
              {items.map((item) => {
              const isActive = item.path === pathname;
              return (
                <li key={item.label}>
                  {item.disabled || !item.path ? (
                    <button
                      className="sidebar-nav__item sidebar-nav__item--disabled"
                      type="button"
                      disabled
                      aria-disabled="true"
                      title={`${item.label} — 추후 제공`}
                    >
                      <span
                        className="sidebar-nav__marker"
                        aria-hidden="true"
                      >
                        {item.marker}
                      </span>
                      <span className="sidebar-nav__label">{item.label}</span>
                      <span className="sidebar-nav__coming-soon">
                        추후 제공
                      </span>
                    </button>
                  ) : (
                    <button
                      className={`sidebar-nav__item${
                        isActive ? ' sidebar-nav__item--active' : ''
                      }`}
                      type="button"
                      onClick={() => handleNavigate(item.path as AppRoutePath)}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      <span
                        className="sidebar-nav__marker"
                        aria-hidden="true"
                      >
                        {item.marker}
                      </span>
                      <span className="sidebar-nav__label">{item.label}</span>
                      {item.notificationCount ? (
                        <span
                          className="sidebar-nav__count"
                          aria-label={`${item.notificationCount}건`}
                        >
                          {item.notificationCount}
                        </span>
                      ) : null}
                    </button>
                  )}
                </li>
              );
              })}
            </ul>
          </section>
        );
      })}
    </nav>
  );
}

interface AppHeaderProps
  extends Pick<
    AppLayoutProps,
    | 'selectedElderName'
    | 'lastUpdatedLabel'
    | 'systemStatus'
    | 'systemStatusLabel'
    | 'notificationCount'
    | 'guardianName'
    | 'guardianRole'
    | 'onElderSelect'
    | 'onRefresh'
    | 'onNotificationsOpen'
  > {
  drawerOpen: boolean;
  onDrawerToggle: () => void;
}

export function AppHeader({
  selectedElderName = '봄순 어르신',
  lastUpdatedLabel = '방금 전',
  systemStatus = 'normal',
  systemStatusLabel,
  notificationCount = 0,
  guardianName = '김보호',
  guardianRole = '주 보호자',
  onElderSelect,
  onRefresh,
  onNotificationsOpen,
  drawerOpen,
  onDrawerToggle,
}: AppHeaderProps) {
  const guardianInitial = guardianName.trim().slice(0, 1) || '보';

  return (
    <header className="app-header">
      <div className="app-header__leading">
        <button
          className="app-header__menu-button"
          type="button"
          onClick={onDrawerToggle}
          aria-label={drawerOpen ? '메뉴 닫기' : '메뉴 열기'}
          aria-expanded={drawerOpen}
          aria-controls="mobile-navigation-drawer"
        >
          <span aria-hidden="true">{drawerOpen ? '×' : '☰'}</span>
        </button>
        <button
          className="elder-selector"
          type="button"
          onClick={onElderSelect}
          disabled={!onElderSelect}
          aria-label={`돌봄 대상: ${selectedElderName}`}
        >
          <span className="elder-selector__label">돌봄 대상</span>
          <strong className="elder-selector__name">{selectedElderName}</strong>
          {onElderSelect ? (
            <span className="elder-selector__chevron" aria-hidden="true">
              ▾
            </span>
          ) : null}
        </button>
      </div>

      <div className="app-header__status">
        <div className="refresh-status">
          <span className="refresh-status__label">최근 갱신</span>
          <span className="refresh-status__time">{lastUpdatedLabel}</span>
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
        <StatusBadge
          status={systemStatus}
          label={systemStatusLabel ?? '시스템 정상'}
        />
      </div>

      <div className="app-header__account">
        <button
          className="notification-button"
          type="button"
          onClick={onNotificationsOpen}
          disabled={!onNotificationsOpen}
          aria-label={`알림 ${notificationCount}건`}
        >
          <span aria-hidden="true">알림</span>
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
            <strong className="guardian-profile__name">{guardianName}</strong>
            <span className="guardian-profile__role">{guardianRole}</span>
          </span>
        </div>
      </div>
    </header>
  );
}

export function AppLayout({
  children,
  pathname,
  onNavigate,
  selectedElderName,
  lastUpdatedLabel,
  systemStatus,
  systemStatusLabel,
  notificationCount,
  guardianName,
  guardianRole,
  onElderSelect,
  onRefresh,
  onNotificationsOpen,
  mockNotice,
}: AppLayoutProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerCloseButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) {
      return undefined;
    }

    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const originalOverflow = document.body.style.overflow;
    const backgroundRegions = [
      document.querySelector<HTMLElement>('.app-shell__body'),
      document.querySelector<HTMLElement>('.app-sidebar'),
      document.querySelector<HTMLElement>('.mobile-bottom-nav'),
    ].filter((region): region is HTMLElement => region !== null);
    document.body.style.overflow = 'hidden';
    backgroundRegions.forEach((region) => {
      region.setAttribute('inert', '');
      region.setAttribute('aria-hidden', 'true');
    });

    const handleEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setDrawerOpen(false);
      }
    };

    const handleTab = (event: KeyboardEvent): void => {
      if (event.key !== 'Tab' || !drawerRef.current) {
        return;
      }

      const focusableElements = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      );
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (!firstElement || !lastElement) {
        event.preventDefault();
        drawerRef.current.focus();
        return;
      }

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener('keydown', handleEscape);
    document.addEventListener('keydown', handleTab);
    drawerCloseButtonRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.removeEventListener('keydown', handleTab);
      document.body.style.overflow = originalOverflow;
      backgroundRegions.forEach((region) => {
        region.removeAttribute('inert');
        region.removeAttribute('aria-hidden');
      });
      previouslyFocused?.focus();
    };
  }, [drawerOpen]);

  const handleNavigate = (path: string): void => {
    onNavigate(path);
    setDrawerOpen(false);
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        본문으로 바로가기
      </a>

      <aside className="app-sidebar">
        <Brand />
        <Navigation pathname={pathname} onNavigate={handleNavigate} />
        <div className="app-sidebar__support">
          <p>도움이 필요하신가요?</p>
          <span>돌봄 서비스 문의는 운영팀에 알려주세요.</span>
        </div>
      </aside>

      <div className="app-shell__body">
        <AppHeader
          selectedElderName={selectedElderName}
          lastUpdatedLabel={lastUpdatedLabel}
          systemStatus={systemStatus}
          systemStatusLabel={systemStatusLabel}
          notificationCount={notificationCount}
          guardianName={guardianName}
          guardianRole={guardianRole}
          onElderSelect={onElderSelect}
          onRefresh={onRefresh}
          onNotificationsOpen={onNotificationsOpen}
          drawerOpen={drawerOpen}
          onDrawerToggle={() => setDrawerOpen((current) => !current)}
        />

        {mockNotice ? (
          <div className="app-shell__notice">{mockNotice}</div>
        ) : null}

        <main className="app-main" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>

      {drawerOpen ? (
        <div
          className="mobile-drawer-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) {
              setDrawerOpen(false);
            }
          }}
        >
          <aside
            ref={drawerRef}
            className="mobile-drawer"
            id="mobile-navigation-drawer"
            aria-label="모바일 메뉴"
            role="dialog"
            aria-modal="true"
            tabIndex={-1}
          >
            <div className="mobile-drawer__header">
              <Brand />
              <button
                ref={drawerCloseButtonRef}
                className="mobile-drawer__close"
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="메뉴 닫기"
              >
                <span aria-hidden="true">×</span>
              </button>
            </div>
            <Navigation
              pathname={pathname}
              onNavigate={handleNavigate}
              onItemSelected={() => setDrawerOpen(false)}
            />
          </aside>
        </div>
      ) : null}

      <nav className="mobile-bottom-nav" aria-label="빠른 메뉴">
        {MOBILE_NAV_ITEMS.map((item) => {
          if (!item.path) {
            return null;
          }

          const isActive = item.path === pathname;
          return (
            <button
              className={`mobile-bottom-nav__item${
                isActive ? ' mobile-bottom-nav__item--active' : ''
              }`}
              type="button"
              key={item.path}
              onClick={() => handleNavigate(item.path as AppRoutePath)}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="mobile-bottom-nav__marker" aria-hidden="true">
                {item.marker}
              </span>
              <span>{item.shortLabel}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
