import type { HTMLAttributes, ReactNode } from 'react';

export type BadgeTone =
  | 'neutral'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
}

export function Badge({
  tone = 'neutral',
  dot = false,
  className = '',
  children,
  ...spanProps
}: BadgeProps) {
  return (
    <span
      {...spanProps}
      className={`badge badge--${tone} ${className}`.trim()}
    >
      {dot ? <span className="badge__dot" aria-hidden="true" /> : null}
      <span>{children}</span>
    </span>
  );
}

export type StatusLevel =
  | 'normal'
  | 'online'
  | 'completed'
  | 'attention'
  | 'pending'
  | 'paused'
  | 'danger'
  | 'offline';

const STATUS_LABELS: Record<StatusLevel, string> = {
  normal: '정상',
  online: '온라인',
  completed: '완료',
  attention: '확인 필요',
  pending: '대기 중',
  paused: '일시 중지',
  danger: '위험',
  offline: '오프라인',
};

const STATUS_TONES: Record<StatusLevel, BadgeTone> = {
  normal: 'success',
  online: 'success',
  completed: 'success',
  attention: 'warning',
  pending: 'info',
  paused: 'neutral',
  danger: 'danger',
  offline: 'neutral',
};

export interface StatusBadgeProps
  extends Omit<BadgeProps, 'children' | 'tone'> {
  status: StatusLevel;
  label?: string;
}

export function StatusBadge({
  status,
  label,
  ...badgeProps
}: StatusBadgeProps) {
  return (
    <Badge {...badgeProps} tone={STATUS_TONES[status]} dot>
      {label ?? STATUS_LABELS[status]}
    </Badge>
  );
}
