import type { Attachment, WSMessageType } from '../types';
import { withSecretQuery } from './apiAuth';

/**
 * Per-session WebSocket pool.
 *
 * Each chat session gets its own WebSocket connection to the backend
 * (`/ws/chat?session_id=xxx`). The backend ConnectionManager keys connections
 * by session_id natively, so opening multiple WS at once is supported.
 *
 * The pool decouples WebSocket lifecycle from React component lifecycle —
 * which means navigating away from a chat (to settings, asset library, or
 * even another chat) does NOT drop in-flight task events.
 */

type PoolHandler = (sessionId: string, msg: WSMessageType) => void;
type ConnectionListener = (sessionId: string, connected: boolean) => void;

interface PooledConnection {
  ws: WebSocket | null;
  sessionId: string;
  reconnectAttempts: number;
  reconnectTimer: number | null;
  /** True if the consumer explicitly asked to close — skip reconnect. */
  closed: boolean;
  /** Resolves when the socket has reached OPEN at least once. */
  ready: Promise<void>;
  /** Heartbeat interval handle (null when not running). */
  heartbeatTimer: number | null;
  /** Epoch ms of the last message received (incl. pong) — drives half-open detection. */
  lastActivityAt: number;
  /** User messages queued while the socket was down, resent on reconnect. */
  pending: string[];
}

// Reconnect strategy: infinite retries with exponential backoff capped at
// 30s. Wifi switches and laptop wake-from-sleep often produce more than 5
// blips, and a permanently-dead pool entry leaves the UI stuck — so we
// never give up unless the consumer explicitly disconnects.
const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30_000;

export function backoffDelay(attempt: number): number {
  const exp = Math.min(Math.max(attempt - 1, 0), 10); // clamp before pow blows up
  return Math.min(RECONNECT_BASE_DELAY_MS * 2 ** exp, RECONNECT_MAX_DELAY_MS);
}

// Heartbeat: ping every 25s; if no message (incl. pong) arrives within the
// interval + a 10s grace, the socket is treated as half-open and force-closed
// so the existing reconnect logic kicks in. Detects dead connections that
// never fire `onclose` (laptop sleep, wifi switch).
export const HEARTBEAT_INTERVAL_MS = 25_000;
export const PONG_TIMEOUT_MS = 10_000;
// isLoading watchdog: if a session stays disconnected this long with no events,
// release the stuck "生成中" state so the user isn't trapped on a dead turn.
export const LOADING_WATCHDOG_MS = 120_000;

/** True when a socket has gone silent past one heartbeat window + pong grace,
 * i.e. it's probably half-open and should be force-reconnected. */
export function isConnectionStale(
  lastActivityAt: number,
  now: number,
  heartbeatIntervalMs: number,
  pongTimeoutMs: number,
): boolean {
  return now - lastActivityAt > heartbeatIntervalMs + pongTimeoutMs;
}

class WebSocketPool {
  private connections: Map<string, PooledConnection> = new Map();
  private handlers: Set<PoolHandler> = new Set();
  private connectionListeners: Set<ConnectionListener> = new Set();
  private globalListenersAttached = false;

  /** Notify subscribers when a session's WebSocket transitions between
   * connected (OPEN) and disconnected (any non-OPEN) state. */
  private fireConnectionChange(sessionId: string, connected: boolean): void {
    this.connectionListeners.forEach((handler) => {
      try {
        handler(sessionId, connected);
      } catch (err) {
        console.error('[wsPool] connection listener threw', err);
      }
    });
  }

  /**
   * Open (or reuse) a WebSocket for the given session. Returns a promise that
   * resolves once the socket has connected at least once.
   */
  ensureConnected(sessionId: string): Promise<void> {
    if (!sessionId) {
      return Promise.resolve();
    }
    const existing = this.connections.get(sessionId);
    if (existing && !existing.closed) {
      return existing.ready;
    }
    return this.openConnection(sessionId);
  }

  private buildUrl(sessionId: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const baseUrl = `${protocol}//${window.location.host}/ws/chat?session_id=${encodeURIComponent(sessionId)}`;
    return withSecretQuery(baseUrl);
  }

  private openConnection(sessionId: string): Promise<void> {
    let resolveReady: (() => void) | null = null;
    let rejectReady: ((err: unknown) => void) | null = null;
    const ready = new Promise<void>((resolve, reject) => {
      resolveReady = resolve;
      rejectReady = reject;
    });

    const conn: PooledConnection = {
      ws: null,
      sessionId,
      reconnectAttempts: 0,
      reconnectTimer: null,
      closed: false,
      ready,
      heartbeatTimer: null,
      lastActivityAt: 0,
      pending: [],
    };
    this.connections.set(sessionId, conn);
    this.attachSocket(conn, resolveReady ?? undefined, rejectReady ?? undefined);

    return ready;
  }

  /** Build a socket for `conn`, wire all handlers + heartbeat + resend. Used
   * for both the initial connect and every reconnect (no more duplicated
   * onopen/onmessage/onclose between two near-identical methods). */
  private attachSocket(
    conn: PooledConnection,
    resolveReady?: () => void,
    rejectReady?: (err: unknown) => void,
  ): void {
    this.ensureGlobalListeners();
    const ws = new WebSocket(this.buildUrl(conn.sessionId));
    conn.ws = ws;
    let resolve = resolveReady ?? null;
    let reject = rejectReady ?? null;

    ws.onopen = () => {
      conn.reconnectAttempts = 0;
      conn.lastActivityAt = Date.now();
      this.startHeartbeat(conn);
      this.flushPending(conn);
      this.fireConnectionChange(conn.sessionId, true);
      resolve?.();
      resolve = null;
      reject = null;
    };

    ws.onmessage = (event) => {
      conn.lastActivityAt = Date.now();
      try {
        const data: WSMessageType = JSON.parse(event.data);
        this.handlers.forEach((handler) => {
          try {
            handler(conn.sessionId, data);
          } catch (err) {
            console.error('[wsPool] handler threw', err);
          }
        });
      } catch (err) {
        console.error('[wsPool] failed to parse message', err);
      }
    };

    ws.onerror = (event) => {
      console.error('[wsPool] socket error', event);
      reject?.(event);
      reject = null;
      resolve = null;
    };

    ws.onclose = () => {
      conn.ws = null;
      this.stopHeartbeat(conn);
      this.fireConnectionChange(conn.sessionId, false);
      if (conn.closed) return;
      conn.reconnectAttempts += 1;
      const delay = backoffDelay(conn.reconnectAttempts);
      conn.reconnectTimer = window.setTimeout(() => {
        conn.reconnectTimer = null;
        if (conn.closed) return;
        this.attachSocket(conn);
      }, delay);
    };
  }

  private startHeartbeat(conn: PooledConnection): void {
    this.stopHeartbeat(conn);
    if (typeof window === 'undefined') return;
    conn.heartbeatTimer = window.setInterval(() => {
      const ws = conn.ws;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (isConnectionStale(conn.lastActivityAt, Date.now(), HEARTBEAT_INTERVAL_MS, PONG_TIMEOUT_MS)) {
        // Half-open: silent for a full window. Force-close so onclose fires and
        // reconnect runs — a silently-dead socket won't emit onclose by itself.
        try {
          ws.close();
        } catch {
          // ignore
        }
        return;
      }
      try {
        ws.send(JSON.stringify({ type: 'ping' }));
      } catch {
        // ignore — onclose/onerror handles a dead socket
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(conn: PooledConnection): void {
    if (conn.heartbeatTimer !== null) {
      if (typeof window !== 'undefined') {
        window.clearInterval(conn.heartbeatTimer);
      }
      conn.heartbeatTimer = null;
    }
  }

  /** Resend queued user messages once the socket is OPEN again. */
  private flushPending(conn: PooledConnection): void {
    const ws = conn.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const queued = conn.pending;
    conn.pending = [];
    for (const payload of queued) {
      try {
        ws.send(payload);
      } catch {
        conn.pending.push(payload);
      }
    }
  }

  /** Register window-level revive triggers once. Guarded for non-browser
   * (test) environments where `window` is absent. */
  private ensureGlobalListeners(): void {
    if (this.globalListenersAttached || typeof window === 'undefined') return;
    this.globalListenersAttached = true;
    const revive = () => this.reviveConnections();
    window.addEventListener('online', revive);
    window.addEventListener('visibilitychange', () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        revive();
      }
    });
  }

  /** Immediately reconnect any non-OPEN session — used when the tab becomes
   * visible or the network returns, instead of waiting out the backoff. */
  private reviveConnections(): void {
    this.connections.forEach((conn) => {
      if (conn.closed) return;
      const ws = conn.ws;
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
      }
      if (conn.reconnectTimer !== null) {
        window.clearTimeout(conn.reconnectTimer);
        conn.reconnectTimer = null;
      }
      conn.reconnectAttempts = 0;
      this.attachSocket(conn);
    });
  }

  /** Close and forget a session's socket (orchestrator-driven). */
  disconnect(sessionId: string): void {
    const conn = this.connections.get(sessionId);
    if (!conn) return;
    conn.closed = true;
    this.stopHeartbeat(conn);
    if (conn.reconnectTimer) {
      window.clearTimeout(conn.reconnectTimer);
      conn.reconnectTimer = null;
    }
    if (conn.ws) {
      try {
        conn.ws.close();
      } catch {
        // ignore
      }
      conn.ws = null;
    }
    this.connections.delete(sessionId);
    this.fireConnectionChange(sessionId, false);
  }

  /** Close and forget every session — used on logout/global teardown. */
  disconnectAll(): void {
    Array.from(this.connections.keys()).forEach((id) => this.disconnect(id));
  }

  send(sessionId: string, content: string, attachments: Attachment[] = []): void {
    const payload = JSON.stringify({ type: 'message', content, attachments });
    const conn = this.connections.get(sessionId);
    const ws = conn?.ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
      return;
    }
    // Socket not open: queue the user message for resend on reconnect instead
    // of silently dropping it (the old behaviour lost messages on a blip).
    if (conn && !conn.closed) {
      conn.pending.push(payload);
    }
  }

  stop(sessionId: string): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(JSON.stringify({ type: 'stop' }));
  }

  respondToToolApproval(sessionId: string, approvalId: string, approved: boolean): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(
      JSON.stringify({
        type: 'tool_approval',
        approval_id: approvalId,
        approved,
      }),
    );
  }

  respondToBrowserHandoff(sessionId: string, handoffId: string, completed: boolean): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(
      JSON.stringify({
        type: 'browser_handoff',
        handoff_id: handoffId,
        completed,
      }),
    );
  }

  respondToUserQuestion(
    sessionId: string,
    questionId: string,
    answers: Record<string, { selected: string | string[]; notes?: string }>,
  ): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(
      JSON.stringify({
        type: 'user_question_response',
        question_id: questionId,
        answers,
      }),
    );
  }

  /**
   * Send a real-time guidance hint while the agent is busy. Unlike a
   * normal user message this is queued server-side and merged into the
   * next LLM call — no new turn is started, the in-flight tool keeps
   * running.
   */
  sendGuidance(sessionId: string, content: string): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(JSON.stringify({ type: 'guidance', content }));
  }

  ping(sessionId: string): void {
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(JSON.stringify({ type: 'ping' }));
  }

  /**
   * Subscribe to all incoming messages across every session in the pool.
   * Returns an unsubscribe function.
   */
  onMessage(handler: PoolHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  /** Subscribe to OPEN/CLOSE transitions for any session. The handler is
   * called with `(sessionId, connected)` whenever a session's underlying
   * socket transitions; subscribers should make their own state reactive
   * (e.g., push into a zustand store) instead of polling `isConnected`. */
  onConnectionChange(handler: ConnectionListener): () => void {
    this.connectionListeners.add(handler);
    return () => {
      this.connectionListeners.delete(handler);
    };
  }

  isConnected(sessionId: string): boolean {
    const ws = this.connections.get(sessionId)?.ws;
    return !!ws && ws.readyState === WebSocket.OPEN;
  }

  activeSessionIds(): string[] {
    return Array.from(this.connections.keys()).filter((id) => !this.connections.get(id)?.closed);
  }

  private socketFor(sessionId: string): WebSocket | null {
    const ws = this.connections.get(sessionId)?.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return null;
    }
    return ws;
  }
}

export const wsPool = new WebSocketPool();

// Backwards-compatible facade kept around so the rest of the codebase can
// migrate progressively. New code should depend on `wsPool` directly with an
// explicit sessionId.
export const wsService = {
  connect(sessionId: string): Promise<void> {
    return wsPool.ensureConnected(sessionId);
  },
  disconnect(sessionId?: string): void {
    if (sessionId) {
      wsPool.disconnect(sessionId);
    } else {
      wsPool.disconnectAll();
    }
  },
  send(sessionId: string, content: string, attachments: Attachment[] = []): void {
    wsPool.send(sessionId, content, attachments);
  },
  stop(sessionId: string): void {
    wsPool.stop(sessionId);
  },
  respondToToolApproval(sessionId: string, approvalId: string, approved: boolean): void {
    wsPool.respondToToolApproval(sessionId, approvalId, approved);
  },
  respondToBrowserHandoff(sessionId: string, handoffId: string, completed: boolean): void {
    wsPool.respondToBrowserHandoff(sessionId, handoffId, completed);
  },
  isConnected(sessionId: string): boolean {
    return wsPool.isConnected(sessionId);
  },
};
