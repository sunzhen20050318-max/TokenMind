import React, { useCallback, useEffect, useRef, useState } from 'react';
import { shouldRestoreLastSession } from './app/sessionRestoreState';
import { AttachmentPreview } from './components/AttachmentPreview/AttachmentPreview';
import { Header } from './components/Layout/Header';
import { Sidebar } from './components/Layout/Sidebar';
import { ChatWindow } from './components/Chat/ChatWindow';
import { createProjectConversation } from './components/Projects/projectEntryFlow';
import { EntryGate } from './components/EntryGate/EntryGate';
import { KnowledgePage } from './pages/Knowledge';
import { MusicPage } from './pages/Music';
import { ProjectHome } from './pages/ProjectHome';
import { VideoPage } from './pages/Video';
import { VoiceClonePage } from './pages/voice/VoiceCloneStudio';
import { TtsPage } from './pages/voice/TtsStudio';
import { VoiceDesignPage } from './pages/voice/VoiceDesignStudio';
import { api } from './services/api';
import { useChatStore } from './stores/chatStore';
import { useSessions } from './hooks/useSessions';
import './app.css';

const LAST_SESSION_KEY = 'tokenmind:last-session';
const SIDEBAR_COLLAPSED_KEY = 'tokenmind:sidebar-collapsed';

const App: React.FC = () => {
  const {
    currentSession,
    creativeCapabilities,
    fetchModelProviders,
    loadCreativeCapabilities,
    setCurrentSession,
    activeProjectId,
    activeProject,
    queuePendingSessionStarter,
  } = useChatStore();
  const { sessions } = useSessions();
  const [gateDismissed, setGateDismissed] = useState(false);
  const [gateExiting, setGateExiting] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mainView, setMainView] = useState<
    | 'chat'
    | 'knowledge'
    | 'music'
    | 'voice-clone'
    | 'tts'
    | 'voice-design'
    | 'video'
    | 'project-home'
    | 'project-chat'
  >('chat');
  const enterTimerRef = useRef<number | null>(null);
  const appReady = gateDismissed || gateExiting;

  const handleEnter = useCallback(() => {
    if (gateDismissed || gateExiting) {
      return;
    }

    setGateExiting(true);
    enterTimerRef.current = window.setTimeout(() => {
      setGateDismissed(true);
      setGateExiting(false);
    }, 720);
  }, [gateDismissed, gateExiting]);

  useEffect(() => {
    void fetchModelProviders();
    void loadCreativeCapabilities();
  }, [fetchModelProviders, loadCreativeCapabilities]);

  useEffect(() => {
    if (!currentSession) {
      return;
    }
    window.localStorage.setItem(LAST_SESSION_KEY, currentSession);
  }, [currentSession]);

  useEffect(() => {
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (stored === 'true') {
      setSidebarCollapsed(true);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? 'true' : 'false');
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (
      !shouldRestoreLastSession({
        appReady,
        currentSession,
        sessionCount: sessions.length,
        mainView,
        activeProjectId,
      })
    ) {
      return;
    }

    const rememberedSessionId = window.localStorage.getItem(LAST_SESSION_KEY);
    const restoredSession = sessions.find((session) => session.session_id === rememberedSessionId);
    setCurrentSession(restoredSession?.session_id || sessions[0].session_id);
  }, [appReady, currentSession, sessions, setCurrentSession, mainView, activeProjectId]);

  useEffect(
    () => () => {
      if (enterTimerRef.current) {
        window.clearTimeout(enterTimerRef.current);
      }
    },
    []
  );

  return (
    <div className="app-root">
      {!gateDismissed ? <EntryGate isExiting={gateExiting} onEnter={handleEnter} /> : null}

      <div
        className={[
          'app-shell',
          gateDismissed ? 'app-shell--visible' : gateExiting ? 'app-shell--revealing' : 'app-shell--hidden',
          sidebarCollapsed ? 'app-shell--sidebar-collapsed' : '',
        ].join(' ')}
      >
        <div className="app-main">
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
            mainView={mainView}
            onSelectMainView={setMainView}
          />
          <main className="app-main__content">
            <Header />
            {mainView === 'knowledge' ? (
              <KnowledgePage isActive />
            ) : mainView === 'music' ? (
              <MusicPage
                capability={creativeCapabilities?.music}
                coverCapability={creativeCapabilities?.music_cover}
              />
            ) : mainView === 'voice-clone' ? (
              <VoiceClonePage capability={creativeCapabilities?.voice_clone} />
            ) : mainView === 'tts' ? (
              <TtsPage capability={creativeCapabilities?.tts} />
            ) : mainView === 'voice-design' ? (
              <VoiceDesignPage capability={creativeCapabilities?.voice_design} />
            ) : mainView === 'video' ? (
              <VideoPage capability={creativeCapabilities?.video} />
            ) : mainView === 'project-home' ? (
              <ProjectHome
                onStartConversation={async (message) => {
                  const projectId = activeProjectId || activeProject?.id;
                  if (!projectId) {
                    return;
                  }

                  const sessionId = await createProjectConversation({
                    projectId,
                    message,
                    generateSessionId: () => `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                    createProjectSession: async (projectId, nextSessionId) => {
                      await api.createProjectSession(projectId, nextSessionId);
                    },
                    queueSessionStarter: (content, nextSessionId) => {
                      queuePendingSessionStarter(nextSessionId, content);
                    },
                  });

                  setCurrentSession(sessionId);
                  setMainView('project-chat');
                }}
                onOpenSession={(sessionId) => {
                  setCurrentSession(sessionId);
                  setMainView('project-chat');
                }}
              />
            ) : currentSession ? (
              <ChatWindow sessionId={currentSession} />
            ) : (
              <div className="app-main__empty">点击左侧“新建对话”开始新的会话</div>
            )}
          </main>
        </div>
      </div>
      <AttachmentPreview />
    </div>
  );
};

export default App;
