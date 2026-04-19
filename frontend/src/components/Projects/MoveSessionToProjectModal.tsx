import React, { useMemo, useState } from 'react';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import './projects.css';

interface MoveSessionToProjectModalProps {
  sessionId: string;
  onClose: () => void;
  onMoved?: () => void;
}

export const MoveSessionToProjectModal: React.FC<MoveSessionToProjectModalProps> = ({
  sessionId,
  onClose,
  onMoved,
}) => {
  const { projects, loadProjects, loadSessions, openProject } = useChatStore();
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const projectOptions = useMemo(() => projects, [projects]);

  const handleSubmit = async () => {
    if (!selectedProjectId) {
      setError('请选择一个项目');
      return;
    }
    setSaving(true);
    try {
      await api.moveSessionToProject(selectedProjectId, sessionId);
      await loadSessions();
      await loadProjects();
      await openProject(selectedProjectId);
      onMoved?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '移入项目失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="project-modal__backdrop">
      <div className="project-modal">
        <div className="project-modal__header">
          <h2>移入项目</h2>
          <button type="button" className="project-modal__close" onClick={onClose}>
            ×
          </button>
        </div>

        <label className="project-modal__field">
          <span>目标项目</span>
          <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

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
            disabled={saving || projectOptions.length === 0}
          >
            {saving ? '处理中...' : '确认移入'}
          </button>
        </div>
      </div>
    </div>
  );
};
