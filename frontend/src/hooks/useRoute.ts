import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export const APP_ROUTES = [
  '/',
  '/dashboard',
  '/records',
  '/care-plan',
  '/bomi-home',
  '/elder/profile',
  '/conversation-preferences',
  '/confirmation-requests',
  '/health',
  '/medications',
  '/schedules',
] as const;

export type AppRoutePath = (typeof APP_ROUTES)[number];

export interface NavigateOptions {
  replace?: boolean;
}

export interface RouteState {
  pathname: string;
  navigate: (path: string, options?: NavigateOptions) => void;
  isActive: (path: string) => boolean;
}

const normalizePath = (path: string): string => {
  const withoutQuery = path.split(/[?#]/, 1)[0] ?? '/';
  const withLeadingSlash = withoutQuery.startsWith('/')
    ? withoutQuery
    : `/${withoutQuery}`;

  if (withLeadingSlash.length > 1) {
    return withLeadingSlash.replace(/\/+$/, '');
  }

  return '/';
};

const getBrowserPath = (): string => {
  if (typeof window === 'undefined') {
    return '/';
  }

  return normalizePath(window.location.pathname);
};

const HISTORY_INDEX_KEY = '__bomiHistoryIndex';

const readHistoryIndex = (): number | null => {
  const state: unknown = window.history.state;
  if (typeof state !== 'object' || state === null) {
    return null;
  }
  const value = (state as Record<string, unknown>)[HISTORY_INDEX_KEY];
  return typeof value === 'number' ? value : null;
};

const historyStateWithIndex = (index: number): Record<string, unknown> => {
  const state: unknown = window.history.state;
  const base =
    typeof state === 'object' && state !== null
      ? (state as Record<string, unknown>)
      : {};
  return { ...base, [HISTORY_INDEX_KEY]: index };
};

const initializeHistoryIndex = (): number => {
  if (typeof window === 'undefined') {
    return 0;
  }
  const existingIndex = readHistoryIndex();
  if (existingIndex !== null) {
    return existingIndex;
  }
  window.history.replaceState(historyStateWithIndex(0), '', window.location.href);
  return 0;
};

export const isKnownAppRoute = (path: string): path is AppRoutePath =>
  APP_ROUTES.includes(normalizePath(path) as AppRoutePath);

export function useRoute(): RouteState {
  const [pathname, setPathname] = useState<string>(getBrowserPath);
  const [initialHistoryIndex] = useState(initializeHistoryIndex);
  const historyIndexRef = useRef(initialHistoryIndex);
  const restoringHistoryRef = useRef(false);

  useEffect(() => {
    const handlePopState = (): void => {
      if (restoringHistoryRef.current) {
        restoringHistoryRef.current = false;
        return;
      }
      const nextPath = getBrowserPath();
      if (nextPath === pathname) {
        return;
      }
      const navigationEvent = new CustomEvent('bomi:before-navigate', {
        cancelable: true,
        detail: { from: pathname, to: nextPath },
      });
      if (!window.dispatchEvent(navigationEvent)) {
        const nextIndex = readHistoryIndex();
        if (nextIndex !== null) {
          const restoreDelta = historyIndexRef.current - nextIndex;
          if (restoreDelta !== 0) {
            restoringHistoryRef.current = true;
            window.history.go(restoreDelta);
          }
        }
        return;
      }
      const nextIndex = readHistoryIndex();
      if (nextIndex !== null) {
        historyIndexRef.current = nextIndex;
      }
      setPathname(nextPath);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [pathname]);

  const navigate = useCallback(
    (path: string, options: NavigateOptions = {}): void => {
      const nextPath = normalizePath(path);
      const currentPath = getBrowserPath();

      if (nextPath === currentPath) {
        setPathname(nextPath);
        return;
      }

      const navigationEvent = new CustomEvent('bomi:before-navigate', {
        cancelable: true,
        detail: { from: currentPath, to: nextPath },
      });
      if (!window.dispatchEvent(navigationEvent)) {
        return;
      }

      if (options.replace) {
        window.history.replaceState(
          historyStateWithIndex(historyIndexRef.current),
          '',
          nextPath,
        );
      } else {
        const nextIndex = historyIndexRef.current + 1;
        window.history.pushState(
          historyStateWithIndex(nextIndex),
          '',
          nextPath,
        );
        historyIndexRef.current = nextIndex;
      }

      setPathname(nextPath);
      window.scrollTo({ top: 0, behavior: 'auto' });
    },
    [],
  );

  const isActive = useCallback(
    (path: string): boolean => pathname === normalizePath(path),
    [pathname],
  );

  return useMemo(
    () => ({
      pathname,
      navigate,
      isActive,
    }),
    [isActive, navigate, pathname],
  );
}
