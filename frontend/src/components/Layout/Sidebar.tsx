import React, { useMemo, useState } from 'react';
import { useSessions } from '../../hooks/useSessions';
import { useChatStore } from '../../stores/chatStore';
import { SettingsModal } from '../../pages/Settings';
import { TasksModal } from '../../pages/Tasks';
import { StorageModal } from '../../pages/Storage';

export const Sidebar: React.FC = () => {
  const { sessions, createNewSession } = useSessions();
  const { currentSession, setCurrentSession, deleteSession, renameSession } = useChatStore();
  const [showSettings, setShowSettings] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [showStorage, setShowStorage] = useState(false);
  const [query, setQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  const currentSessionMeta = sessions.find((session) => session.session_id === currentSession);

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

  return (
    <div
      style={{
        width: '260px',
        height: '100%',
        backgroundColor: '#0f0f0f',
        display: 'flex',
        flexDirection: 'column',
        borderRight: '1px solid #1a1a1a',
      }}
    >
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #1a1a1a',
          display: 'grid',
          gap: '8px',
        }}
      >
        <button
          onClick={() => setShowSettings(true)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid #2a2a2a',
            backgroundColor: 'transparent',
            color: '#a0a0a0',
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.15s',
          }}
          onMouseOver={(event) => {
            event.currentTarget.style.backgroundColor = '#1a1a1a';
            event.currentTarget.style.color = '#e5e5e5';
          }}
          onMouseOut={(event) => {
            event.currentTarget.style.backgroundColor = 'transparent';
            event.currentTarget.style.color = '#a0a0a0';
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            设置中心
          </span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>

        <button
          onClick={() => setShowTasks(true)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid #2a2a2a',
            backgroundColor: 'transparent',
            color: '#a0a0a0',
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.15s',
          }}
          onMouseOver={(event) => {
            event.currentTarget.style.backgroundColor = '#1a1a1a';
            event.currentTarget.style.color = '#e5e5e5';
          }}
          onMouseOut={(event) => {
            event.currentTarget.style.backgroundColor = 'transparent';
            event.currentTarget.style.color = '#a0a0a0';
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            定时任务
          </span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 6h13" />
            <path d="M8 12h13" />
            <path d="M8 18h13" />
            <path d="M3 6h.01" />
            <path d="M3 12h.01" />
            <path d="M3 18h.01" />
          </svg>
        </button>

        <button
          onClick={() => setShowStorage(true)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid #2a2a2a',
            backgroundColor: 'transparent',
            color: '#a0a0a0',
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.15s',
          }}
          onMouseOver={(event) => {
            event.currentTarget.style.backgroundColor = '#1a1a1a';
            event.currentTarget.style.color = '#e5e5e5';
          }}
          onMouseOut={(event) => {
            event.currentTarget.style.backgroundColor = 'transparent';
            event.currentTarget.style.color = '#a0a0a0';
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            文件中心
          </span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4.379a1.5 1.5 0 0 1 1.06.44l1.121 1.12a1.5 1.5 0 0 0 1.06.44H19.5A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-10Z" />
          </svg>
        </button>
      </div>

      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #1a1a1a',
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索会话"
          style={{
            width: '100%',
            marginBottom: '10px',
            padding: '9px 12px',
            borderRadius: '8px',
            border: '1px solid #242424',
            backgroundColor: '#141414',
            color: '#f3f3f3',
            fontSize: '13px',
            outline: 'none',
          }}
        />
        <button
          onClick={createNewSession}
          style={{
            width: '100%',
            padding: '10px 16px',
            borderRadius: '6px',
            border: '1px solid #2a2a2a',
            backgroundColor: 'transparent',
            color: '#e5e5e5',
            fontSize: '14px',
            fontWeight: 500,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
          onMouseOver={(event) => {
            event.currentTarget.style.backgroundColor = '#1a1a1a';
            event.currentTarget.style.borderColor = '#3a3a3a';
          }}
          onMouseOut={(event) => {
            event.currentTarget.style.backgroundColor = 'transparent';
            event.currentTarget.style.borderColor = '#2a2a2a';
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建对话
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {filteredSessions.length === 0 ? (
          <div
            style={{
              padding: '24px 16px',
              color: '#6e6e73',
              fontSize: '13px',
              textAlign: 'center',
            }}
          >
            {query ? '没有匹配的会话' : '还没有会话'}
          </div>
        ) : (
          filteredSessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => setCurrentSession(session.session_id)}
              style={{
                padding: '12px 16px',
                cursor: 'pointer',
                backgroundColor: currentSession === session.session_id ? '#1c1c1e' : 'transparent',
                borderLeft:
                  currentSession === session.session_id ? '2px solid #fff' : '2px solid transparent',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                transition: 'background-color 0.15s ease',
              }}
              onMouseOver={(event) => {
                if (currentSession !== session.session_id) {
                  event.currentTarget.style.backgroundColor = '#161616';
                }
              }}
              onMouseOut={(event) => {
                if (currentSession !== session.session_id) {
                  event.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              <div style={{ overflow: 'hidden', flex: 1 }}>
                {editingSessionId === session.session_id ? (
                  <input
                    autoFocus
                    value={editingTitle}
                    onChange={(event) => setEditingTitle(event.target.value)}
                    onClick={(event) => event.stopPropagation()}
                    onBlur={() => {
                      void submitRename(session.session_id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        void submitRename(session.session_id);
                      }
                      if (event.key === 'Escape') {
                        setEditingSessionId(null);
                        setEditingTitle('');
                      }
                    }}
                    style={{
                      width: '100%',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      border: '1px solid #3a3a3a',
                      backgroundColor: '#111',
                      color: '#fff',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                ) : (
                  <div
                    style={{
                      fontSize: '14px',
                      fontWeight: 500,
                      color: '#e5e5e5',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {session.title || session.first_message || '新会话'}
                  </div>
                )}
                <div style={{ fontSize: '12px', color: '#666', marginTop: '2px' }}>
                  {session.created_at
                    ? new Date(session.created_at).toLocaleString('zh-CN', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : ''}
                </div>
              </div>

              <div
                style={{ display: 'flex', alignItems: 'center', gap: '4px', opacity: 0 }}
                className="session-actions"
              >
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    beginRename(session.session_id, session.title, session.first_message);
                  }}
                  style={{
                    padding: '6px',
                    border: 'none',
                    backgroundColor: 'transparent',
                    color: '#9a9a9a',
                    cursor: 'pointer',
                    borderRadius: '4px',
                  }}
                  title="重命名"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </button>
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    deleteSession(session.session_id);
                  }}
                  style={{
                    padding: '6px',
                    border: 'none',
                    backgroundColor: 'transparent',
                    color: '#6e6e73',
                    fontSize: '14px',
                    cursor: 'pointer',
                    borderRadius: '4px',
                  }}
                  title="删除"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <style>{`
        div:hover > .session-actions {
          opacity: 1 !important;
        }
      `}</style>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {showTasks && (
      <TasksModal
        onClose={() => setShowTasks(false)}
        currentSessionId={currentSession}
        currentSessionLabel={
          currentSessionMeta?.title || currentSessionMeta?.first_message || currentSession || undefined
        }
        sessions={sessions}
      />
      )}
      {showStorage && <StorageModal onClose={() => setShowStorage(false)} />}
    </div>
  );
};
