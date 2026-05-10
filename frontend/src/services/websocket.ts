import type { Attachment, WSMessageType } from '../types';

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

class WebSocketPool {
  private connections: Map<string, PooledConnection> = new Map();
  private handlers: Set<PoolHandler> = new Set();
  private connectionListeners: Set<ConnectionListener> = new Set();

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
    };
    this.connections.set(sessionId, conn);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat?session_id=${encodeURIComponent(sessionId)}`;
    const ws = new WebSocket(wsUrl);
    conn.ws = ws;

    ws.onopen = () => {
      conn.reconnectAttempts = 0;
      this.fireConnectionChange(sessionId, true);
      resolveReady?.();
      resolveReady = null;
      rejectReady = null;
    };

    ws.onmessage = (event) => {
      try {
        const data: WSMessageType = JSON.parse(event.data);
        this.handlers.forEach((handler) => {
          try {
            handler(sessionId, data);
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
      rejectReady?.(event);
      rejectReady = null;
      resolveReady = null;
    };

    ws.onclose = () => {
      // Drop the live socket reference; reconnect logic may replace it.
      conn.ws = null;
      this.fireConnectionChange(sessionId, false);
      if (conn.closed) return;
      conn.reconnectAttempts += 1;
      const delay = backoffDelay(conn.reconnectAttempts);
      conn.reconnectTimer = window.setTimeout(() => {
        conn.reconnectTimer = null;
        if (conn.closed) return;
        // Best-effort: reuse the same conn slot, replace its ws via a fresh
        // openConnection-like flow but reusing the entry.
        this.reattachSocket(conn);
      }, delay);
    };

    return ready;
  }

  private reattachSocket(conn: PooledConnection): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat?session_id=${encodeURIComponent(conn.sessionId)}`;
    const ws = new WebSocket(wsUrl);
    conn.ws = ws;

    ws.onopen = () => {
      conn.reconnectAttempts = 0;
      this.fireConnectionChange(conn.sessionId, true);
    };

    ws.onmessage = (event) => {
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
      console.error('[wsPool] reattach error', event);
    };

    ws.onclose = () => {
      conn.ws = null;
      this.fireConnectionChange(conn.sessionId, false);
      if (conn.closed) return;
      conn.reconnectAttempts += 1;
      const delay = backoffDelay(conn.reconnectAttempts);
      conn.reconnectTimer = window.setTimeout(() => {
        conn.reconnectTimer = null;
        if (conn.closed) return;
        this.reattachSocket(conn);
      }, delay);
    };
  }

  /** Close and forget a session's socket (orchestrator-driven). */
  disconnect(sessionId: string): void {
    const conn = this.connections.get(sessionId);
    if (!conn) return;
    conn.closed = true;
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
    const ws = this.socketFor(sessionId);
    if (!ws) return;
    ws.send(
      JSON.stringify({
        type: 'message',
        content,
        attachments,
      }),
    );
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
  isConnected(sessionId: string): boolean {
    return wsPool.isConnected(sessionId);
  },
};
