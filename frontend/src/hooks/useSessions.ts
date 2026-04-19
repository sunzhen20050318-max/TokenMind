import { useEffect } from 'react';
import { api } from '../services/api';
import { useChatStore } from '../stores/chatStore';

export function useSessions() {
  const { sessions, loadSessions, setCurrentSession } = useChatStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const createNewSession = async () => {
    const newSessionId = `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const { activeProjectId, activeProject } = useChatStore.getState();
    const projectId = activeProjectId || activeProject?.id;
    if (projectId) {
      await api.createProjectSession(projectId, newSessionId);
    }
    setCurrentSession(newSessionId);
    return newSessionId;
  };

  return { sessions, loadSessions, createNewSession };
}
