import { useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';

export function useSessions() {
  const { sessions, loadSessions, setCurrentSession } = useChatStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const createNewSession = () => {
    const newSessionId = `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setCurrentSession(newSessionId);
    return newSessionId;
  };

  return { sessions, loadSessions, createNewSession };
}
