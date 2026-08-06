import type { ReactNode } from 'react';
import { Button } from './Button';

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  symbol?: string;
  compact?: boolean;
}

export function EmptyState({
  title,
  description,
  action,
  symbol = '—',
  compact = false,
}: EmptyStateProps) {
  return (
    <section
      className={`feedback-state empty-state${
        compact ? ' feedback-state--compact' : ''
      }`}
      aria-label={title}
    >
      <span className="feedback-state__symbol" aria-hidden="true">
        {symbol}
      </span>
      <h2 className="feedback-state__title">{title}</h2>
      {description ? (
        <p className="feedback-state__description">{description}</p>
      ) : null}
      {action ? <div className="feedback-state__action">{action}</div> : null}
    </section>
  );
}

export interface LoadingStateProps {
  label?: string;
  rows?: number;
  compact?: boolean;
}

export function LoadingState({
  label = '정보를 불러오는 중입니다',
  rows = 3,
  compact = false,
}: LoadingStateProps) {
  return (
    <section
      className={`feedback-state loading-state${
        compact ? ' feedback-state--compact' : ''
      }`}
      role="status"
      aria-live="polite"
    >
      <span className="loading-state__spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
      <div className="loading-state__skeletons" aria-hidden="true">
        {Array.from({ length: Math.max(1, rows) }, (_, index) => (
          <span
            className="loading-state__skeleton"
            key={`loading-row-${index + 1}`}
          />
        ))}
      </div>
    </section>
  );
}

export interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

export function ErrorState({
  title = '정보를 불러오지 못했습니다',
  description = '잠시 후 다시 시도해 주세요.',
  onRetry,
  retryLabel = '다시 시도',
  compact = false,
}: ErrorStateProps) {
  return (
    <section
      className={`feedback-state error-state${
        compact ? ' feedback-state--compact' : ''
      }`}
      role="alert"
    >
      <span className="feedback-state__symbol" aria-hidden="true">
        !
      </span>
      <h2 className="feedback-state__title">{title}</h2>
      <p className="feedback-state__description">{description}</p>
      {onRetry ? (
        <div className="feedback-state__action">
          <Button variant="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
