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
  };
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
