import { useEffect, useCallback, useRef } from 'react';
import { wsService } from '../services/websocket';
import { useChatStore } from '../stores/chatStore';
import type { WSMessageType } from '../types';

export function useWebSocket(sessionId: string) {
  const {
    addMessage,
    setConnected,
    setError,
    setLoading,
    setActiveTool,
    addToolCall,
    completeToolCall,
    completeAllRunningTools,
    clearOldToolCalls,
    setCurrentTurnId,
  } = useChatStore();

  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    wsService.connect(sessionId).then(() => {
      setConnected(true);
    }).catch(() => {
      setError('Failed to connect to server');
      setConnected(false);
    });

    const unsubscribe = wsService.onMessage((msg: WSMessageType) => {
      switch (msg.type) {
        case 'connected':
          break;
        case 'response': {
          // Complete ALL running tool calls with the same duration (only for current turn)
          if (startTimeRef.current) {
            const duration = Math.round((Date.now() - startTimeRef.current) / 1000);
            completeAllRunningTools(duration);
            startTimeRef.current = null;
          }
          setActiveTool(null);
          setLoading(false);

          // Clear tool calls from previous turns (keep current turn's tools visible)
          clearOldToolCalls();
          // Reset current turn after response
          setCurrentTurnId(null);

          // Add the assistant message
          addMessage({
            role: 'assistant',
            content: msg.content,
            timestamp: new Date().toISOString(),
          });
          break;
        }
        case 'tool':
        case 'tool_start': {
          // Any tool event starts the timer and adds the tool
          // For tool_start: use content (full command), not tool_name
          const toolName = msg.content;
          const toolId = msg.type === 'tool_start' ? msg.tool_id : undefined;

          if (!startTimeRef.current) {
            startTimeRef.current = Date.now();
          }
          setActiveTool(toolName);
          addToolCall(toolName, toolId);
          break;
        }
        case 'tool_end': {
          // Complete the specific tool
          const toolId = msg.tool_id;
          const duration = Math.round(msg.duration);
          completeToolCall(toolId, duration);
          break;
        }
        case 'progress':
          break;
        case 'error':
          setError(msg.content);
          setLoading(false);
          setActiveTool(null);
          startTimeRef.current = null;
          break;
      }
    });

    return () => {
      unsubscribe();
      wsService.disconnect();
      setConnected(false);
      setActiveTool(null);
      startTimeRef.current = null;
    };
  }, [sessionId, addMessage, setConnected, setError, setLoading, setActiveTool, addToolCall, completeToolCall, completeAllRunningTools, clearOldToolCalls, setCurrentTurnId]);

  const sendMessage = useCallback((content: string) => {
    // Don't clear old tool calls here - they're associated with previous messages
    // They'll be cleared when a new assistant response arrives
    startTimeRef.current = null;
    setActiveTool(null);
    wsService.send(content);
  }, [setActiveTool]);

  return { sendMessage, isConnected: wsService.isConnected };
}