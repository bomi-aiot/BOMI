import type { ReactNode } from 'react';

export interface PageHeaderProps {
  title: string;
  description?: string;
  eyebrow?: string;
  metadata?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  description,
  eyebrow,
  metadata,
  actions,
}: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header__copy">
        {eyebrow ? <p className="page-header__eyebrow">{eyebrow}</p> : null}
        <h1 className="page-header__title">{title}</h1>
        {description ? (
          <p className="page-header__description">{description}</p>
        ) : null}
        {metadata ? (
          <div className="page-header__metadata">{metadata}</div>
        ) : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </div>
  );
}
