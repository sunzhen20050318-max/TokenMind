export type BrowserTaskStatus =
  | 'pending'
  | 'running'
  | 'awaiting_user'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type BrowserStepPhase = 'thinking' | 'action' | 'observation' | 'intervention';

export type BrowserArtifactKind =
  | 'screenshot'
  | 'page_text'
  | 'download'
  | 'pdf'
  | 'extract_json'
  | 'log';

export interface BrowserTask {
  id: string;
  project_id: string;
  session_id?: string | null;
  instruction: string;
  start_url?: string | null;
  status: BrowserTaskStatus;
  result_summary?: string | null;
  error_detail?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  step_count: number;
  max_steps: number;
  timeout_seconds: number;
  metadata: Record<string, unknown>;
}

export interface BrowserStep {
  id: string;
  task_id: string;
  step_index: number;
  phase: BrowserStepPhase;
  action_name?: string | null;
  action_args?: Record<string, unknown> | null;
  thinking?: string | null;
  observation?: string | null;
  screenshot_artifact_id?: string | null;
  success: boolean;
  error?: string | null;
  duration_ms?: number | null;
  timestamp: string;
}

export interface BrowserArtifact {
  id: string;
  task_id: string;
  step_index?: number | null;
  kind: BrowserArtifactKind;
  file_path: string;
  source_url?: string | null;
  mime_type?: string | null;
  size_bytes: number;
  created_at: string;
  knowledge_doc_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface BrowserTaskListItem {
  id: string;
  project_id: string;
  session_id?: string | null;
  instruction: string;
  status: BrowserTaskStatus;
  created_at: string;
  finished_at: string | null;
  step_count: number;
  artifact_count: number;
}

export interface BrowserTaskListResponse {
  items: BrowserTaskListItem[];
}

export interface BrowserTaskDetailResponse {
  task: BrowserTask;
  steps: BrowserStep[];
  artifacts: BrowserArtifact[];
}

export interface CreateBrowserTaskRequest {
  project_id: string;
  instruction: string;
  start_url?: string;
  session_id?: string;
  max_steps?: number;
  timeout_seconds?: number;
}

export interface BrowserAgentEnvCheck {
  cli_installed: boolean;
  chrome_installed: boolean;
  is_ready: boolean;
  version: string | null;
  issues: string[];
}

// ── WebSocket stream events ────────────────────────────────────────────────

export interface BrowserStreamStepEvent {
  type: 'step';
  step: BrowserStep;
}

export interface BrowserStreamArtifactEvent {
  type: 'artifact';
  artifact: BrowserArtifact;
}

export interface BrowserStreamStatusEvent {
  type: 'status';
  status: BrowserTaskStatus;
  error?: string;
  result_summary?: string;
}

export type BrowserStreamEvent =
  | BrowserStreamStepEvent
  | BrowserStreamArtifactEvent
  | BrowserStreamStatusEvent;
