import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Header } from './components/Layout/Header';
import { Sidebar } from './components/Layout/Sidebar';
import { ChatWindow } from './components/Chat/ChatWindow';
import { EntryGate } from './components/EntryGate/EntryGate';
import { useChatStore } from './stores/chatStore';
import { useSessions } from './hooks/useSessions';
import './app.css';

const App: React.FC = () => {
  const { currentSession, fetchModelProviders } = useChatStore();
  const { createNewSession } = useSessions();
  const [gateDismissed, setGateDismissed] = useState(false);
  const [gateExiting, setGateExiting] = useState(false);
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
    if (appReady && !currentSession) {
      createNewSession();
    }
  }, [appReady, currentSession, createNewSession]);

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
        ].join(' ')}
      >
      <Header />
      <div className="app-main">
        <Sidebar />
        <main className="app-main__content">
          {currentSession ? (
            <ChatWindow sessionId={currentSession} />
          ) : (
            <div className="app-main__empty">
              Select a conversation or start a new one
            </div>
          )}
        </main>
      </div>
      </div>
    </div>
  );
};

export default App;
