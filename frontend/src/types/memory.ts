export interface MemoryContextItem {
  role: string;
  content: string;
  timestamp?: string | null;
}

export interface MemoryArchiveItem {
  id: string;
  content: string;
  timestamp?: string | null;
}

export interface LongTermMemoryState {
  content: string;
  updated_at: string | null;
  character_count: number;
  editable: boolean;
}

export interface CurrentContextState {
  session_id: string | null;
  session_label: string | null;
  items: MemoryContextItem[];
}

export interface ArchivePreviewState {
  query: string;
  total: number;
  items: MemoryArchiveItem[];
}

export interface MemorySettingsState {
  auto_consolidation: boolean;
  template_enabled: boolean;
  editable_long_term: boolean;
  summary: string;
}

export interface MemoryOverviewResponse {
  long_term: LongTermMemoryState;
  current_context: CurrentContextState;
  archive: ArchivePreviewState;
  settings: MemorySettingsState;
}
