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
  MusicGenerateRequest,
  MusicGenerateResponse,
  SkillListResponse,
  SkillSuggestion,
  SkillSuggestionListResponse,
  SkillSummary,
  TtsSynthesizeRequest,
  TtsSynthesizeResponse,
  TtsVoiceListResponse,
  VoiceCloneCreateRequest,
  VoiceCloneCreateResponse,
  VoiceCloneListResponse,
  VoiceCloneRecord,
  VoiceCloneUploadResponse,
  VoiceDesignCreateRequest,
  VoiceDesignCreateResponse,
} from '../types';
import type {
  AssetActionResponse,
  AssetCategory,
  AssetItem,
  AssetListResponse,
} from '../types/assets';
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
  ChannelCatalogEntry,
  ChannelCatalogResponse,
  ChannelConfigUpdate,
  ChannelName,
  CreativeCapabilityKey,
  CreativeCapabilitySettings,
  CreativeCapabilitySettingsUpdate,
  McpServerSettingsUpdate,
  McpToolsResponse,
  ProviderSettingsUpdate,
  RuntimeSettingsUpdate,
  ToolsSettingsUpdate,
} from '../types/config';
import type {
  KnowledgeBaseType,
  KnowledgeDetailResponse,
  KnowledgeDocument,
  KnowledgeOverviewResponse,
  WikiGraphData,
  WikiPageListResponse,
} from '../types/knowledge';
import type { UsageAggregateResponse, UsageQuery } from '../types/usage';

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

  async deleteSessionMessage(sessionId: string, timestamp: string): Promise<void> {
    const params = new URLSearchParams({ timestamp });
    const res = await fetch(
      `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages?${params.toString()}`,
      { method: 'DELETE' },
    );
    if (!res.ok) {
      throw new Error(`Failed to delete message: ${res.statusText}`);
    }
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

  getAttachmentUrl(attachmentId: string): string {
    return `${API_BASE}/chat/attachments/${encodeURIComponent(attachmentId)}`;
  },

  async generateMusic(payload: MusicGenerateRequest): Promise<MusicGenerateResponse> {
    const res = await fetch(`${API_BASE}/creative/music/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to generate music: ${res.statusText}`);
    }
    return res.json();
  },

  async uploadVoiceCloneAudio(file: File): Promise<VoiceCloneUploadResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('purpose', 'voice_clone');
    const res = await fetch(`${API_BASE}/creative/voice/clone/upload`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to upload clone audio: ${res.statusText}`);
    }
    return res.json();
  },

  async createVoiceClone(payload: VoiceCloneCreateRequest): Promise<VoiceCloneCreateResponse> {
    const res = await fetch(`${API_BASE}/creative/voice/clone/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to create voice clone: ${res.statusText}`);
    }
    return res.json();
  },

  async listVoiceClones(options: { source?: 'clone' | 'design' } = {}): Promise<VoiceCloneRecord[]> {
    const url = new URL(`${API_BASE}/creative/voice/clone/list`, window.location.origin);
    if (options.source) {
      url.searchParams.set('source', options.source);
    }
    const res = await fetch(url.toString().replace(window.location.origin, ''));
    if (!res.ok) {
      throw new Error(`Failed to load voice clones: ${res.statusText}`);
    }
    const payload = (await res.json()) as VoiceCloneListResponse;
    return payload.items ?? [];
  },

  async designVoice(payload: VoiceDesignCreateRequest): Promise<VoiceDesignCreateResponse> {
    const res = await fetch(`${API_BASE}/creative/voice/design/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to design voice: ${res.statusText}`);
    }
    return res.json();
  },

  async keepAliveVoiceClone(voiceId: string): Promise<VoiceCloneRecord> {
    const res = await fetch(
      `${API_BASE}/creative/voice/clone/${encodeURIComponent(voiceId)}/keep-alive`,
      { method: 'POST' },
    );
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to keep voice alive: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteVoiceClone(voiceId: string): Promise<VoiceCloneRecord> {
    const res = await fetch(`${API_BASE}/creative/voice/clone/${encodeURIComponent(voiceId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to delete voice clone: ${res.statusText}`);
    }
    return res.json();
  },

  getVoiceCloneDemoUrl(attachmentId: string): string {
    return `${API_BASE}/chat/attachments/${encodeURIComponent(attachmentId)}`;
  },

  async synthesizeVoice(payload: TtsSynthesizeRequest): Promise<TtsSynthesizeResponse> {
    const res = await fetch(`${API_BASE}/creative/voice/tts/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to synthesize speech: ${res.statusText}`);
    }
    return res.json();
  },

  async listSkills(): Promise<SkillSummary[]> {
    const res = await fetch(`${API_BASE}/skills/list`);
    if (!res.ok) {
      throw new Error(`Failed to load skills: ${res.statusText}`);
    }
    const payload = (await res.json()) as SkillListResponse;
    return payload.items ?? [];
  },

  async setSkillEnabled(name: string, enabled: boolean): Promise<SkillSummary> {
    const res = await fetch(
      `${API_BASE}/skills/${encodeURIComponent(name)}/enabled`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      },
    );
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to update skill: ${res.statusText}`);
    }
    return res.json();
  },

  async listSkillSuggestions(): Promise<SkillSuggestion[]> {
    const res = await fetch(`${API_BASE}/skills/suggestions`);
    if (!res.ok) {
      throw new Error(`Failed to load skill suggestions: ${res.statusText}`);
    }
    const payload = (await res.json()) as SkillSuggestionListResponse;
    return payload.items ?? [];
  },

  async approveSkillSuggestion(id: string, overwrite = false): Promise<SkillSuggestion> {
    const res = await fetch(`${API_BASE}/skills/suggestions/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overwrite }),
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to approve skill suggestion: ${res.statusText}`);
    }
    return (await res.json()) as SkillSuggestion;
  },

  async rejectSkillSuggestion(id: string): Promise<{ deleted: boolean }> {
    const res = await fetch(`${API_BASE}/skills/suggestions/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      const detail =
        error && typeof error === 'object' && 'detail' in error && typeof error.detail === 'string'
          ? error.detail
          : null;
      throw new Error(detail || `Failed to reject skill suggestion: ${res.statusText}`);
    }
    return (await res.json()) as { deleted: boolean };
  },

  async getUsageAggregate(query: UsageQuery): Promise<UsageAggregateResponse> {
    const params = new URLSearchParams({ groupBy: query.groupBy });
    if (query.start) params.set('start', query.start);
    if (query.end) params.set('end', query.end);
    if (query.provider) params.set('provider', query.provider);
    if (query.model) params.set('model', query.model);
    if (query.sessionId) params.set('sessionId', query.sessionId);
    if (query.limit) params.set('limit', String(query.limit));
    const res = await fetch(`${API_BASE}/usage/aggregate?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Failed to load usage: ${res.statusText}`);
    }
    return (await res.json()) as UsageAggregateResponse;
  },

  async listTtsVoices(): Promise<TtsVoiceListResponse> {
    const res = await fetch(`${API_BASE}/creative/voice/tts/voices`);
    if (!res.ok) {
      throw new Error(`Failed to load voices: ${res.statusText}`);
    }
    return res.json();
  },

  async retainAttachment(attachmentId: string): Promise<Attachment> {
    const res = await fetch(`${API_BASE}/chat/attachments/${encodeURIComponent(attachmentId)}/retain`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new Error(error?.detail || `Failed to retain attachment: ${res.statusText}`);
    }
    const payload = await res.json();
    return payload.attachment as Attachment;
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

  async listAssets(params: {
    category: AssetCategory;
    favorite?: boolean;
    cursor?: number;
    limit?: number;
  }): Promise<AssetListResponse> {
    const search = new URLSearchParams({ category: params.category });
    if (params.favorite !== undefined) {
      search.set('favorite', String(params.favorite));
    }
    if (params.cursor !== undefined) {
      search.set('cursor', String(params.cursor));
    }
    if (params.limit !== undefined) {
      search.set('limit', String(params.limit));
    }
    const res = await fetch(`${API_BASE}/assets?${search.toString()}`);
    if (!res.ok) {
      throw new Error(`Failed to list assets: ${res.statusText}`);
    }
    return res.json();
  },

  async setAssetFavorite(assetId: string, favorite: boolean): Promise<AssetItem> {
    const res = await fetch(`${API_BASE}/assets/${encodeURIComponent(assetId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ favorite }),
    });
    if (!res.ok) {
      throw new Error(`Failed to update asset: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteAsset(assetId: string): Promise<AssetActionResponse> {
    const res = await fetch(`${API_BASE}/assets/${encodeURIComponent(assetId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Failed to delete asset: ${res.statusText}`);
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

  async patchSession(
    sessionId: string,
    payload: { active_wiki_kb_id?: string | null },
  ): Promise<{ session_id: string; active_wiki_kb_id: string | null }> {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to patch session: ${res.statusText}`);
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
  ): Promise<{
    success: boolean;
    provider: string;
    config: AppConfigResponse['providers'][string];
    defaults: { model: string; provider: string };
  }> {
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

  async updateCreativeCapability(
    capability: CreativeCapabilityKey,
    config: CreativeCapabilitySettingsUpdate
  ): Promise<{ success: boolean; capability: string; config: CreativeCapabilitySettings }> {
    const res = await fetch(`${API_BASE}/config/creative/${encodeURIComponent(capability)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      throw new Error(`Failed to update creative capability: ${res.statusText}`);
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

  async listChannels(): Promise<ChannelCatalogResponse> {
    const res = await fetch(`${API_BASE}/config/channels`);
    if (!res.ok) {
      throw new Error(`Failed to load channels: ${res.statusText}`);
    }
    return res.json();
  },

  async updateChannel(
    name: ChannelName,
    update: ChannelConfigUpdate,
  ): Promise<{ success: boolean; name: ChannelName; config: ChannelCatalogEntry['config'] }> {
    const res = await fetch(`${API_BASE}/config/channels/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    if (!res.ok) {
      throw new Error(`Failed to update channel: ${res.statusText}`);
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

  async createKnowledgeBase(payload: {
    name: string;
    description: string;
    type?: KnowledgeBaseType;
    language?: string;
  }): Promise<KnowledgeDetailResponse | KnowledgeOverviewResponse | Record<string, unknown>> {
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

  async listWikiPages(id: string): Promise<WikiPageListResponse> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/pages`);
    if (!res.ok) {
      throw new Error(`Failed to list wiki pages: ${res.statusText}`);
    }
    return res.json();
  },

  async getWikiGraph(id: string): Promise<WikiGraphData> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/graph`);
    if (!res.ok) {
      throw new Error(`Failed to load wiki graph: ${res.statusText}`);
    }
    return res.json();
  },

  async rebuildWikiGraph(id: string): Promise<WikiGraphData> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/graph/rebuild`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to rebuild wiki graph: ${res.statusText}`);
    }
    return res.json();
  },

  async recompileWikiSources(id: string): Promise<{
    processed: number;
    results: Array<{ document_id: string; status: string; error?: string }>;
  }> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/recompile`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to recompile wiki sources: ${res.statusText}`);
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
