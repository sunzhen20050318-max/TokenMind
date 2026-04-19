import React from 'react';
import { useChatStore } from '../../stores/chatStore';
import './header.css';

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

  const sessionLabel = currentSessionMeta?.title || currentSessionMeta?.first_message || '准备开始新的对话';

  return (
    <header className="shell-header">
      <div className="shell-header__meta">
        <div className="shell-header__model">{currentModel}</div>
        <div className="shell-header__session">{sessionLabel}</div>
      </div>

      <div className="shell-header__status">
        <span className={`shell-header__status-dot ${isConnected ? 'is-online' : 'is-offline'}`} />
        <span>{isConnected ? '已连接' : '未连接'}</span>
      </div>
    </header>
  );
};
