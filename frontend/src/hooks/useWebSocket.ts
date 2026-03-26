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
    addTimelineEvent,
    setCurrentTurnId,
    startStreamingAssistant,
    appendStreamingAssistant,
    finishStreamingAssistant,
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
        case 'response_start':
          startStreamingAssistant();
          break;
        case 'response_delta':
          appendStreamingAssistant(msg.content);
          break;
        case 'response_end':
        case 'response': {
          // Complete ALL running tool calls with the same duration (only for current turn)
          if (startTimeRef.current) {
            const duration = Math.round((Date.now() - startTimeRef.current) / 1000);
            completeAllRunningTools(duration);
            startTimeRef.current = null;
          }
          setActiveTool(null);
          setLoading(false);
          // Reset current turn after response
          finishStreamingAssistant(msg.type === 'response_end' ? msg.content : msg.content);
          setCurrentTurnId(null);
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
          addTimelineEvent({
            type: 'tool_start',
            content: toolName,
            toolId,
            toolName,
          });
          break;
        }
        case 'tool_end': {
          // Complete the specific tool
          const toolId = msg.tool_id;
          const duration = Math.round(msg.duration);
          completeToolCall(toolId, duration);
          addTimelineEvent({
            type: 'tool_end',
            content: msg.content,
            toolId,
            toolName: msg.tool_name,
            duration,
          });
          break;
        }
        case 'progress':
          addTimelineEvent({
            type: 'progress',
            content: msg.content,
          });
          break;
        case 'error':
          setError(msg.content);
          setLoading(false);
          setActiveTool(null);
          startTimeRef.current = null;
          finishStreamingAssistant();
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
  }, [sessionId, addMessage, setConnected, setError, setLoading, setActiveTool, addToolCall, completeToolCall, completeAllRunningTools, addTimelineEvent, setCurrentTurnId, startStreamingAssistant, appendStreamingAssistant, finishStreamingAssistant]);

  const sendMessage = useCallback((content: string) => {
    // Don't clear old tool calls here - they're associated with previous messages
    // They'll be cleared when a new assistant response arrives
    startTimeRef.current = null;
    setActiveTool(null);
    wsService.send(content);
  }, [setActiveTool]);

  const stopMessage = useCallback(() => {
    wsService.stop();
  }, []);

  return { sendMessage, stopMessage, isConnected: wsService.isConnected };
}
