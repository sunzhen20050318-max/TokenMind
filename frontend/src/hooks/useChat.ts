import { useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { api } from '../services/api';

export function useChat() {
  const { currentSession, addMessage, setLoading, setError } = useChatStore();

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || !currentSession) return;

      // Add user message immediately
      addMessage({
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      });

      setLoading(true);
      setError(null);

      try {
        const response = await api.sendMessage(content, currentSession);
        addMessage({
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to send message');
      } finally {
        setLoading(false);
      }
    },
    [currentSession, addMessage, setLoading, setError]
  );

  return { sendMessage };
}
