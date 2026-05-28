export interface BrowserInstallStep {
  key: string;
  title: string;
  detail: string;
  command?: string | null;
  url?: string | null;
}

export interface BrowserProfile {
  context_id: string;
  alias?: string | null;
  is_default: boolean;
}

export interface BrowserStatusResponse {
  ready: boolean;
  opencli: {
    installed: boolean;
    version: string | null;
    path: string | null;
  };
  node: {
    installed: boolean;
    version: string | null;
    ok: boolean;
    required_major: number;
  };
  daemon: {
    port: number;
    running: boolean;
  };
  profiles: BrowserProfile[];
  missing_steps: BrowserInstallStep[];
  last_error: string | null;
}

export interface BrowserSiteCommand {
  name: string;
  description?: string | null;
}

export interface BrowserSite {
  site: string;
  commands: BrowserSiteCommand[];
  featured: boolean;
}

export interface BrowserSiteListResponse {
  items: BrowserSite[];
  featured_count: number;
}

export interface BrowserProfileListResponse {
  items: BrowserProfile[];
}

export type BrowserRunMode = 'site' | 'primitive';

export interface BrowserRunRequest {
  mode: BrowserRunMode;
  site?: string;
  command?: string;
  args?: Record<string, unknown>;
  session?: string;
  action?: string;
  options?: Record<string, unknown>;
  profile?: string;
  timeout_s?: number;
}

export interface BrowserRunResponse {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  command: string[];
}

export interface BrowserInstallResponse {
  success: boolean;
  message: string;
  version: string;
  status: BrowserStatusResponse;
}

export interface BrowserRegistryEntry {
  id: string;
  name: string;
  url: string;
  hostname: string;
  logged_in: boolean;
  is_preset: boolean;
  adapter: string | null;
  updated_at: number;
}

export interface BrowserRegistryListResponse {
  items: BrowserRegistryEntry[];
}

export interface BrowserRegistryAddRequest {
  name: string;
  url: string;
  adapter?: string | null;
}

export interface BrowserRegistryUpdateRequest {
  name?: string;
  url?: string;
  logged_in?: boolean;
}
