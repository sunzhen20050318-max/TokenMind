import React, { useEffect } from 'react';
import { Header } from './components/Layout/Header';
import { Sidebar } from './components/Layout/Sidebar';
import { ChatWindow } from './components/Chat/ChatWindow';
import { useChatStore } from './stores/chatStore';
import { useSessions } from './hooks/useSessions';

const App: React.FC = () => {
  const { currentSession } = useChatStore();
  const { createNewSession } = useSessions();

  useEffect(() => {
    if (!currentSession) {
      createNewSession();
    }
  }, [currentSession, createNewSession]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
      }}
    >
      <Header />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <main style={{ flex: 1, overflow: 'hidden' }}>
          {currentSession ? (
            <ChatWindow sessionId={currentSession} />
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: '#6e6e73',
                fontSize: '14px',
              }}
            >
              Select a conversation or start a new one
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
