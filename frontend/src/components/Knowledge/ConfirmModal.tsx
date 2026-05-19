import React, { useEffect, useState } from 'react';

import './createKnowledgeBaseModal.css';

interface ConfirmModalProps {
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  title,
  message,
  confirmLabel = '确认',
  cancelLabel = '取消',
  danger = false,
  onClose,
  onConfirm,
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const handleConfirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
      setBusy(false);
    }
  };

  return (
    <div className="kb-modal__backdrop" onClick={() => !busy && onClose()}>
      <div
        className="kb-modal"
        role="alertdialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kb-modal__header">
          <h2>{title}</h2>
          <button
            type="button"
            className="kb-modal__close"
            onClick={onClose}
            aria-label="关闭"
            disabled={busy}
          >
            ×
          </button>
        </div>

        <div className="kb-modal__message">{message}</div>

        {error ? <div className="kb-modal__error">{error}</div> : null}

        <div className="kb-modal__actions">
          <button
            type="button"
            className="kb-modal__button is-secondary"
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`kb-modal__button ${danger ? 'is-danger' : ''}`}
            onClick={() => void handleConfirm()}
            disabled={busy}
          >
            {busy ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
