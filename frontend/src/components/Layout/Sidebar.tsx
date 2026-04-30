import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BrandMark } from '../BrandMark';
import { useSessions } from '../../hooks/useSessions';
import { useChatStore } from '../../stores/chatStore';
import { CreativeTasksDock } from '../CreativeTasksDock/CreativeTasksDock';
import { CreateProjectModal } from '../Projects/CreateProjectModal';
import { MoveSessionToProjectModal } from '../Projects/MoveSessionToProjectModal';
import { ProjectConfirmModal } from '../Projects/ProjectConfirmModal';
import { OverlayPortal } from '../Overlay/OverlayPortal';
import { buildProjectConfirmContent } from '../Projects/projectConfirmState';
import { buildProjectSidebarTree } from '../Projects/projectSidebarState';
import './sidebar.css';

export type SidebarMainView =
  | 'chat'
  | 'knowledge'
  | 'assets'
  | 'music'
  | 'voice-clone'
  | 'tts'
  | 'voice-design'
  | 'video'
  | 'project-home'
  | 'project-chat'
  | 'settings';

const VOICE_VIEWS: SidebarMainView[] = ['voice-clone', 'tts', 'voice-design'];

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mainView: SidebarMainView;
  onSelectMainView: (view: SidebarMainView) => void;
}

function formatSessionTime(value?: string): string {
  if (!value) {
    return '';
  }

  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function SidebarIcon({
  id,
}: {
  id:
    | 'settings'
    | 'search'
    | 'plus'
    | 'collapse'
    | 'chats'
    | 'knowledge'
    | 'assets'
    | 'music'
    | 'voice'
    | 'video'
    | 'project'
    | 'more';
}) {
  if (id === 'settings') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    );
  }

  if (id === 'search') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="11" cy="11" r="7" />
        <path d="m21 21-4.3-4.3" />
      </svg>
    );
  }

  if (id === 'collapse') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M15 6l-6 6 6 6" />
      </svg>
    );
  }

  if (id === 'chats') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <path d="M8 8h8" />
        <path d="M8 12h5" />
      </svg>
    );
  }

  if (id === 'knowledge') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M6 4.5h9a3 3 0 0 1 3 3v10.5H9a3 3 0 0 0-3 3V4.5Z" />
        <path d="M6 4.5h-.5A2.5 2.5 0 0 0 3 7v9.5A3.5 3.5 0 0 0 6.5 20H18" />
      </svg>
    );
  }

  if (id === 'assets') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3.5" y="3.5" width="7" height="7" rx="1.4" />
        <rect x="13.5" y="3.5" width="7" height="7" rx="1.4" />
        <rect x="3.5" y="13.5" width="7" height="7" rx="1.4" />
        <rect x="13.5" y="13.5" width="7" height="7" rx="1.4" />
      </svg>
    );
  }

  if (id === 'project') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" />
      </svg>
    );
  }

  if (id === 'music') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M9 18V6.5L19 4v11.5" />
        <circle cx="7" cy="18" r="2.5" />
        <circle cx="17" cy="15.5" r="2.5" />
      </svg>
    );
  }

  if (id === 'voice') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 1 1-6 0V7a3 3 0 0 1 3-3Z" />
        <path d="M18 11a6 6 0 0 1-12 0" />
        <path d="M12 17v3" />
      </svg>
    );
  }

  if (id === 'video') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3" y="5" width="14" height="14" rx="3" />
        <path d="m17 10 4-2v8l-4-2" />
      </svg>
    );
  }

  if (id === 'more') {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor">
        <circle cx="6" cy="12" r="1.6" />
        <circle cx="12" cy="12" r="1.6" />
        <circle cx="18" cy="12" r="1.6" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  );
}

function SessionActionIcon({ kind }: { kind: 'rename' | 'delete' | 'move' }) {
  if (kind === 'rename') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
      </svg>
    );
  }

  if (kind === 'move') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" />
        <path d="M9 12h6" />
        <path d="m12 9 3 3-3 3" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggleCollapse,
  mainView,
  onSelectMainView,
}) => {
  const { sessions, createNewSession } = useSessions();
  const {
    currentSession,
    setCurrentSession,
    deleteSession,
    renameSession,
    projects,
    activeProjectId,
    projectSessions,
    loadProjects,
    openProject,
    deleteProject,
    leaveProject,
    sessionsState,
    isLoading,
    pendingApproval,
    activeTool,
  } = useChatStore();

  /**
   * Returns true when the given session has any in-flight work (loading,
   * pending approval, or active tool execution) — drives the busy dot in
   * the sidebar.
   */
  const sessionIsBusy = useCallback(
    (sessionId: string): boolean => {
      if (sessionId === currentSession) {
        return isLoading || !!pendingApproval || !!activeTool;
      }
      const slice = sessionsState[sessionId];
      if (!slice) return false;
      return slice.isLoading || !!slice.pendingApproval || !!slice.activeTool;
    },
    [currentSession, sessionsState, isLoading, pendingApproval, activeTool],
  );
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [moveTargetSessionId, setMoveTargetSessionId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  const [expandedProjectIds, setExpandedProjectIds] = useState<string[]>([]);
  const [confirmState, setConfirmState] = useState<{
    kind: 'delete-project' | 'delete-project-session';
    targetId: string;
    targetName?: string;
  } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const sessionMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (!collapsed) {
      setSessionMenuOpen(false);
    }
  }, [collapsed]);

  useEffect(() => {
    if (!activeProjectId) {
      return;
    }
    setExpandedProjectIds((current) => (current.includes(activeProjectId) ? current : [...current, activeProjectId]));
  }, [activeProjectId]);

  useEffect(() => {
    if (!sessionMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!sessionMenuRef.current?.contains(event.target as Node)) {
        setSessionMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [sessionMenuOpen]);

  useEffect(() => {
    if (!moreMenuOpen) return;
    const handler = (event: MouseEvent) => {
      if (!moreMenuRef.current?.contains(event.target as Node)) {
        setMoreMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [moreMenuOpen]);

  const filteredSessions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return sessions;
    }

    return sessions.filter((session) => {
      const haystack = `${session.title || ''} ${session.first_message || ''}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [query, sessions]);

  const projectTree = useMemo(
    () =>
      buildProjectSidebarTree({
        projects,
        activeProjectId,
        expandedProjectIds,
        projectSessions,
      }),
    [projects, activeProjectId, expandedProjectIds, projectSessions]
  );
  const isProjectViewActive = mainView === 'project-home' || mainView === 'project-chat';
  const hasSidebarOverlay =
    showCreateProject || moveTargetSessionId !== null || confirmState !== null;

  const beginRename = (sessionId: string, currentTitle?: string, firstMessage?: string) => {
    setEditingSessionId(sessionId);
    setEditingTitle(currentTitle || firstMessage || '');
  };

  const submitRename = async (sessionId: string) => {
    await renameSession(sessionId, editingTitle.trim() || null);
    setEditingSessionId(null);
    setEditingTitle('');
  };

  const selectSession = (sessionId: string) => {
    leaveProject();
    onSelectMainView('chat');
    setCurrentSession(sessionId);
    setSessionMenuOpen(false);
  };

  const handleCreateSession = async () => {
    const createInProject = !!activeProjectId && (mainView === 'project-home' || mainView === 'project-chat');
    if (!createInProject) {
      leaveProject();
    }
    onSelectMainView(createInProject ? 'project-chat' : 'chat');
    await createNewSession();
    setSessionMenuOpen(false);
  };

  const toggleProjectNode = (projectId: string) => {
    setExpandedProjectIds((current) =>
      current.includes(projectId) ? current.filter((id) => id !== projectId) : [...current, projectId]
    );
  };

  const handleOpenProject = async (projectId: string) => {
    const isCurrentProject = activeProjectId === projectId && isProjectViewActive;
    if (isCurrentProject) {
      toggleProjectNode(projectId);
      setSessionMenuOpen(false);
      return;
    }
    setExpandedProjectIds((current) => (current.includes(projectId) ? current : [...current, projectId]));
    await openProject(projectId);
    onSelectMainView('project-home');
    setSessionMenuOpen(false);
  };

  const handleSelectProjectSession = (projectId: string, sessionId: string) => {
    setExpandedProjectIds((current) => (current.includes(projectId) ? current : [...current, projectId]));
    setCurrentSession(sessionId);
    onSelectMainView('project-chat');
    setSessionMenuOpen(false);
  };

  const handleDeleteProject = async (projectId: string, projectName: string) => {
    setConfirmState({
      kind: 'delete-project',
      targetId: projectId,
      targetName: projectName,
    });
  };

  const handleDeleteProjectSession = async (sessionId: string, sessionTitle?: string) => {
    setConfirmState({
      kind: 'delete-project-session',
      targetId: sessionId,
      targetName: sessionTitle,
    });
  };

  const handleConfirmDelete = async () => {
    if (!confirmState) {
      return;
    }

    setConfirmBusy(true);
    try {
      if (confirmState.kind === 'delete-project') {
        const { targetId } = confirmState;
        const deletingActiveProject = activeProjectId === targetId && isProjectViewActive;
        await deleteProject(targetId);
        setExpandedProjectIds((current) => current.filter((id) => id !== targetId));
        if (deletingActiveProject) {
          onSelectMainView('chat');
        }
        setConfirmState(null);
        return;
      }

      const deletingActiveSession = currentSession === confirmState.targetId && mainView === 'project-chat';
      await deleteSession(confirmState.targetId);
      if (deletingActiveSession) {
        onSelectMainView('project-home');
      }
      setConfirmState(null);
    } finally {
      setConfirmBusy(false);
    }
  };

  const renderSessionList = (compact = false) => {
    if (filteredSessions.length === 0) {
      return (
        <div className={`shell-sidebar__empty ${compact ? 'is-compact' : ''}`}>
          {query ? '没有匹配的对话' : '点击“新建对话”开始新的会话'}
        </div>
      );
    }

    return filteredSessions.map((session) => {
      const isActive = currentSession === session.session_id && mainView === 'chat';
      const title = session.title || session.first_message || '新对话';
      const compactLabel = title.trim().slice(0, 1).toUpperCase() || 'T';
      const busy = sessionIsBusy(session.session_id);

      return (
        <div
          key={session.session_id}
          className={`shell-sidebar__session ${isActive ? 'is-active' : ''} ${compact ? 'is-popover' : ''}`}
          onClick={() => selectSession(session.session_id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              selectSession(session.session_id);
            }
          }}
          role="button"
          tabIndex={0}
          title={collapsed ? title : undefined}
        >
          <div className="shell-sidebar__session-main">
            {compact ? <div className="shell-sidebar__session-avatar">{compactLabel}</div> : null}
            {editingSessionId === session.session_id && !compact ? (
              <input
                autoFocus
                className="shell-sidebar__rename-input"
                onBlur={() => {
                  void submitRename(session.session_id);
                }}
                onChange={(event) => setEditingTitle(event.target.value)}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void submitRename(session.session_id);
                  }
                  if (event.key === 'Escape') {
                    setEditingSessionId(null);
                    setEditingTitle('');
                  }
                }}
                value={editingTitle}
              />
            ) : (
              <div className="shell-sidebar__session-body">
                <div className="shell-sidebar__session-title">
                  <span className="shell-sidebar__session-title-text">{title}</span>
                  {busy ? (
                    <span
                      className="shell-sidebar__session-busy"
                      title="此会话有任务正在进行"
                      aria-label="任务进行中"
                    />
                  ) : null}
                </div>
                <div className="shell-sidebar__session-meta">
                  {formatSessionTime(session.updated_at || session.created_at)}
                </div>
              </div>
            )}
          </div>

          {!compact ? (
            <div className="shell-sidebar__session-actions">
              <button
                className="shell-sidebar__session-action"
                onClick={(event) => {
                  event.stopPropagation();
                  setMoveTargetSessionId(session.session_id);
                }}
                title="移入项目"
                type="button"
              >
                <SessionActionIcon kind="move" />
              </button>
              <button
                className="shell-sidebar__session-action"
                onClick={(event) => {
                  event.stopPropagation();
                  beginRename(session.session_id, session.title, session.first_message);
                }}
                title="重命名"
                type="button"
              >
                <SessionActionIcon kind="rename" />
              </button>
              <button
                className="shell-sidebar__session-action"
                onClick={(event) => {
                  event.stopPropagation();
                  void deleteSession(session.session_id);
                }}
                title="删除"
                type="button"
              >
                <SessionActionIcon kind="delete" />
              </button>
            </div>
          ) : null}
        </div>
      );
    });
  };

  return (
    <aside className={`shell-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <button
        className={`shell-sidebar__edge-toggle ${collapsed ? 'is-collapsed' : ''}`}
        onClick={onToggleCollapse}
        title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        type="button"
      >
        <span className={`shell-sidebar__collapse-icon ${collapsed ? 'is-collapsed' : ''}`}>
          <SidebarIcon id="collapse" />
        </span>
      </button>

      <div className="shell-sidebar__top">
        <div className="shell-sidebar__brand">
          <div className="shell-sidebar__brand-row">
            <BrandMark alt="TokenMind 标志" size={collapsed ? 28 : 32} variant={collapsed ? 'icon' : 'wordmark'} />
          </div>
        </div>

        <button
          className="shell-sidebar__primary"
          onClick={() => {
            void handleCreateSession();
          }}
          title="新建对话"
          type="button"
        >
          <span className="shell-sidebar__icon">
            <SidebarIcon id="plus" />
          </span>
          <span>新建对话</span>
        </button>

        {!collapsed ? (
          <div className="shell-sidebar__nav">
            <button
              className={`shell-sidebar__nav-item ${mainView === 'knowledge' ? 'is-active' : ''}`}
              type="button"
              onClick={() => onSelectMainView('knowledge')}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="knowledge" />
              </span>
              <span>知识库</span>
            </button>

            <button
              className={`shell-sidebar__nav-item ${mainView === 'assets' ? 'is-active' : ''}`}
              type="button"
              onClick={() => onSelectMainView('assets')}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="assets" />
              </span>
              <span>资产库</span>
            </button>

            <div className={`shell-sidebar__project-shell ${projectsExpanded ? 'is-open' : ''} ${isProjectViewActive ? 'is-active' : ''}`}>
              <button
                className={`shell-sidebar__group-toggle ${projectsExpanded ? 'is-open' : ''} ${
                  isProjectViewActive ? 'is-active' : ''
                }`}
                type="button"
                onClick={() => setProjectsExpanded((value) => !value)}
              >
                <span className="shell-sidebar__group-label">
                  <span className="shell-sidebar__icon">
                    <SidebarIcon id="project" />
                  </span>
                  <span>项目</span>
                </span>
                <span className={`shell-sidebar__group-caret ${projectsExpanded ? 'is-open' : ''}`}>▾</span>
              </button>

              {projectsExpanded ? (
                <div className="shell-sidebar__project-directory">
                  <div className="shell-sidebar__project-directory-head">
                    <button
                      type="button"
                      className="shell-sidebar__project-create"
                      onClick={() => setShowCreateProject(true)}
                    >
                      {'\u65b0\u9879\u76ee'}
                    </button>
                  </div>

                  {projectTree.length === 0 ? (
                    <div className="shell-sidebar__project-empty">{'\u8fd8\u6ca1\u6709\u9879\u76ee'}</div>
                  ) : (
                    projectTree.map((node) => (
                      <div
                        key={node.project.id}
                        className={`shell-sidebar__project-node ${
                          node.isExpanded ? 'is-open' : ''
                        }`}
                      >
                        <div className="shell-sidebar__project-head">
                          <button
                            type="button"
                            className={`shell-sidebar__project-row ${
                              activeProjectId === node.project.id &&
                              isProjectViewActive ? 'is-active' : ''
                            }`}
                            onClick={() => {
                              void handleOpenProject(node.project.id);
                            }}
                          >
                            <span className="shell-sidebar__project-row-icon">
                              <SidebarIcon id="project" />
                            </span>
                            <span className="shell-sidebar__project-row-label">{node.project.name}</span>
                            <span className={`shell-sidebar__project-row-caret ${node.isExpanded ? 'is-open' : ''}`}>▾</span>
                          </button>

                          <div className="shell-sidebar__project-actions">
                            <button
                              type="button"
                              className="shell-sidebar__project-action"
                              title={'\u5220\u9664\u9879\u76ee'}
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleDeleteProject(node.project.id, node.project.name);
                              }}
                            >
                              <SessionActionIcon kind="delete" />
                            </button>
                          </div>
                        </div>

                        {node.sessions.length > 0 ? (
                          <div className="shell-sidebar__project-session-list">
                            {node.sessions.map((session) => (
                              <div
                                key={session.session_id}
                                className={`shell-sidebar__project-session-item ${
                                  currentSession === session.session_id && mainView === 'project-chat'
                                    ? 'is-active'
                                    : ''
                                }`}
                              >
                                <button
                                  type="button"
                                  className={`shell-sidebar__project-session ${
                                    currentSession === session.session_id && mainView === 'project-chat'
                                      ? 'is-active'
                                      : ''
                                  }`}
                                  onClick={() => {
                                    handleSelectProjectSession(node.project.id, session.session_id);
                                  }}
                                  title={session.title || session.first_message || '\u65b0\u5bf9\u8bdd'}
                                >
                                  {session.title || session.first_message || '\u65b0\u5bf9\u8bdd'}
                                </button>

                                <div className="shell-sidebar__project-session-actions">
                                  <button
                                    type="button"
                                    className="shell-sidebar__project-action"
                                    title={'\u5220\u9664\u4f1a\u8bdd'}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      handleDeleteProjectSession(
                                        session.session_id,
                                        session.title || session.first_message || '\u65b0\u5bf9\u8bdd'
                                      );
                                    }}
                                  >
                                    <SessionActionIcon kind="delete" />
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              ) : null}
            </div>

            <div className="shell-sidebar__more" ref={moreMenuRef}>
              <button
                className={`shell-sidebar__nav-item ${
                  mainView === 'music' ||
                  mainView === 'video' ||
                  VOICE_VIEWS.includes(mainView)
                    ? 'is-active'
                    : ''
                }`}
                type="button"
                onClick={() => setMoreMenuOpen((value) => !value)}
                aria-expanded={moreMenuOpen}
              >
                <span className="shell-sidebar__icon">
                  <SidebarIcon id="more" />
                </span>
                <span>更多</span>
                <span className={`shell-sidebar__group-caret ${moreMenuOpen ? 'is-open' : ''}`}>▾</span>
              </button>

              {moreMenuOpen ? (
                <div className="shell-sidebar__more-popover" role="menu">
                  <button
                    className={`shell-sidebar__more-item ${mainView === 'music' ? 'is-active' : ''}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onSelectMainView('music');
                      setMoreMenuOpen(false);
                    }}
                  >
                    <span className="shell-sidebar__icon">
                      <SidebarIcon id="music" />
                    </span>
                    <span>音乐</span>
                  </button>
                  <button
                    className={`shell-sidebar__more-item ${mainView === 'voice-clone' ? 'is-active' : ''}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onSelectMainView('voice-clone');
                      setMoreMenuOpen(false);
                    }}
                  >
                    <span className="shell-sidebar__icon">
                      <SidebarIcon id="voice" />
                    </span>
                    <span>声音克隆</span>
                  </button>
                  <button
                    className={`shell-sidebar__more-item ${mainView === 'tts' ? 'is-active' : ''}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onSelectMainView('tts');
                      setMoreMenuOpen(false);
                    }}
                  >
                    <span className="shell-sidebar__icon">
                      <SidebarIcon id="voice" />
                    </span>
                    <span>语音合成</span>
                  </button>
                  <button
                    className={`shell-sidebar__more-item ${mainView === 'voice-design' ? 'is-active' : ''}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onSelectMainView('voice-design');
                      setMoreMenuOpen(false);
                    }}
                  >
                    <span className="shell-sidebar__icon">
                      <SidebarIcon id="voice" />
                    </span>
                    <span>音色设计</span>
                  </button>
                  <button
                    className={`shell-sidebar__more-item ${mainView === 'video' ? 'is-active' : ''}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onSelectMainView('video');
                      setMoreMenuOpen(false);
                    }}
                  >
                    <span className="shell-sidebar__icon">
                      <SidebarIcon id="video" />
                    </span>
                    <span>视频</span>
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="shell-sidebar__collapsed-actions" ref={sessionMenuRef}>
            <button
              className={`shell-sidebar__collapsed-button ${mainView === 'knowledge' ? 'is-active' : ''}`}
              type="button"
              title="知识库"
              onClick={() => {
                onSelectMainView('knowledge');
                setSessionMenuOpen(false);
              }}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="knowledge" />
              </span>
            </button>

            <button
              className={`shell-sidebar__collapsed-button ${
                mainView === 'project-home' || mainView === 'project-chat' ? 'is-active' : ''
              }`}
              type="button"
              title="项目"
              onClick={onToggleCollapse}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="project" />
              </span>
            </button>

            <button
              className={`shell-sidebar__collapsed-button ${mainView === 'music' ? 'is-active' : ''}`}
              type="button"
              title="音乐"
              onClick={() => {
                onSelectMainView('music');
                setSessionMenuOpen(false);
              }}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="music" />
              </span>
            </button>

            <button
              className={`shell-sidebar__collapsed-button ${
                VOICE_VIEWS.includes(mainView) ? 'is-active' : ''
              }`}
              type="button"
              title="声音工程"
              onClick={() => {
                onSelectMainView('voice-clone');
                setSessionMenuOpen(false);
              }}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="voice" />
              </span>
            </button>

            <button
              className={`shell-sidebar__collapsed-button ${mainView === 'video' ? 'is-active' : ''}`}
              type="button"
              title="视频"
              onClick={() => {
                onSelectMainView('video');
                setSessionMenuOpen(false);
              }}
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="video" />
              </span>
            </button>

            <button
              className={`shell-sidebar__collapsed-button ${sessionMenuOpen ? 'is-active' : ''}`}
              onClick={() => setSessionMenuOpen((value) => !value)}
              title="最近对话"
              type="button"
            >
              <span className="shell-sidebar__icon">
                <SidebarIcon id="chats" />
              </span>
            </button>

            {sessionMenuOpen ? (
              <div className="shell-sidebar__popover" role="dialog" aria-label="最近对话列表">
                <div className="shell-sidebar__popover-head">
                  <span>最近对话</span>
                  <span className="shell-sidebar__section-meta">{filteredSessions.length}</span>
                </div>

                <label className="shell-sidebar__search is-popover">
                  <span className="shell-sidebar__search-icon">
                    <SidebarIcon id="search" />
                  </span>
                  <input
                    type="text"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索对话"
                  />
                </label>

                <div className="shell-sidebar__popover-list">{renderSessionList(true)}</div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {!collapsed ? (
        <div className="shell-sidebar__sessions">
          <div className="shell-sidebar__section-head">
            <span>最近对话</span>
            <span className="shell-sidebar__section-meta">{filteredSessions.length}</span>
          </div>

          <label className="shell-sidebar__search">
            <span className="shell-sidebar__search-icon">
              <SidebarIcon id="search" />
            </span>
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索对话"
            />
          </label>

          <div className="shell-sidebar__session-list">{renderSessionList()}</div>
        </div>
      ) : (
        <div className="shell-sidebar__collapsed-spacer" />
      )}

      <CreativeTasksDock collapsed={collapsed} onSelectMainView={onSelectMainView} />

      <div className="shell-sidebar__footer">
        <button
          className={`shell-sidebar__settings ${mainView === 'settings' ? 'is-active' : ''}`}
          onClick={() => onSelectMainView('settings')}
          title="设置中心"
          type="button"
        >
          <span className="shell-sidebar__icon">
            <SidebarIcon id="settings" />
          </span>
          <span>设置中心</span>
        </button>
      </div>

      {hasSidebarOverlay ? (
        <OverlayPortal>
          {showCreateProject ? (
            <CreateProjectModal
              onClose={() => setShowCreateProject(false)}
              onCreated={() => onSelectMainView('project-home')}
            />
          ) : null}
          {moveTargetSessionId ? (
            <MoveSessionToProjectModal
              sessionId={moveTargetSessionId}
              onClose={() => setMoveTargetSessionId(null)}
              onMoved={() => onSelectMainView('project-home')}
            />
          ) : null}
          {confirmState ? (
            <ProjectConfirmModal
              {...buildProjectConfirmContent(confirmState.kind, confirmState.targetName)}
              busy={confirmBusy}
              onClose={() => {
                if (!confirmBusy) {
                  setConfirmState(null);
                }
              }}
              onConfirm={handleConfirmDelete}
            />
          ) : null}
        </OverlayPortal>
      ) : null}
    </aside>
  );
};
