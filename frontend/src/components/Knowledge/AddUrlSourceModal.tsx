import React, { useEffect, useState } from 'react';

import { api } from '../../services/api';
import type { KnowledgeDocument } from '../../types/knowledge';
import './createKnowledgeBaseModal.css';

interface AddUrlSourceModalProps {
  knowledgeBaseId: string;
  onClose: () => void;
  // Called as soon as the fetch returns and the source is registered.
  // The parent should kick off any follow-up work (polling, refresh)
  // without awaiting — the modal closes immediately.
  onAdded: (document: KnowledgeDocument) => void;
}

export const AddUrlSourceModal: React.FC<AddUrlSourceModalProps> = ({
  knowledgeBaseId,
  onClose,
  onAdded,
}) => {
  const [url, setUrl] = useState('');
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
    const trimmed = url.trim();
    if (!trimmed) {
      setError('请输入文章链接');
      return;
    }
    if (!/^https?:\/\//i.test(trimmed)) {
      setError('链接必须以 http(s) 开头');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await api.addUrlSource(knowledgeBaseId, trimmed);
      // Hand the document off to the parent without awaiting; the
      // modal's job ended once the fetch returned and the document
      // was registered. The LLM compile that follows is tracked by
      // the same progress bar as a regular upload.
      onAdded(result.document);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '抓取失败');
      setSaving(false);
    }
  };

  return (
    <div className="kb-modal__backdrop" onClick={() => !saving && onClose()}>
      <div
        className="kb-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-url-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kb-modal__header">
          <h2 id="add-url-modal-title">添加文章链接</h2>
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

        <p className="kb-modal__hint">
          目前支持微信公众号链接(<code>https://mp.weixin.qq.com/s/...</code>)。文章会被抓取并保存到当前知识库,然后跟普通素材一样被 LLM 编译为 Wiki 页面。
        </p>

        <label className="kb-modal__field">
          <span>文章链接</span>
          <input
            autoFocus
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://mp.weixin.qq.com/s/..."
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
            {saving ? '抓取中…' : '抓取并添加'}
          </button>
        </div>
      </div>
    </div>
  );
};
