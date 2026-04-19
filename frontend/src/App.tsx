import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Header } from './components/Layout/Header';
import { Sidebar } from './components/Layout/Sidebar';
import { ChatWindow } from './components/Chat/ChatWindow';
import { EntryGate } from './components/EntryGate/EntryGate';
import { KnowledgePage } from './pages/Knowledge';
import { useChatStore } from './stores/chatStore';
import { useSessions } from './hooks/useSessions';
import './app.css';

const LAST_SESSION_KEY = 'tokenmind:last-session';
const LEGACY_LAST_SESSION_KEY = 'sun-agent:last-session';
const SIDEBAR_COLLAPSED_KEY = 'tokenmind:sidebar-collapsed';

const App: React.FC = () => {
  const { currentSession, fetchModelProviders, setCurrentSession } = useChatStore();
  const { sessions } = useSessions();
  const [gateDismissed, setGateDismissed] = useState(false);
  const [gateExiting, setGateExiting] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mainView, setMainView] = useState<'chat' | 'knowledge'>('chat');
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
  }, [fetchModelProviders]);

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
    if (!appReady || currentSession || sessions.length === 0) {
      return;
    }

    const rememberedSessionId =
      window.localStorage.getItem(LAST_SESSION_KEY) ||
      window.localStorage.getItem(LEGACY_LAST_SESSION_KEY);
    const restoredSession = sessions.find((session) => session.session_id === rememberedSessionId);
    setCurrentSession(restoredSession?.session_id || sessions[0].session_id);
  }, [appReady, currentSession, sessions, setCurrentSession]);

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
            ) : currentSession ? (
              <ChatWindow sessionId={currentSession} />
            ) : (
              <div className="app-main__empty">点击左侧“新建对话”开始新的会话</div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default App;
