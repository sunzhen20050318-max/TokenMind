import React, { useState } from 'react';
import { useSessions } from '../../hooks/useSessions';
import { useChatStore } from '../../stores/chatStore';
import { SettingsModal } from '../../pages/Settings';

export const Sidebar: React.FC = () => {
  const { sessions, createNewSession } = useSessions();
  const { currentSession, setCurrentSession, deleteSession, modelProviders, activeModelId } = useChatStore();
  const [showSettings, setShowSettings] = useState(false);

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
      {/* Model selector + settings */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #1a1a1a',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}
      >
        <button
          onClick={() => setShowSettings(true)}
          style={{
            flex: 1,
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
          onMouseOver={(e) => {
            e.currentTarget.style.backgroundColor = '#1a1a1a';
            e.currentTarget.style.color = '#e5e5e5';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = '#a0a0a0';
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeModelId
              ? (modelProviders.find(p => p.id === activeModelId)?.name || activeModelId)
              : '选择模型'}
          </span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>

      {/* New Chat button */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #1a1a1a',
        }}
      >
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
          onMouseOver={(e) => {
            e.currentTarget.style.backgroundColor = '#1a1a1a';
            e.currentTarget.style.borderColor = '#3a3a3a';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.borderColor = '#2a2a2a';
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          New Chat
        </button>
      </div>

      {/* Session list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {sessions.length === 0 ? (
          <div
            style={{
              padding: '24px 16px',
              color: '#6e6e73',
              fontSize: '13px',
              textAlign: 'center',
            }}
          >
            No conversations yet
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => setCurrentSession(session.session_id)}
              style={{
                padding: '12px 16px',
                cursor: 'pointer',
                backgroundColor:
                  currentSession === session.session_id ? '#1c1c1e' : 'transparent',
                borderLeft:
                  currentSession === session.session_id
                    ? '2px solid #fff'
                    : '2px solid transparent',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                transition: 'background-color 0.15s ease',
              }}
              onMouseOver={(e) => {
                if (currentSession !== session.session_id) {
                  e.currentTarget.style.backgroundColor = '#161616';
                }
              }}
              onMouseOut={(e) => {
                if (currentSession !== session.session_id) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              <div style={{ overflow: 'hidden', flex: 1 }}>
                <div
                  style={{
                    fontSize: '14px',
                    fontWeight: 400,
                    color: '#e5e5e5',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {session.first_message || 'New conversation'}
                </div>
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
              <button
                onClick={(e) => {
                  e.stopPropagation();
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
                  opacity: 0,
                  transition: 'opacity 0.15s ease',
                }}
                className="delete-btn"
                onMouseOver={(e) => {
                  e.currentTarget.style.color = '#ff453a';
                  e.currentTarget.style.backgroundColor = '#3d3d40';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.color = '#6e6e73';
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          ))
        )}
      </div>

      <style>{`
        div:hover > button.delete-btn {
          opacity: 1 !important;
        }
      `}</style>
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
};
