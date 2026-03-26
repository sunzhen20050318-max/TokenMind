import React from 'react';
import { useChatStore } from '../../stores/chatStore';
import { BrandMark } from '../BrandMark';

export const Header: React.FC = () => {
  const { isConnected, currentSession, sessions, activeModelId, modelProviders, modelProvidersStatus } =
    useChatStore();
  const currentSessionMeta = sessions.find((session) => session.session_id === currentSession);
  const currentModel = (() => {
    if (modelProvidersStatus === 'idle' || modelProvidersStatus === 'loading') {
      return '正在读取模型...';
    }
    if (activeModelId) {
      return modelProviders.find((provider) => provider.id === activeModelId)?.name || activeModelId;
    }
    if (modelProvidersStatus === 'error') {
      return '模型状态不可用';
    }
    return '未设置默认模型';
  })();

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
        <BrandMark size={26} alt="SUN-AGENT 标志" />
        <span style={{ fontSize: '16px', fontWeight: 600, color: '#fff' }}>SUN-AGENT</span>
        <div style={{ fontSize: '12px', color: '#707070' }}>
          {currentSessionMeta?.title || currentSessionMeta?.first_message || '准备开始新的对话'}
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
        {isConnected ? '已连接' : '未连接'}
        </div>
      </div>
    </div>
  );
};
