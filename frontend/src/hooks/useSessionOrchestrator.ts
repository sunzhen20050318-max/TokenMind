import { useEffect, useRef } from 'react';
import {
  installNotificationSoundUnlock,
  playReplyNotification,
} from '../services/notificationSound';
import { wsPool } from '../services/websocket';
import { useChatStore } from '../stores/chatStore';
import type { WSMessageType } from '../types';

/**
 * App-level WebSocket orchestrator.
 *
 * Maintains the WebSocket pool: keeps the foreground session connected, plus
 * any background session that still has work in flight (loading or pending
 * approval). All incoming events are dispatched into chatStore via the
 * per-session mutators so background tasks accumulate progress just like the
 * foreground one — no event is dropped when the user navigates away.
 *
 * This hook should be mounted exactly once at the App root.
 */

const EXEC_TRUST_STORAGE_KEY = 'tokenmind:trusted-exec-sessions';
const IDLE_DISCONNECT_MS = 30_000;

function readTrustedSessions(): string[] {
  try {
    const raw = window.localStorage.getItem(EXEC_TRUST_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export function useSessionOrchestrator(): void {
  const idleTimersRef = useRef<Map<string, number>>(new Map());
  // Tool-start time per session, for measuring tool durations on response_end.
  const toolStartTimesRef = useRef<Map<string, number>>(new Map());

  // Subscribe to wsPool messages once; route them into the chatStore using
  // the explicit sessionId carried in the pool dispatch (NOT chatStore's
  // currentSession, which only describes UI focus).
  useEffect(() => {
    installNotificationSoundUnlock();

    const store = useChatStore.getState();
    const trusted = new Set(readTrustedSessions());

    const unsubscribe = wsPool.onMessage((sessionId, msg: WSMessageType) => {
      // Lazily allocate a slice for background sessions so subsequent updates
      // have a stable place to land.
      store.ensureSessionSlice(sessionId);

      switch (msg.type) {
        case 'connected':
          break;
        case 'response_start':
          store.startSessionStreamingAssistant(sessionId);
          break;
        case 'response_delta':
          store.appendSessionStreamingAssistant(sessionId, msg.content);
          break;
        case 'response_end':
        case 'response': {
          const startTs = toolStartTimesRef.current.get(sessionId);
          if (startTs) {
            const duration = Math.round((Date.now() - startTs) / 1000);
            store.completeAllSessionRunningTools(sessionId, duration);
            toolStartTimesRef.current.delete(sessionId);
          }
          store.setSessionActiveTool(sessionId, null);
          store.setSessionLoading(sessionId, false);
          store.finishSessionStreamingAssistant(
            sessionId,
            msg.type === 'response_end' ? msg.content : msg.content,
            msg.citations,
            msg.attachments,
          );
          store.setSessionCurrentTurnId(sessionId, null);
          void playReplyNotification();
          break;
        }
        case 'tool':
        case 'tool_start': {
          const toolName = msg.content;
          const toolId = msg.type === 'tool_start' ? msg.tool_id : undefined;
          if (!toolStartTimesRef.current.has(sessionId)) {
            toolStartTimesRef.current.set(sessionId, Date.now());
          }
          store.setSessionActiveTool(sessionId, toolName);
          store.addSessionToolCall(sessionId, toolName, toolId);
          store.addSessionTimelineEvent(sessionId, {
            type: 'tool_start',
            content: toolName,
            toolId,
            toolName,
          });
          break;
        }
        case 'tool_end': {
          const toolId = msg.tool_id;
          const duration = Math.round(msg.duration);
          store.completeSessionToolCall(sessionId, toolId, duration);
          store.addSessionTimelineEvent(sessionId, {
            type: 'tool_end',
            content: msg.content,
            toolId,
            toolName: msg.tool_name,
            duration,
          });
          break;
        }
        case 'tool_error':
          store.failSessionToolCall(sessionId, msg.tool_id);
          store.addSessionTimelineEvent(sessionId, {
            type: 'tool_error',
            content: msg.content,
            toolId: msg.tool_id,
            toolName: msg.tool_name,
            detail: msg.detail,
          });
          store.setSessionActiveTool(sessionId, null);
          break;
        case 'progress':
          store.addSessionTimelineEvent(sessionId, {
            type: 'progress',
            content: msg.content,
          });
          break;
        case 'reasoning':
          // Model thinking content (DeepSeek-R1 / Qwen Thinking / Kimi
          // Thinking etc.) — render as its own collapsible row inside
          // ToolChain, in temporal order with tool calls.
          store.addSessionTimelineEvent(sessionId, {
            type: 'reasoning',
            content: msg.content,
          });
          break;
        case 'guidance_received':
          // Server confirmed it queued the guidance — append a user
          // bubble flagged as guidance so the chat shows what the user
          // told the agent without spawning a brand-new turn.
          store.addSessionMessage(sessionId, {
            role: 'user',
            content: msg.content,
            timestamp: new Date().toISOString(),
            is_guidance: true,
          });
          break;
        case 'session_title_updated':
          // Auto-generated title arrived from the background summarizer.
          store.applySessionTitle(msg.session_id, msg.title);
          break;
        case 'approval_required':
          if (trusted.has(sessionId) || store.getSessionSlice(sessionId).sessionExecTrusted) {
            wsPool.respondToToolApproval(sessionId, msg.approval_id, true);
            break;
          }
          store.setSessionPendingApproval(sessionId, {
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
          store.setSessionError(sessionId, msg.content);
          store.setSessionLoading(sessionId, false);
          store.setSessionActiveTool(sessionId, null);
          toolStartTimesRef.current.delete(sessionId);
          store.finishSessionStreamingAssistant(sessionId);
          store.setSessionPendingApproval(sessionId, null);
          break;
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // Push wsPool open/close transitions into the chatStore so any component
  // that wants to react to connection state can subscribe to the store.
  // Polling `wsPool.isConnected(...)` synchronously in render leaves the UI
  // stuck — the WebSocket can transition without React being told.
  useEffect(() => {
    const setSessionConnected = useChatStore.getState().setSessionConnected;
    const unsubscribe = wsPool.onConnectionChange((sessionId, connected) => {
      setSessionConnected(sessionId, connected);
    });
    return () => {
      unsubscribe();
    };
  }, []);

  // Drive the pool: ensure the current session is connected; keep alive any
  // background session with running work; idle-evict the rest after a delay.
  useEffect(() => {
    const unsub = useChatStore.subscribe((state, prev) => {
      // Cheap guard: re-evaluate only when something connectivity-relevant moved.
      if (
        state.currentSession === prev.currentSession &&
        state.sessionsState === prev.sessionsState &&
        state.isLoading === prev.isLoading &&
        state.pendingApproval === prev.pendingApproval &&
        state.activeTool === prev.activeTool
      ) {
        return;
      }
      reconcilePool(idleTimersRef.current);
    });
    // Run once on mount in case the current session is already set.
    reconcilePool(idleTimersRef.current);
    return () => {
      unsub();
    };
  }, []);

  // Cleanup all open sockets when the App unmounts (page nav away).
  useEffect(
    () => () => {
      idleTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      idleTimersRef.current.clear();
      wsPool.disconnectAll();
    },
    [],
  );
}

function reconcilePool(idleTimers: Map<string, number>): void {
  const state = useChatStore.getState();
  const required = new Set<string>();

  if (state.currentSession) {
    required.add(state.currentSession);
  }
  // Foreground busy state implies the current session needs a live socket.
  if (state.isLoading || state.pendingApproval || state.activeTool) {
    if (state.currentSession) required.add(state.currentSession);
  }
  // Background sessions with in-flight work also need their sockets kept open.
  for (const [sessionId, slice] of Object.entries(state.sessionsState)) {
    if (slice.isLoading || slice.pendingApproval || slice.activeTool) {
      required.add(sessionId);
    }
  }

  // Open new connections for required sessions.
  required.forEach((sessionId) => {
    void wsPool.ensureConnected(sessionId);
    // If a previously scheduled idle eviction is pending, cancel it.
    const timer = idleTimers.get(sessionId);
    if (timer) {
      window.clearTimeout(timer);
      idleTimers.delete(sessionId);
    }
  });

  // Schedule idle eviction for sockets that are open but no longer required.
  wsPool.activeSessionIds().forEach((sessionId) => {
    if (required.has(sessionId)) return;
    if (idleTimers.has(sessionId)) return;
    const timer = window.setTimeout(() => {
      idleTimers.delete(sessionId);
      // Re-check at fire time — required set may have changed.
      const latest = useChatStore.getState();
      const stillIdle =
        latest.currentSession !== sessionId &&
        !(latest.sessionsState[sessionId]?.isLoading) &&
        !(latest.sessionsState[sessionId]?.pendingApproval) &&
        !(latest.sessionsState[sessionId]?.activeTool);
      if (stillIdle) {
        wsPool.disconnect(sessionId);
      }
    }, IDLE_DISCONNECT_MS);
    idleTimers.set(sessionId, timer);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Public helpers used by ChatWindow / approval modal — replaces the previous
// useWebSocket hook surface.
// ─────────────────────────────────────────────────────────────────────────────

export function sendMessage(
  sessionId: string,
  content: string,
  attachments: Parameters<typeof wsPool.send>[2] = [],
): void {
  void wsPool.ensureConnected(sessionId);
  wsPool.send(sessionId, content, attachments);
}

export function stopSessionTask(sessionId: string): void {
  wsPool.stop(sessionId);
}

export function sendSessionGuidance(sessionId: string, content: string): void {
  void wsPool.ensureConnected(sessionId);
  wsPool.sendGuidance(sessionId, content);
}

export function respondToToolApproval(
  sessionId: string,
  approvalId: string,
  approved: boolean,
): void {
  wsPool.respondToToolApproval(sessionId, approvalId, approved);
}

export function setSessionExecTrust(sessionId: string, enabled: boolean): void {
  const next = new Set(readTrustedSessions());
  if (enabled) {
    next.add(sessionId);
  } else {
    next.delete(sessionId);
  }
  try {
    window.localStorage.setItem(EXEC_TRUST_STORAGE_KEY, JSON.stringify(Array.from(next)));
  } catch {
    // ignore storage failures
  }
  useChatStore.getState().setSessionExecTrusted(sessionId, enabled);
}

export function isSessionExecTrusted(sessionId: string): boolean {
  return readTrustedSessions().includes(sessionId);
}

/**
 * Synchronous, non-reactive check. Reads the current WebSocket readyState.
 * Use only in event handlers / imperative paths — do not call from render
 * (the value won't update when the socket transitions). For render code
 * use {@link useSessionConnected} instead.
 */
export function isSessionConnected(sessionId: string): boolean {
  return wsPool.isConnected(sessionId);
}

/**
 * Reactive hook returning whether the given session's WebSocket is OPEN.
 * Subscribes to chatStore.connectedSessions, which the orchestrator keeps
 * in sync with wsPool's open/close events.
 */
export function useSessionConnected(sessionId: string): boolean {
  return useChatStore((state) => state.connectedSessions.has(sessionId));
}
