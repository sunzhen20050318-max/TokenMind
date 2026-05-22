export interface ProviderSettings {
  api_key: string;
  api_base: string | null;
  extra_headers: Record<string, string> | null;
  default_model: string | null;
}

export type CreativeCapabilityKey =
  | 'image'
  | 'music'
  | 'music_cover'
  | 'voice_clone'
  | 'tts'
  | 'voice_design'
  | 'video';

export const CREATIVE_CAPABILITY_KEYS: CreativeCapabilityKey[] = [
  'image',
  'music',
  'music_cover',
  'voice_clone',
  'tts',
  'voice_design',
  'video',
];

export interface CreativeCapabilitySettings {
  enabled: boolean;
  provider: string;
  api_key: string;
  api_base: string | null;
  model: string;
  extra_headers: Record<string, string> | null;
}

export interface CreativeSettings {
  image: CreativeCapabilitySettings;
  music: CreativeCapabilitySettings;
  music_cover: CreativeCapabilitySettings;
  voice_clone: CreativeCapabilitySettings;
  tts: CreativeCapabilitySettings;
  voice_design: CreativeCapabilitySettings;
  video: CreativeCapabilitySettings;
}

export function createEmptyCreativeCapabilitySettings(): CreativeCapabilitySettings {
  return {
    enabled: false,
    provider: '',
    api_key: '',
    api_base: null,
    model: '',
    extra_headers: null,
  };
}

export function isCreativeCapabilityConfigured(
  capability: CreativeCapabilitySettings | null | undefined
): boolean {
  if (!capability) {
    return false;
  }
  return Boolean(capability.provider.trim() && capability.model.trim());
}

export interface AgentSettings {
  workspace: string;
  model: string;
  provider: string;
  max_tokens: number;
  context_window_tokens: number;
  temperature: number;
  max_tool_iterations: number;
  reasoning_effort: string | null;
}

export interface WebSearchSettings {
  provider: string;
  api_key: string;
  base_url: string | null;
  max_results: number;
}

export interface WebToolSettings {
  proxy: string | null;
  search: WebSearchSettings;
}

export interface ExecToolSettings {
  timeout: number;
  path_append: string;
  confirm_high_risk: boolean;
  approval_timeout_s: number;
}

export interface UploadsSettings {
  max_file_mb: number;
  max_total_mb: number;
  retention_days: number;
  cleanup_interval_hours: number;
}

export interface KnowledgeSettings {
  vector_backend: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  embedding_model: string;
  embedding_api_key: string;
  embedding_api_base: string | null;
  rerank_model: string;
  rerank_api_key: string;
  rerank_api_base: string | null;
  rerank_top_n: number;
  vlm_model: string;
  vlm_api_key: string;
  vlm_api_base: string | null;
  vlm_timeout: number;
  vlm_max_dim: number;
  vlm_max_workers: number;
}

export interface McpServerSettings {
  enabled: boolean;
  notes: string;
  icon: string;
  type: 'stdio' | 'sse' | 'streamableHttp' | null;
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
  headers: Record<string, string>;
  tool_timeout: number;
  enabled_tools: string[];
}

export interface McpDiscoveredTool {
  name: string;
  wrapped_name: string;
  description: string;
  enabled: boolean;
}

export interface McpServerToolsState {
  status: 'connected' | 'error';
  transport_type: string | null;
  tool_count: number;
  enabled_count: number;
  tools: McpDiscoveredTool[];
  error: string | null;
}

export interface ToolsSettings {
  web: WebToolSettings;
  exec: ExecToolSettings;
  uploads: UploadsSettings;
  knowledge: KnowledgeSettings;
  audit_enabled: boolean;
  restrict_to_workspace: boolean;
  mcp_servers: Record<string, McpServerSettings>;
}

export interface RuntimeSettings {
  channels: {
    send_progress: boolean;
    send_tool_hints: boolean;
  };
  gateway: {
    host: string;
    port: number;
    auth_secret: string;
  };
}

export interface AppConfigResponse {
  providers: Record<string, ProviderSettings>;
  creative: CreativeSettings;
  defaults: AgentSettings;
  agent: AgentSettings;
  tools: ToolsSettings;
  runtime: RuntimeSettings;
}

export interface McpToolsResponse {
  servers: Record<string, McpServerToolsState>;
}

export interface ProviderSettingsUpdate {
  api_key?: string;
  api_base?: string | null;
  extra_headers?: Record<string, string> | null;
  default_model?: string | null;
}

export interface CreativeCapabilitySettingsUpdate {
  enabled?: boolean;
  provider?: string;
  api_key?: string;
  api_base?: string | null;
  model?: string;
  extra_headers?: Record<string, string> | null;
}

export interface AgentSettingsUpdate {
  workspace?: string;
  model?: string;
  provider?: string;
  max_tokens?: number;
  context_window_tokens?: number;
  temperature?: number;
  max_tool_iterations?: number;
  reasoning_effort?: string | null;
}

export interface ToolsSettingsUpdate {
  web?: {
    proxy?: string | null;
    search?: {
      provider?: string;
      api_key?: string;
      base_url?: string | null;
      max_results?: number;
    };
  };
  exec?: {
    timeout?: number;
    path_append?: string;
    confirm_high_risk?: boolean;
    approval_timeout_s?: number;
  };
  uploads?: {
    max_file_mb?: number;
    max_total_mb?: number;
    retention_days?: number;
    cleanup_interval_hours?: number;
  };
  knowledge?: {
    vector_backend?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    top_k?: number;
    embedding_model?: string;
    embedding_api_key?: string;
    embedding_api_base?: string | null;
    rerank_model?: string;
    rerank_api_key?: string;
    rerank_api_base?: string | null;
    rerank_top_n?: number;
    vlm_model?: string;
    vlm_api_key?: string;
    vlm_api_base?: string | null;
    vlm_timeout?: number;
    vlm_max_dim?: number;
    vlm_max_workers?: number;
  };
  audit_enabled?: boolean;
  restrict_to_workspace?: boolean;
}

export interface RuntimeSettingsUpdate {
  channels?: {
    send_progress?: boolean;
    send_tool_hints?: boolean;
  };
  gateway?: {
    host?: string;
    port?: number;
    auth_secret?: string;
  };
}

export interface McpServerSettingsUpdate {
  enabled?: boolean;
  notes?: string;
  icon?: string;
  type?: 'stdio' | 'sse' | 'streamableHttp' | null;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  tool_timeout?: number;
  enabled_tools?: string[];
}

export type ChannelName = 'feishu' | 'dingtalk' | 'wecom' | 'qq' | 'mochat';

export interface ChannelCatalogEntry {
  name: ChannelName;
  label: string;
  description: string;
  fields: string[];
  required: string[];
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface ChannelCatalogResponse {
  channels: ChannelCatalogEntry[];
}

export interface ChannelConfigUpdate {
  enabled?: boolean;
  [key: string]: unknown;
}
