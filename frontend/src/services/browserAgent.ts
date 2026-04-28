import type {
  BrowserAgentEnvCheck,
  BrowserTask,
  BrowserTaskDetailResponse,
  BrowserTaskListResponse,
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

  async listTasks(params?: { projectId?: string; limit?: number }): Promise<BrowserTaskListResponse> {
    const search = new URLSearchParams();
    if (params?.projectId) search.set('project_id', params.projectId);
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

  artifactUrl(artifactId: string): string {
    return `${API_BASE}/browser-tasks/artifacts/${encodeURIComponent(artifactId)}/file`;
  },
};
