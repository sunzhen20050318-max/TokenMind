import type {
  SendMessageResponse,
  ChatHistoryResponse,
  Session,
  StatusResponse,
} from '../types';

const API_BASE = '/api';

export const api = {
  async sendMessage(
    message: string,
    sessionId?: string
  ): Promise<SendMessageResponse> {
    const res = await fetch(`${API_BASE}/chat/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok) {
      throw new Error(`Failed to send message: ${res.statusText}`);
    }
    return res.json();
  },

  async getHistory(sessionId: string): Promise<ChatHistoryResponse> {
    const res = await fetch(`${API_BASE}/chat/history/${encodeURIComponent(sessionId)}`);
    if (!res.ok) {
      throw new Error(`Failed to get history: ${res.statusText}`);
    }
    return res.json();
  },

  async listSessions(): Promise<{ sessions: Session[] }> {
    const res = await fetch(`${API_BASE}/sessions`);
    if (!res.ok) {
      throw new Error(`Failed to list sessions: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteSession(sessionId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Failed to delete session: ${res.statusText}`);
    }
  },

  async clearSession(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/clear`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to clear session: ${res.statusText}`);
    }
    return res.json();
  },

  async getStatus(): Promise<StatusResponse> {
    const res = await fetch(`${API_BASE}/status`);
    if (!res.ok) {
      throw new Error(`Failed to get status: ${res.statusText}`);
    }
    return res.json();
  },
};
