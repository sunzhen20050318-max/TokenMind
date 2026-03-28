import { useEffect, useCallback, useRef, useState } from 'react';
import { wsService } from '../services/websocket';
import {
  installNotificationSoundUnlock,
  playReplyNotification,
  primeNotificationSound,
} from '../services/notificationSound';
import { useChatStore } from '../stores/chatStore';
import type { Attachment, PendingToolApproval, WSMessageType } from '../types';

const EXEC_TRUST_STORAGE_KEY = 'sun-agent:trusted-exec-sessions';

function readTrustedSessions(): string[] {
  try {
    const raw = window.localStorage.getItem(EXEC_TRUST_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

function writeTrustedSessions(sessionIds: string[]): void {
  try {
    window.localStorage.setItem(EXEC_TRUST_STORAGE_KEY, JSON.stringify(sessionIds));
  } catch {
    // Ignore storage failures; trust will just fall back to in-memory behavior.
  }
}

export function useWebSocket(sessionId: string) {
  const {
    addMessage,
    setConnected,
    setError,
    setLoading,
    setActiveTool,
    addToolCall,
    completeToolCall,
    failToolCall,
    completeAllRunningTools,
    addTimelineEvent,
    setCurrentTurnId,
    startStreamingAssistant,
    appendStreamingAssistant,
    finishStreamingAssistant,
  } = useChatStore();

  const startTimeRef = useRef<number | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingToolApproval | null>(null);
  const [sessionExecTrusted, setSessionExecTrusted] = useState(false);

  useEffect(() => {
    setSessionExecTrusted(readTrustedSessions().includes(sessionId));
  }, [sessionId]);

  useEffect(() => {
    installNotificationSoundUnlock();

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
          void playReplyNotification();
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
        case 'tool_error':
          failToolCall(msg.tool_id);
          addTimelineEvent({
            type: 'tool_error',
            content: msg.content,
            toolId: msg.tool_id,
            toolName: msg.tool_name,
            detail: msg.detail,
          });
          setActiveTool(null);
          break;
        case 'progress':
          addTimelineEvent({
            type: 'progress',
            content: msg.content,
          });
          break;
        case 'approval_required':
          if (sessionExecTrusted) {
            wsService.respondToToolApproval(msg.approval_id, true);
            break;
          }
          setPendingApproval({
            approval_id: msg.approval_id,
            tool_id: msg.tool_id,
            tool_name: msg.tool_name,
            command: msg.command,
            risk_reason: msg.risk_reason,
            working_dir: msg.working_dir,
            timeout_s: msg.timeout_s,
            received_at_ms: Date.now(),
          });
          break;
        case 'error':
          setError(msg.content);
          setLoading(false);
          setActiveTool(null);
          startTimeRef.current = null;
          finishStreamingAssistant();
          setPendingApproval(null);
          break;
      }
    });

    return () => {
      unsubscribe();
      wsService.disconnect();
      setConnected(false);
      setActiveTool(null);
      startTimeRef.current = null;
      setPendingApproval(null);
    };
  }, [sessionId, sessionExecTrusted, addMessage, setConnected, setError, setLoading, setActiveTool, addToolCall, completeToolCall, failToolCall, completeAllRunningTools, addTimelineEvent, setCurrentTurnId, startStreamingAssistant, appendStreamingAssistant, finishStreamingAssistant]);

  const sendMessage = useCallback((content: string, attachments: Attachment[] = []) => {
    // Don't clear old tool calls here - they're associated with previous messages
    // They'll be cleared when a new assistant response arrives
    startTimeRef.current = null;
    setActiveTool(null);
    void primeNotificationSound();
    wsService.send(content, attachments);
  }, [setActiveTool]);

  const stopMessage = useCallback(() => {
    wsService.stop();
  }, []);

  const respondToApproval = useCallback((approved: boolean) => {
    if (!pendingApproval) {
      return;
    }
    wsService.respondToToolApproval(pendingApproval.approval_id, approved);
    setPendingApproval(null);
  }, [pendingApproval]);

  const setExecTrustForSession = useCallback((enabled: boolean) => {
    const next = new Set(readTrustedSessions());
    if (enabled) {
      next.add(sessionId);
    } else {
      next.delete(sessionId);
    }
    writeTrustedSessions(Array.from(next));
    setSessionExecTrusted(enabled);
  }, [sessionId]);

  return {
    sendMessage,
    stopMessage,
    isConnected: wsService.isConnected,
    pendingApproval,
    sessionExecTrusted,
    enableExecForSession: () => setExecTrustForSession(true),
    disableExecForSession: () => setExecTrustForSession(false),
    approvePendingTool: () => respondToApproval(true),
    rejectPendingTool: () => respondToApproval(false),
    trustAndApprovePendingTool: () => {
      setExecTrustForSession(true);
      respondToApproval(true);
    },
  };
}
