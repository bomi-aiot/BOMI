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

const ALL_NAVIGATION_GROUPS = [
  {
    label: '돌봄 보기',
    items: [
      {
        label: '오늘',
        shortLabel: '오늘',
        marker: '오늘',
        path: '/dashboard',
      },
      {
        label: '생활 기록',
        shortLabel: '기록',
        marker: '기록',
        path: '/records',
      },
      {
        label: '돌봄 계획',
        shortLabel: '계획',
        marker: '계획',
        path: '/care-plan',
      },
      {
        label: '확인할 일',
        shortLabel: '확인',
        marker: '확',
        path: '/confirmation-requests',
      },
      {
        label: '보미와 집',
        shortLabel: '보미',
        marker: '보미',
        path: '/bomi-home',
      },
      {
        label: '어르신 설정',
        shortLabel: '설정',
        marker: '설정',
        path: '/elder/profile',
      },
    ],
  },
  {
    label: '세부 관리',
    items: [
      { label: '복약 관리', shortLabel: '복약', marker: '약', path: '/medications' },
      { label: '일정 관리', shortLabel: '일정', marker: '일', path: '/schedules' },
      { label: '공유된 생활 정보', shortLabel: '정보', marker: '공유', path: '/conversation-preferences' },
    ],
  },
] as const satisfies readonly NavigationGroup[];

const ALL_MOBILE_NAV_ITEMS: readonly NavigationItem[] = [
  {
    label: '오늘',
    shortLabel: '오늘',
    marker: '오늘',
    path: '/dashboard',
  },
  {
    label: '생활 기록',
    shortLabel: '기록',
    marker: '기록',
    path: '/records',
  },
  {
    label: '확인할 일',
    shortLabel: '확인',
    marker: '확',
    path: '/confirmation-requests',
  },
  {
    label: '보미와 집',
    shortLabel: '보미',
    marker: '보미',
    path: '/bomi-home',
  },
];

/**
 * 시연 대본에 등장하는 화면만 네비게이션에 남긴다 (S15P11E102-378).
 *
 * 왜 — 화면이 9개라 리허설 때 어디를 눌러야 하는지 매번 헤맸다. 남기지 않은 화면은
 * 대본 밖이거나(생활 기록·돌봄 계획·일정 관리) 쓰기가 아직 백엔드에 없다
 * (어르신 설정·공유된 생활 정보 — docs/backend-api-todo.md 2·3번).
 *
 * 라우트는 그대로 살려둔다. 주소창으로는 여전히 들어갈 수 있어서 개발 중 확인에
 * 걸리는 게 없고, 시연 중 실수로 눌릴 일만 사라진다.
 *
 * 되돌리기 — 이 집합에 경로를 더하면 그 화면이 다시 보인다. 전부 되살리려면
 * 아래 두 파생 선언을 지우고 ALL_ 접두사를 떼면 원래대로다.
 *   '/dashboard'  오늘 — 종합 화면. 시간이 남으면 3막 마무리 컷으로 되살릴 후보.
 */
const DEMO_NAV_PATHS: ReadonlySet<string> = new Set([
  '/medications', // 1막 — 보호자가 복약 시각을 등록한다
  '/bomi-home', // 2막 — 로봇 모드·실내 온습도를 1초 폴링으로 관제한다
  '/confirmation-requests', // 3막 — 대화에서 AI 가 건진 사실을 보호자가 확정한다
  '/schedules', // 병원 일정 등록 — 등록 결과를 웹에서 보여주는 화면
]);

const isDemoVisible = (item: NavigationItem): boolean =>
  item.path !== undefined && DEMO_NAV_PATHS.has(item.path);

export const NAVIGATION_GROUPS: readonly NavigationGroup[] = ALL_NAVIGATION_GROUPS
  .map((group) => ({ ...group, items: group.items.filter(isDemoVisible) }))
  .filter((group) => group.items.length > 0);

const MOBILE_NAV_ITEMS: readonly NavigationItem[] =
  ALL_MOBILE_NAV_ITEMS.filter(isDemoVisible);

export interface AppLayoutProps {
  children: ReactNode;
  pathname: string;
  onNavigate: (path: string) => void;
  selectedElderName?: string;
  lastObservationLabel?: string;
  alertStatus?: StatusLevel;
  alertStatusLabel?: string;
  notificationCount?: number;
  guardianName?: string;
  guardianRole?: string;
  onRefresh?: () => void;
  onNotificationsOpen?: () => void;
  mockNotice?: ReactNode;
}

interface NavigationProps {
  pathname: string;
  onNavigate: (path: string) => void;
  onItemSelected?: () => void;
  notificationCount?: number;
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
  notificationCount = 0,
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
                      {(item.path === '/confirmation-requests'
                        ? notificationCount
                        : item.notificationCount) ? (
                        <span
                          className="sidebar-nav__count"
                          aria-label={`${
                            item.path === '/confirmation-requests'
                              ? notificationCount
                              : item.notificationCount
                          }건`}
                        >
                          {item.path === '/confirmation-requests'
                            ? notificationCount
                            : item.notificationCount}
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
    | 'lastObservationLabel'
    | 'alertStatus'
    | 'alertStatusLabel'
    | 'notificationCount'
    | 'guardianName'
    | 'guardianRole'
    | 'onRefresh'
    | 'onNotificationsOpen'
  > {
  drawerOpen: boolean;
  onDrawerToggle: () => void;
}

export function AppHeader({
  selectedElderName = '봄순 어르신',
  lastObservationLabel = '관찰 시각 없음',
  alertStatus = 'pending',
  alertStatusLabel,
  notificationCount = 0,
  guardianName = '보호자',
  guardianRole = '보호자 화면',
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
        <StatusBadge
          status={alertStatus}
          label={alertStatusLabel ?? '알림 확인 중'}
        />
      </div>

      <div className="app-header__account">
        <button
          className="notification-button"
          type="button"
          onClick={onNotificationsOpen}
          disabled={!onNotificationsOpen}
          aria-label={`확인할 일 ${notificationCount}건`}
        >
          <span aria-hidden="true">확인</span>
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
  lastObservationLabel,
  alertStatus,
  alertStatusLabel,
  notificationCount = 0,
  guardianName,
  guardianRole,
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
        <Navigation pathname={pathname} onNavigate={handleNavigate} notificationCount={notificationCount} />
        <div className="app-sidebar__support">
          <p>도움이 필요하신가요?</p>
          <span>돌봄 서비스 문의는 운영팀에 알려주세요.</span>
        </div>
      </aside>

      <div className="app-shell__body">
        <AppHeader
          selectedElderName={selectedElderName}
          lastObservationLabel={lastObservationLabel}
          alertStatus={alertStatus}
          alertStatusLabel={alertStatusLabel}
          notificationCount={notificationCount}
          guardianName={guardianName}
          guardianRole={guardianRole}
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
              notificationCount={notificationCount}
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
              aria-label={
                item.path === '/confirmation-requests'
                  ? `확인할 일 ${notificationCount}건`
                  : item.label
              }
            >
              <span className="mobile-bottom-nav__marker" aria-hidden="true">
                {item.marker}
              </span>
              {item.path === '/confirmation-requests' && notificationCount > 0 ? (
                <span className="mobile-bottom-nav__count" aria-hidden="true">
                  {notificationCount > 99 ? '99+' : notificationCount}
                </span>
              ) : null}
              <span>{item.shortLabel}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
