import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Button } from './Button';

export type ModalSize = 'small' | 'medium' | 'large';

export interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children?: ReactNode;
  footer?: ReactNode;
  size?: ModalSize;
  closeLabel?: string;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
  closeDisabled?: boolean;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  size = 'medium',
  closeLabel = '창 닫기',
  closeOnBackdrop = true,
  closeOnEscape = true,
  closeDisabled = false,
}: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const originalOverflow = document.body.style.overflow;
    const appRoot = document.getElementById('root');
    const originalAriaHidden = appRoot?.getAttribute('aria-hidden');
    document.body.style.overflow = 'hidden';
    appRoot?.setAttribute('inert', '');
    appRoot?.setAttribute('aria-hidden', 'true');

    const focusTarget =
      dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
      dialogRef.current;
    focusTarget?.focus();

    const handleEscape = (event: globalThis.KeyboardEvent): void => {
      if (event.key === 'Escape' && closeOnEscape) {
        event.preventDefault();
        onCloseRef.current();
      }
    };

    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = originalOverflow;
      appRoot?.removeAttribute('inert');
      if (originalAriaHidden === null) {
        appRoot?.removeAttribute('aria-hidden');
      } else if (originalAriaHidden !== undefined) {
        appRoot?.setAttribute('aria-hidden', originalAriaHidden);
      }
      previouslyFocused?.focus();
    };
  }, [closeOnEscape, open]);

  if (!open) {
    return null;
  }

  const handleBackdropClick = (
    event: ReactMouseEvent<HTMLDivElement>,
  ): void => {
    if (closeOnBackdrop && event.currentTarget === event.target) {
      onClose();
    }
  };

  const handleKeyDown = (
    event: ReactKeyboardEvent<HTMLDivElement>,
  ): void => {
    if (event.key !== 'Tab' || !dialogRef.current) {
      return;
    }

    const focusableElements = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    );

    if (focusableElements.length === 0) {
      event.preventDefault();
      dialogRef.current.focus();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement?.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement?.focus();
    }
  };

  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={handleBackdropClick}
    >
      <div
        ref={dialogRef}
        className={`modal modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal__header">
          <div>
            <h2 className="modal__title" id={titleId}>
              {title}
            </h2>
            {description ? (
              <p className="modal__description" id={descriptionId}>
                {description}
              </p>
            ) : null}
          </div>
          <button
            className="modal__close"
            type="button"
            onClick={onClose}
            disabled={closeDisabled}
            aria-label={closeLabel}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
        {children ? <div className="modal__body">{children}</div> : null}
        {footer ? <div className="modal__footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

export interface ConfirmModalProps {
  open: boolean;
  title: string;
  description: string;
  onClose: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'default' | 'danger';
  isLoading?: boolean;
  children?: ReactNode;
}

export function ConfirmModal({
  open,
  title,
  description,
  onClose,
  onConfirm,
  confirmLabel = '확인',
  cancelLabel = '취소',
  tone = 'default',
  isLoading = false,
  children,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      title={title}
      description={description}
      onClose={() => {
        if (!isLoading) {
          onClose();
        }
      }}
      size="small"
      closeOnBackdrop={!isLoading}
      closeOnEscape={!isLoading}
      closeDisabled={isLoading}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
