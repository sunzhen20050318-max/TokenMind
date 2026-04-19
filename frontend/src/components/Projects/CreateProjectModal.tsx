import React, { useState } from 'react';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import './projects.css';

interface CreateProjectModalProps {
  onClose: () => void;
  onCreated?: () => void;
}

export const CreateProjectModal: React.FC<CreateProjectModalProps> = ({ onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const { loadProjects, openProject } = useChatStore();

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('项目名称不能为空');
      return;
    }
    setSaving(true);
    try {
      const project = await api.createProject(name.trim());
      await loadProjects();
      await openProject(project.id);
      onCreated?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建项目失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="project-modal__backdrop">
      <div className="project-modal">
        <div className="project-modal__header">
          <h2>创建项目</h2>
          <button type="button" className="project-modal__close" onClick={onClose}>
            ×
          </button>
        </div>

        <label className="project-modal__field">
          <span>项目名称</span>
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="输入项目名称"
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                void handleSubmit();
              }
            }}
          />
        </label>

        <div className="project-modal__tip">
          项目会把属于它的聊天收进单独空间，项目中的聊天不会出现在全局最近列表。
        </div>

        {error ? <div className="project-modal__error">{error}</div> : null}

        <div className="project-modal__actions">
          <button type="button" className="project-modal__button is-secondary" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="project-modal__button"
            onClick={() => {
              void handleSubmit();
            }}
            disabled={saving}
          >
            {saving ? '创建中...' : '创建项目'}
          </button>
        </div>
      </div>
    </div>
  );
};
