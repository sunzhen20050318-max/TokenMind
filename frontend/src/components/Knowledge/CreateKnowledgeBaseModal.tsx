import React, { useEffect, useState } from 'react';

import { api } from '../../services/api';
import type { KnowledgeBaseType } from '../../types/knowledge';
import './createKnowledgeBaseModal.css';

interface CreateKnowledgeBaseModalProps {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

interface TypeOption {
  value: KnowledgeBaseType;
  title: string;
  blurb: string;
}

const TYPE_OPTIONS: TypeOption[] = [
  {
    value: 'rag',
    title: 'RAG 知识库',
    blurb: '上传文档后自动切分、向量化，提问时由后端检索片段注入上下文。',
  },
  {
    value: 'wiki',
    title: 'Wiki 知识库',
    blurb: 'LLM 把原始资料编译成相互链接的 Markdown 页面，对话时模型用工具浏览。',
  },
];

export const CreateKnowledgeBaseModal: React.FC<CreateKnowledgeBaseModalProps> = ({
  onClose,
  onCreated,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<KnowledgeBaseType>('rag');
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
        type,
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

        <fieldset className="kb-modal__type-group" aria-label="知识库类型">
          {TYPE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`kb-modal__type-card ${type === option.value ? 'is-active' : ''}`}
            >
              <input
                type="radio"
                name="kb-type"
                value={option.value}
                checked={type === option.value}
                onChange={() => setType(option.value)}
              />
              <span className="kb-modal__type-title">{option.title}</span>
              <span className="kb-modal__type-blurb">{option.blurb}</span>
            </label>
          ))}
        </fieldset>

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
