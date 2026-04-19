import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BrandMark } from '../BrandMark';
import { useSessions } from '../../hooks/useSessions';
import { useChatStore } from '../../stores/chatStore';
import { SettingsModal } from '../../pages/Settings';
import './sidebar.css';

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mainView: 'chat' | 'knowledge';
  onSelectMainView: (view: 'chat' | 'knowledge') => void;
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

function SidebarIcon({ id }: { id: 'settings' | 'search' | 'plus' | 'collapse' | 'chats' | 'knowledge' }) {
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

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  );
}

function SessionActionIcon({ kind }: { kind: 'rename' | 'delete' }) {
  if (kind === 'rename') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
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
  const { currentSession, setCurrentSession, deleteSession, renameSession } = useChatStore();
  const [showSettings, setShowSettings] = useState(false);
  const [query, setQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const sessionMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!collapsed) {
      setSessionMenuOpen(false);
    }
  }, [collapsed]);

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
    onSelectMainView('chat');
    setCurrentSession(sessionId);
    setSessionMenuOpen(false);
  };

  const handleCreateSession = () => {
    onSelectMainView('chat');
    createNewSession();
    setSessionMenuOpen(false);
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
                <div className="shell-sidebar__session-title">{title}</div>
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

        <button className="shell-sidebar__primary" onClick={handleCreateSession} title="新建对话" type="button">
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

      <div className="shell-sidebar__footer">
        <button
          className="shell-sidebar__settings"
          onClick={() => setShowSettings(true)}
          title="设置中心"
          type="button"
        >
          <span className="shell-sidebar__icon">
            <SidebarIcon id="settings" />
          </span>
          <span>设置中心</span>
        </button>
      </div>

      {showSettings ? <SettingsModal onClose={() => setShowSettings(false)} /> : null}
    </aside>
  );
};
