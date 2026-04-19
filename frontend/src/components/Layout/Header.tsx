import React from 'react';
import { useChatStore } from '../../stores/chatStore';
import './header.css';

const LOADING_MODEL = '\u6b63\u5728\u8bfb\u53d6\u6a21\u578b...';
const MODEL_UNAVAILABLE = '\u6a21\u578b\u72b6\u6001\u4e0d\u53ef\u7528';
const MODEL_NOT_SET = '\u672a\u8bbe\u7f6e\u9ed8\u8ba4\u6a21\u578b';
const READY_FOR_CHAT = '\u51c6\u5907\u5f00\u59cb\u65b0\u7684\u5bf9\u8bdd';
const PROJECT_SUFFIX = '\u00b7 \u9879\u76ee';
const CONNECTED = '\u5df2\u8fde\u63a5';
const DISCONNECTED = '\u672a\u8fde\u63a5';

export const Header: React.FC = () => {
  const {
    isConnected,
    currentSession,
    sessions,
    projectSessions,
    projects,
    activeProjectId,
    activeProject,
    activeModelId,
    modelProviders,
    modelProvidersStatus,
  } = useChatStore();

  const currentSessionMeta =
    sessions.find((session) => session.session_id === currentSession) ||
    projectSessions.find((session) => session.session_id === currentSession);
  const resolvedActiveProject = activeProject || projects.find((project) => project.id === activeProjectId);

  const currentModel = (() => {
    if (modelProvidersStatus === 'idle' || modelProvidersStatus === 'loading') {
      return LOADING_MODEL;
    }

    if (activeModelId) {
      return modelProviders.find((provider) => provider.id === activeModelId)?.name || activeModelId;
    }

    if (modelProvidersStatus === 'error') {
      return MODEL_UNAVAILABLE;
    }

    return MODEL_NOT_SET;
  })();

  const sessionLabel =
    currentSessionMeta?.title ||
    currentSessionMeta?.first_message ||
    (resolvedActiveProject ? `${resolvedActiveProject.name} ${PROJECT_SUFFIX}` : READY_FOR_CHAT);

  return (
    <header className="shell-header">
      <div className="shell-header__meta">
        <div className="shell-header__model">{currentModel}</div>
        <div className="shell-header__session">{sessionLabel}</div>
      </div>

      <div className="shell-header__status">
        <span className={`shell-header__status-dot ${isConnected ? 'is-online' : 'is-offline'}`} />
        <span>{isConnected ? CONNECTED : DISCONNECTED}</span>
      </div>
    </header>
  );
};
