import React, { useEffect, useState } from 'react';

import './createKnowledgeBaseModal.css';

interface RenameKnowledgeBaseModalProps {
  currentName: string;
  onClose: () => void;
  onSubmit: (nextName: string) => Promise<void>;
}

export const RenameKnowledgeBaseModal: React.FC<RenameKnowledgeBaseModalProps> = ({
  currentName,
  onClose,
  onSubmit,
}) => {
  const [name, setName] = useState(currentName);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, saving]);

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('名称不能为空');
      return;
    }
    if (trimmed === currentName.trim()) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit(trimmed);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '重命名失败');
      setSaving(false);
    }
  };

  return (
    <div className="kb-modal__backdrop" onClick={() => !saving && onClose()}>
      <div
        className="kb-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-kb-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kb-modal__header">
          <h2 id="rename-kb-title">重命名知识库</h2>
          <button
            type="button"
            className="kb-modal__close"
            onClick={onClose}
            aria-label="关闭"
            disabled={saving}
          >
            ×
          </button>
        </div>

        <label className="kb-modal__field">
          <span>名称</span>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={saving}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
          />
        </label>

        {error ? <div className="kb-modal__error">{error}</div> : null}

        <div className="kb-modal__actions">
          <button
            type="button"
            className="kb-modal__button is-secondary"
            onClick={onClose}
            disabled={saving}
          >
            取消
          </button>
          <button
            type="button"
            className="kb-modal__button"
            onClick={() => void handleSubmit()}
            disabled={saving}
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
};
