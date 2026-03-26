import React from 'react';
import { useChatStore } from '../../stores/chatStore';

export const Header: React.FC = () => {
  const { isConnected, currentSession, sessions, activeModelId, modelProviders } = useChatStore();
  const currentSessionMeta = sessions.find((session) => session.session_id === currentSession);
  const currentModel = activeModelId
    ? modelProviders.find((provider) => provider.id === activeModelId)?.name || activeModelId
    : 'No model selected';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 20px',
        backgroundColor: '#1a1a1b',
        borderBottom: '1px solid #2d2d30',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5">
          <circle cx="12" cy="12" r="4" fill="white" stroke="white"/>
          <line x1="12" y1="2" x2="12" y2="4"/>
          <line x1="12" y1="20" x2="12" y2="22"/>
          <line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/>
          <line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/>
          <line x1="2" y1="12" x2="4" y2="12"/>
          <line x1="20" y1="12" x2="22" y2="12"/>
          <line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/>
          <line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/>
        </svg>
        <span style={{ fontSize: '16px', fontWeight: 600, color: '#fff' }}>sun-agent</span>
        <div style={{ fontSize: '12px', color: '#707070' }}>
          {currentSessionMeta?.title || currentSessionMeta?.first_message || 'Ready for a new conversation'}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{ fontSize: '12px', color: '#8e8e93' }}>{currentModel}</div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
            color: '#8e8e93',
          }}
        >
        <span
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: isConnected ? '#34c759' : '#ff453a',
            boxShadow: isConnected ? '0 0 6px #34c759' : 'none',
          }}
        />
        {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </div>
    </div>
  );
};
