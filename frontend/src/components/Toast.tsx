import { useEffect } from 'react';
import type { BadgeTone } from './Badge';

export interface ToastProps {
  open: boolean;
  message: string;
  title?: string;
  tone?: BadgeTone;
  durationMs?: number;
  onDismiss: () => void;
  actionLabel?: string;
  onAction?: () => void;
}

export function Toast({
  open,
  message,
  title,
  tone = 'success',
  durationMs = 5000,
  onDismiss,
  actionLabel,
  onAction,
}: ToastProps) {
  useEffect(() => {
    if (!open || durationMs <= 0) {
      return undefined;
    }

    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, onDismiss, open]);

  if (!open) {
    return null;
  }

  const isAlert = tone === 'danger';

  return (
    <div
      className={`toast toast--${tone}`}
      role={isAlert ? 'alert' : 'status'}
      aria-live={isAlert ? 'assertive' : 'polite'}
    >
      <span className="toast__indicator" aria-hidden="true" />
      <div className="toast__content">
        {title ? <strong className="toast__title">{title}</strong> : null}
        <p className="toast__message">{message}</p>
      </div>
      {actionLabel && onAction ? (
        <button
          className="toast__action"
          type="button"
          onClick={() => {
            onAction();
            onDismiss();
          }}
        >
          {actionLabel}
        </button>
      ) : null}
      <button
        className="toast__close"
        type="button"
        onClick={onDismiss}
        aria-label="알림 닫기"
      >
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
