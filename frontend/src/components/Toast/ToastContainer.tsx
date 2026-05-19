import React, { useEffect } from 'react';

import { useToastStore, type ToastItem } from '../../stores/toastStore';
import './toast.css';

const ICON: Record<ToastItem['level'], string> = {
  info: 'ℹ',
  success: '✓',
  warning: '!',
  error: '✕',
};

const ToastCard: React.FC<{ toast: ToastItem; onDismiss: (id: string) => void }> = ({
  toast,
  onDismiss,
}) => {
  useEffect(() => {
    if (toast.duration <= 0) return;
    const tid = window.setTimeout(() => onDismiss(toast.id), toast.duration);
    return () => window.clearTimeout(tid);
  }, [toast.id, toast.duration, onDismiss]);

  return (
    <div className={`tm-toast tm-toast--${toast.level}`} role="status" aria-live="polite">
      <span className="tm-toast__icon" aria-hidden="true">{ICON[toast.level]}</span>
      <div className="tm-toast__body">
        {toast.title ? <div className="tm-toast__title">{toast.title}</div> : null}
        <div className="tm-toast__message">{toast.message}</div>
      </div>
      <button
        type="button"
        className="tm-toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label="关闭"
      >
        ×
      </button>
    </div>
  );
};

export const ToastContainer: React.FC = () => {
  const toasts = useToastStore((state) => state.toasts);
  const dismissToast = useToastStore((state) => state.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="tm-toast-stack" role="region" aria-label="通知">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </div>
  );
};
