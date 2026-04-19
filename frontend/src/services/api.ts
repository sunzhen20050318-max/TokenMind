import type {
  SendMessageResponse,
  ChatHistoryResponse,
  Project,
  ProjectDetailResponse,
  Session,
  StatusResponse,
  UploadFilesResponse,
  Attachment,
  UploadProgress,
} from '../types';
import type { CreateCronJobPayload, CronJob, CronStatus } from '../types/cron';
import type {
  DeleteStorageFileResponse,
  StorageCleanupResponse,
  StorageOverviewResponse,
} from '../types/storage';
import type { LongTermMemoryState, MemoryOverviewResponse } from '../types/memory';
import type {
  AgentSettingsUpdate,
  AppConfigResponse,
  McpServerSettingsUpdate,
  McpToolsResponse,
  ProviderSettingsUpdate,
  RuntimeSettingsUpdate,
  ToolsSettingsUpdate,
} from '../types/config';
import type { KnowledgeDetailResponse, KnowledgeDocument, KnowledgeOverviewResponse } from '../types/knowledge';

const API_BASE = '/api';

export const api = {
  async sendMessage(
    message: string,
    sessionId?: string,
    attachments: Attachment[] = []
  ): Promise<SendMessageResponse> {
    const res = await fetch(`${API_BASE}/chat/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId, attachments }),
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

  async listProjects(): Promise<{ items: Project[] }> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) {
      throw new Error(`Failed to list projects: ${res.statusText}`);
    }
    return res.json();
  },

  async createProject(name: string): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to create project: ${res.statusText}`);
    }
    return res.json();
  },

  async getProject(projectId: string): Promise<ProjectDetailResponse> {
    const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to load project: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteProject(
    projectId: string
  ): Promise<{ success: boolean; project_id: string; deleted_session_count: number }> {
    const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to delete project: ${res.statusText}`);
    }
    return res.json();
  },

  async createProjectSession(projectId: string, sessionId: string, title?: string): Promise<Session> {
    const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, title }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to create project session: ${res.statusText}`);
    }
    return res.json();
  },

  async moveSessionToProject(projectId: string, sessionId: string): Promise<{ session: Session }> {
    const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/sessions/link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to move session to project: ${res.statusText}`);
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

  async getCronStatus(): Promise<CronStatus> {
    const res = await fetch(`${API_BASE}/cron/status`);
    if (!res.ok) {
      throw new Error(`Failed to get cron status: ${res.statusText}`);
    }
    return res.json();
  },

  async uploadFiles(
    sessionId: string,
    files: File[],
    onProgress?: (progress: UploadProgress) => void
  ): Promise<UploadFilesResponse> {
    const formData = new FormData();
    const fallbackTotal = files.reduce((sum, file) => sum + file.size, 0);
    formData.append('session_id', sessionId);
    files.forEach((file) => {
      formData.append('files', file);
    });

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/chat/upload`, true);

      xhr.upload.onprogress = (event) => {
        const total = event.lengthComputable ? event.total : fallbackTotal;
        if (!total) {
          return;
        }
        onProgress?.({
          loaded: event.loaded,
          total,
          percent: Math.min(100, Math.round((event.loaded / total) * 100)),
        });
      };

      xhr.onerror = () => {
        reject(new Error('文件上传失败，请检查网络连接后重试'));
      };

      xhr.onload = () => {
        let payload: UploadFilesResponse | { detail?: string } | null = null;
        try {
          payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        } catch {
          payload = null;
        }

        if (xhr.status >= 200 && xhr.status < 300 && payload) {
          onProgress?.({
            loaded: fallbackTotal,
            total: fallbackTotal,
            percent: 100,
          });
          resolve(payload as UploadFilesResponse);
          return;
        }

        const detail =
          payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string'
            ? payload.detail
            : `Failed to upload files: ${xhr.statusText}`;
        reject(new Error(detail));
      };

      xhr.send(formData);
    });
  },

  async listCronJobs(includeDisabled = true): Promise<CronJob[]> {
    const res = await fetch(`${API_BASE}/cron/jobs?include_disabled=${includeDisabled ? 'true' : 'false'}`);
    if (!res.ok) {
      throw new Error(`Failed to list cron jobs: ${res.statusText}`);
    }
    return res.json();
  },

  async createCronJob(payload: CreateCronJobPayload): Promise<CronJob> {
    const res = await fetch(`${API_BASE}/cron/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to create cron job: ${res.statusText}`);
    }
    return res.json();
  },

  async toggleCronJob(jobId: string, enabled: boolean): Promise<CronJob> {
    const res = await fetch(`${API_BASE}/cron/jobs/${encodeURIComponent(jobId)}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to update cron job: ${res.statusText}`);
    }
    return res.json();
  },

  async runCronJob(jobId: string): Promise<{ success: boolean; job_id: string }> {
    const res = await fetch(`${API_BASE}/cron/jobs/${encodeURIComponent(jobId)}/run`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to run cron job: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteCronJob(jobId: string): Promise<{ success: boolean; job_id: string }> {
    const res = await fetch(`${API_BASE}/cron/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to delete cron job: ${res.statusText}`);
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

  async getStorageOverview(): Promise<StorageOverviewResponse> {
    const res = await fetch(`${API_BASE}/storage`);
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to load storage overview: ${res.statusText}`);
    }
    return res.json();
  },

  async cleanupStorage(): Promise<StorageCleanupResponse> {
    const res = await fetch(`${API_BASE}/storage/cleanup`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to cleanup storage: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteStoredFile(path: string): Promise<DeleteStorageFileResponse> {
    const res = await fetch(`${API_BASE}/storage/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to delete stored file: ${res.statusText}`);
    }
    return res.json();
  },

  async renameSession(
    sessionId: string,
    title: string | null
  ): Promise<{ session_id: string; title: string | null }> {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) {
      throw new Error(`Failed to rename session: ${res.statusText}`);
    }
    return res.json();
  },

  async getMemoryOverview(
    sessionId?: string | null,
    archiveQuery?: string
  ): Promise<MemoryOverviewResponse> {
    const params = new URLSearchParams();
    if (sessionId) {
      params.set('session_id', sessionId);
    }
    if (archiveQuery?.trim()) {
      params.set('archive_query', archiveQuery.trim());
    }
    const suffix = params.toString() ? `?${params.toString()}` : '';
    const res = await fetch(`${API_BASE}/memory${suffix}`);
    if (res.status === 404) {
      throw new Error('当前后端还没有加载记忆中心接口，请重启后端后再试。');
    }
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to load memory overview: ${res.statusText}`);
    }
    return res.json();
  },

  async updateLongTermMemory(content: string): Promise<LongTermMemoryState> {
    const res = await fetch(`${API_BASE}/memory/long-term`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (res.status === 404) {
      throw new Error('当前后端还没有加载记忆中心接口，请重启后端后再试。');
    }
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to update long-term memory: ${res.statusText}`);
    }
    return res.json();
  },

  async getConfig(): Promise<AppConfigResponse> {
    const res = await fetch(`${API_BASE}/config`);
    if (!res.ok) {
      throw new Error(`Failed to get config: ${res.statusText}`);
    }
    return res.json();
  },

  async getMcpTools(): Promise<McpToolsResponse> {
    const res = await fetch(`${API_BASE}/config/mcp-tools`);
    if (res.status === 404) {
      throw new Error('当前后端还没有加载 MCP 工具探测接口，请重启后端后再试');
    }
    if (!res.ok) {
      throw new Error(`Failed to inspect MCP tools: ${res.statusText}`);
    }
    return res.json();
  },

  async updateProviderConfig(
    providerId: string,
    config: ProviderSettingsUpdate
  ): Promise<{ success: boolean; provider: string; config: AppConfigResponse['providers'][string] }> {
    const res = await fetch(`${API_BASE}/config/providers/${encodeURIComponent(providerId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      throw new Error(`Failed to update provider config: ${res.statusText}`);
    }
    return res.json();
  },

  async updateDefaults(
    update: Partial<Pick<AppConfigResponse['agent'], 'model' | 'provider'>>
  ): Promise<{ success: boolean; defaults: { model: string; provider: string } }> {
    const res = await fetch(`${API_BASE}/config/defaults`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update defaults: ${res.statusText}`);
    }
    return res.json();
  },

  async updateAgentConfig(
    update: AgentSettingsUpdate
  ): Promise<{ success: boolean; agent: AppConfigResponse['agent'] }> {
    const res = await fetch(`${API_BASE}/config/agent`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update agent config: ${res.statusText}`);
    }
    return res.json();
  },

  async updateToolsConfig(
    update: ToolsSettingsUpdate
  ): Promise<{ success: boolean; tools: AppConfigResponse['tools'] }> {
    const res = await fetch(`${API_BASE}/config/tools`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update tools config: ${res.statusText}`);
    }
    return res.json();
  },

  async updateRuntimeConfig(
    update: RuntimeSettingsUpdate
  ): Promise<{ success: boolean; runtime: AppConfigResponse['runtime'] }> {
    const res = await fetch(`${API_BASE}/config/runtime`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update runtime config: ${res.statusText}`);
    }
    return res.json();
  },

  async upsertMcpServer(
    serverName: string,
    update: McpServerSettingsUpdate
  ): Promise<{ success: boolean; server_name: string; server: AppConfigResponse['tools']['mcp_servers'][string] }> {
    const res = await fetch(`${API_BASE}/config/mcp-servers/${encodeURIComponent(serverName)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update MCP server: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteMcpServer(serverName: string): Promise<{ success: boolean; server_name: string }> {
    const res = await fetch(`${API_BASE}/config/mcp-servers/${encodeURIComponent(serverName)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Failed to delete MCP server: ${res.statusText}`);
    }
    return res.json();
  },

  async getKnowledgeOverview(): Promise<KnowledgeOverviewResponse> {
    const res = await fetch(`${API_BASE}/knowledge`);
    if (!res.ok) {
      throw new Error(`Failed to load knowledge overview: ${res.statusText}`);
    }
    return res.json();
  },

  async getKnowledgeDetail(id: string): Promise<KnowledgeDetailResponse> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}`);
    if (!res.ok) {
      throw new Error(`Failed to load knowledge base: ${res.statusText}`);
    }
    return res.json();
  },

  async createKnowledgeBase(payload: { name: string; description: string }): Promise<KnowledgeDetailResponse | KnowledgeOverviewResponse | Record<string, unknown>> {
    const res = await fetch(`${API_BASE}/knowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to create knowledge base: ${res.statusText}`);
    }
    return res.json();
  },

  async updateKnowledgeBase(
    id: string,
    payload: { name?: string; description?: string; enabled?: boolean }
  ): Promise<{ knowledge_base: KnowledgeDetailResponse['knowledge_base'] }> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to update knowledge base: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteKnowledgeBase(id: string): Promise<{ success: boolean; knowledge_base_id: string }> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Failed to delete knowledge base: ${res.statusText}`);
    }
    return res.json();
  },

  async uploadKnowledgeDocuments(
    id: string,
    files: File[],
    onProgress?: (progress: UploadProgress) => void
  ): Promise<{ documents: KnowledgeDocument[] }> {
    const formData = new FormData();
    const fallbackTotal = files.reduce((sum, file) => sum + file.size, 0);
    files.forEach((file) => formData.append('files', file));

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/knowledge/${encodeURIComponent(id)}/documents`, true);

      xhr.upload.onprogress = (event) => {
        const total = event.lengthComputable ? event.total : fallbackTotal;
        if (!total) {
          return;
        }
        onProgress?.({
          loaded: event.loaded,
          total,
          percent: Math.min(100, Math.round((event.loaded / total) * 100)),
        });
      };

      xhr.onerror = () => {
        reject(new Error('Failed to upload knowledge documents'));
      };

      xhr.onload = () => {
        let payload: { documents: KnowledgeDocument[] } | { detail?: string } | null = null;
        try {
          payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        } catch {
          payload = null;
        }

        if (xhr.status >= 200 && xhr.status < 300 && payload) {
          onProgress?.({
            loaded: fallbackTotal,
            total: fallbackTotal,
            percent: 100,
          });
          resolve(payload as { documents: KnowledgeDocument[] });
          return;
        }

        const detail =
          payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string'
            ? payload.detail
            : `Failed to upload knowledge documents: ${xhr.statusText}`;
        reject(new Error(detail));
      };

      xhr.send(formData);
    });
  },

  async deleteKnowledgeDocument(knowledgeBaseId: string, documentId: string): Promise<{ success: boolean }> {
    const res = await fetch(
      `${API_BASE}/knowledge/${encodeURIComponent(knowledgeBaseId)}/documents/${encodeURIComponent(documentId)}`,
      {
        method: 'DELETE',
      }
    );
    if (!res.ok) {
      throw new Error(`Failed to delete knowledge document: ${res.statusText}`);
    }
    return res.json();
  },

  async getSessionKnowledgeLinks(
    sessionId: string
  ): Promise<{ session_id: string; knowledge_base_ids: string[] }> {
    const res = await fetch(`${API_BASE}/knowledge/links/${encodeURIComponent(sessionId)}`);
    if (!res.ok) {
      throw new Error(`Failed to load session knowledge links: ${res.statusText}`);
    }
    return res.json();
  },

  async updateSessionKnowledgeLinks(
    sessionId: string,
    knowledgeBaseIds: string[]
  ): Promise<{ session_id: string; knowledge_base_ids: string[] }> {
    const res = await fetch(`${API_BASE}/knowledge/links/${encodeURIComponent(sessionId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        knowledge_base_ids: knowledgeBaseIds,
      }),
    });
    if (!res.ok) {
      throw new Error(`Failed to update session knowledge links: ${res.statusText}`);
    }
    return res.json();
  },
};
