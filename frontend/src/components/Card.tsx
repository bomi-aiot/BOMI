import type { HTMLAttributes, ReactNode } from 'react';

export interface CardProps extends HTMLAttributes<HTMLElement> {
  heading?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  compact?: boolean;
  as?: 'article' | 'section' | 'div';
}

export function Card({
  heading,
  description,
  actions,
  children,
  compact = false,
  as: Element = 'section',
  className = '',
  ...elementProps
}: CardProps) {
  const classes = [
    'card',
    compact ? 'card--compact' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Element {...elementProps} className={classes}>
      {heading || description || actions ? (
        <div className="card__header">
          <div className="card__heading-group">
            {heading ? <h2 className="card__title">{heading}</h2> : null}
            {description ? (
              <p className="card__description">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="card__actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className="card__content">{children}</div>
    </Element>
  );
}
