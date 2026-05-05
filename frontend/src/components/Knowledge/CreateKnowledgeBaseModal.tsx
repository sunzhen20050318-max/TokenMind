import React, { useEffect, useState } from 'react';

import { api } from '../../services/api';
import './createKnowledgeBaseModal.css';

interface CreateKnowledgeBaseModalProps {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

export const CreateKnowledgeBaseModal: React.FC<CreateKnowledgeBaseModalProps> = ({
  onClose,
  onCreated,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Esc closes
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('名称不能为空');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createKnowledgeBase({
        name: trimmedName,
        description: description.trim(),
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建知识库失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="kb-modal__backdrop" onClick={onClose}>
      <div
        className="kb-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kb-modal__header">
          <h2 id="kb-modal-title">新建知识库</h2>
          <button
            type="button"
            className="kb-modal__close"
            onClick={onClose}
            aria-label="关闭"
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
            placeholder="例如:产品资料、合同模板、项目规范"
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
          />
        </label>

        <label className="kb-modal__field">
          <span>简介(可选)</span>
          <textarea
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="一句话说明这个知识库主要收什么资料。"
          />
        </label>

        {error ? <div className="kb-modal__error">{error}</div> : null}

        <div className="kb-modal__actions">
          <button
            type="button"
            className="kb-modal__button is-secondary"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="kb-modal__button"
            onClick={() => void handleSubmit()}
            disabled={saving}
          >
            {saving ? '创建中…' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
};
