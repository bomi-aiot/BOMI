import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'ghost'
  | 'danger'
  | 'quiet';
export type ButtonSize = 'small' | 'medium' | 'large';

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  isLoading?: boolean;
  loadingLabel?: string;
  leadingContent?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'medium',
  fullWidth = false,
  isLoading = false,
  loadingLabel = '처리 중',
  leadingContent,
  className = '',
  disabled,
  children,
  type = 'button',
  ...buttonProps
}: ButtonProps) {
  const classes = [
    'button',
    `button--${variant}`,
    `button--${size}`,
    fullWidth ? 'button--full-width' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      {...buttonProps}
      type={type}
      className={classes}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
    >
      {isLoading ? (
        <>
          <span className="button__spinner" aria-hidden="true" />
          <span>{loadingLabel}</span>
        </>
      ) : (
        <>
          {leadingContent ? (
            <span className="button__leading" aria-hidden="true">
              {leadingContent}
            </span>
          ) : null}
          <span>{children}</span>
        </>
      )}
    </button>
  );
}
