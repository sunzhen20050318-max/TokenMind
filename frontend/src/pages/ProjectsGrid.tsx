import React, { useEffect, useMemo, useState } from 'react';
import { CreateProjectModal } from '../components/Projects/CreateProjectModal';
import { ProjectConfirmModal } from '../components/Projects/ProjectConfirmModal';
import { buildProjectConfirmContent } from '../components/Projects/projectConfirmState';
import { OverlayPortal } from '../components/Overlay/OverlayPortal';
import { useChatStore } from '../stores/chatStore';
import '../components/Projects/projects.css';

interface ProjectsGridProps {
  onOpenProject: (projectId: string) => void;
  onProjectCreated: () => void;
}

function formatUpdated(value?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' });
}

export const ProjectsGrid: React.FC<ProjectsGridProps> = ({ onOpenProject, onProjectCreated }) => {
  const { projects, loadProjects, deleteProject } = useChatStore();
  const [showCreate, setShowCreate] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => p.name.toLowerCase().includes(q));
  }, [projects, query]);

  const handleConfirmDelete = async () => {
    if (!confirmTarget) return;
    setConfirmBusy(true);
    try {
      await deleteProject(confirmTarget.id);
      setConfirmTarget(null);
    } finally {
      setConfirmBusy(false);
    }
  };

  return (
    <section className="projects-grid">
      <div className="projects-grid__body">
        <header className="projects-grid__header">
          <h1>项目</h1>
          <button type="button" className="projects-grid__new" onClick={() => setShowCreate(true)}>
            新建项目
          </button>
        </header>

        {projects.length > 0 ? (
          <label className="projects-grid__search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索项目…"
            />
          </label>
        ) : null}

        {projects.length === 0 ? (
          <div className="projects-grid__empty">
            还没有项目。点击右上角“新建项目”，把相关的聊天集中到一个空间里。
          </div>
        ) : filtered.length === 0 ? (
          <div className="projects-grid__empty">没有匹配的项目。</div>
        ) : (
          <div className="projects-grid__cards">
            {filtered.map((project) => (
              <button
                key={project.id}
                type="button"
                className="projects-grid__card"
                onClick={() => onOpenProject(project.id)}
              >
                <div className="projects-grid__card-top">
                  <strong className="projects-grid__card-name">{project.name}</strong>
                  <span
                    className="projects-grid__card-delete"
                    role="button"
                    tabIndex={0}
                    title="删除项目"
                    onClick={(event) => {
                      event.stopPropagation();
                      setConfirmTarget({ id: project.id, name: project.name });
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        setConfirmTarget({ id: project.id, name: project.name });
                      }
                    }}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </span>
                </div>
                {project.instructions ? (
                  <p className="projects-grid__card-desc">{project.instructions}</p>
                ) : null}
                <div className="projects-grid__card-footer">
                  更新于 {formatUpdated(project.updated_at)}
                  {project.session_count ? ` · ${project.session_count} 个会话` : ''}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {(showCreate || confirmTarget) ? (
        <OverlayPortal>
          {showCreate ? (
            <CreateProjectModal
              onClose={() => setShowCreate(false)}
              onCreated={onProjectCreated}
            />
          ) : null}
          {confirmTarget ? (
            <ProjectConfirmModal
              {...buildProjectConfirmContent('delete-project', confirmTarget.name)}
              busy={confirmBusy}
              onClose={() => {
                if (!confirmBusy) {
                  setConfirmTarget(null);
                }
              }}
              onConfirm={handleConfirmDelete}
            />
          ) : null}
        </OverlayPortal>
      ) : null}
    </section>
  );
};
