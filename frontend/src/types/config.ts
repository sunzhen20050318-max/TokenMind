export interface ProviderSettings {
  api_key: string;
  api_base: string | null;
  extra_headers: Record<string, string> | null;
  default_model: string | null;
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
}

export interface McpServerSettings {
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
    heartbeat: {
      enabled: boolean;
      interval_s: number;
    };
  };
}

export interface AppConfigResponse {
  providers: Record<string, ProviderSettings>;
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
    heartbeat?: {
      enabled?: boolean;
      interval_s?: number;
    };
  };
}

export interface McpServerSettingsUpdate {
  type?: 'stdio' | 'sse' | 'streamableHttp' | null;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  tool_timeout?: number;
  enabled_tools?: string[];
}
