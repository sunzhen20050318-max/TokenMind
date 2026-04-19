import React from 'react';
import type { ProjectConfirmContent } from './projectConfirmState';
import './projects.css';

interface ProjectConfirmModalProps extends ProjectConfirmContent {
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
}

export const ProjectConfirmModal: React.FC<ProjectConfirmModalProps> = ({
  title,
  message,
  confirmLabel,
  busy = false,
  onClose,
  onConfirm,
}) => {
  return (
    <div
      className="project-modal__backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div className="project-modal project-modal--confirm" onClick={(event) => event.stopPropagation()}>
        <div className="project-modal__header">
          <h2>{title}</h2>
          <button type="button" className="project-modal__close" onClick={onClose} disabled={busy}>
            ×
          </button>
        </div>

        <div className="project-modal__body">
          <p>{message}</p>
        </div>

        <div className="project-modal__actions">
          <button type="button" className="project-modal__button is-secondary" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="project-modal__button is-danger"
            onClick={() => {
              void onConfirm();
            }}
            disabled={busy}
          >
            {busy ? '删除中...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
