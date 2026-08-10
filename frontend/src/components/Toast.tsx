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
  /**
   * 'critical' 은 위급 알림 전용이다. tone 과 따로 두는 이유 — tone 은 색이고
   * emphasis 는 "화면 어디에 얼마나 크게 뜨는가"라서, danger 토스트를 전부
   * 화면 한가운데로 끌어올리면 저장 실패 같은 사소한 실패까지 위급처럼 보인다.
   */
  emphasis?: 'normal' | 'critical';
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
  emphasis = 'normal',
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

  const isCritical = emphasis === 'critical';
  const isAlert = tone === 'danger' || isCritical;

  return (
    <div
      className={`toast toast--${tone}${isCritical ? ' toast--critical' : ''}`}
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
