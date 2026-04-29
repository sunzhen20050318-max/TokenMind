import type {
  BrowserAgentEnvCheck,
  BrowserTask,
  BrowserTaskDetailResponse,
  BrowserTaskListResponse,
  ContinueBrowserTaskRequest,
  CreateBrowserTaskRequest,
} from '../types/browserAgent';

const API_BASE = '/api';

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail: string | null = null;
    try {
      const data = await res.json();
      detail = typeof data?.detail === 'string' ? data.detail : null;
    } catch {
      detail = null;
    }
    throw new Error(detail || `${action}: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const browserAgentApi = {
  async getEnvCheck(): Promise<BrowserAgentEnvCheck> {
    const res = await fetch(`${API_BASE}/browser-agent/env-check`);
    return jsonOrThrow<BrowserAgentEnvCheck>(res, 'env-check');
  },

  async listTasks(params?: {
    projectId?: string;
    sessionId?: string;
    limit?: number;
  }): Promise<BrowserTaskListResponse> {
    const search = new URLSearchParams();
    if (params?.projectId) search.set('project_id', params.projectId);
    if (params?.sessionId) search.set('session_id', params.sessionId);
    if (params?.limit) search.set('limit', String(params.limit));
    const suffix = search.toString();
    const res = await fetch(`${API_BASE}/browser-tasks${suffix ? `?${suffix}` : ''}`);
    return jsonOrThrow<BrowserTaskListResponse>(res, 'list browser tasks');
  },

  async createTask(payload: CreateBrowserTaskRequest): Promise<{ task: BrowserTask }> {
    const res = await fetch(`${API_BASE}/browser-tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return jsonOrThrow<{ task: BrowserTask }>(res, 'create browser task');
  },

  async continueTask(
    taskId: string,
    payload: ContinueBrowserTaskRequest,
  ): Promise<{ task: BrowserTask }> {
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/continue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return jsonOrThrow<{ task: BrowserTask }>(res, 'continue browser task');
  },

  async getTask(taskId: string): Promise<BrowserTaskDetailResponse> {
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}`);
    return jsonOrThrow<BrowserTaskDetailResponse>(res, 'get browser task');
  },

  async cancelTask(taskId: string): Promise<{ task_id: string; cancelled: boolean }> {
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: 'POST',
    });
    return jsonOrThrow<{ task_id: string; cancelled: boolean }>(res, 'cancel browser task');
  },

  async takeoverTask(taskId: string, reason = '用户主动接管'): Promise<{ accepted: boolean }> {
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/takeover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    return jsonOrThrow<{ accepted: boolean }>(res, 'takeover browser task');
  },

  async resumeTask(taskId: string, note?: string): Promise<{ resumed: boolean }> {
    const hasNote = Boolean(note?.trim());
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/resume`, {
      method: 'POST',
      ...(hasNote
        ? {
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: note?.trim() }),
          }
        : {}),
    });
    return jsonOrThrow<{ resumed: boolean }>(res, 'resume browser task');
  },

  async intervene(
    taskId: string,
    action:
      | 'click_xy'
      | 'type'
      | 'press'
      | 'scroll'
      | 'open'
      | 'back'
      | 'forward'
      | 'reload'
      | 'wait',
    args: Record<string, unknown>,
  ): Promise<{ ok: boolean }> {
    const res = await fetch(`${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/intervene`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, args }),
    });
    return jsonOrThrow<{ ok: boolean }>(res, 'intervene browser task');
  },

  artifactUrl(artifactId: string): string {
    return `${API_BASE}/browser-tasks/artifacts/${encodeURIComponent(artifactId)}/file`;
  },

  /**
   * Open a WebSocket subscription for live task events. The server flushes
   * the replay buffer first, so the caller always sees the full timeline.
   */
  openStream(taskId: string): WebSocket {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}${API_BASE}/browser-tasks/${encodeURIComponent(taskId)}/stream`;
    return new WebSocket(url);
  },
};
