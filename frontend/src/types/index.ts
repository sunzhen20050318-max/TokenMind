export interface Attachment {
  id?: string;
  name: string;
  path?: string;
  mime_type?: string;
  size?: number;
  category?: string;
  is_image?: boolean;
  origin?: 'user_upload' | 'assistant_local' | 'assistant_remote' | 'assistant_generated';
  status?: 'temporary' | 'saved' | 'expired';
  preview_text?: string;
}

export interface MessageCitation {
  id?: string;
  knowledge_base_id?: string;
  knowledge_base_name: string;
  document_id?: string;
  document_name: string;
  excerpt: string;
  score?: number;
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string | Array<{ type?: string; text?: string; [key: string]: unknown }>;
  timestamp?: string;
  isStreaming?: boolean;
  attachments?: Attachment[];
  citations?: MessageCitation[];
  tool_call_id?: string;
  name?: string;
  /** True for user messages sent via the "guidance" path while the agent
   *  was busy. Rendered as a distinct bubble in the chat. */
  is_guidance?: boolean;
  tool_calls?: Array<{
    id?: string;
    name?: string;
    function?: {
      name?: string;
      arguments?: string;
    };
  }>;
}

export interface Session {
  session_id: string;
  updated_at?: string;
  created_at?: string;
  message_count: number;
  first_message?: string;
  title?: string;
  project_id?: string;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  session_count: number;
}

export interface ProjectDetailResponse {
  project: Project;
  sessions: Session[];
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: Message[];
  timeline_events: Array<{
    id: string;
    type: 'progress' | 'tool_start' | 'tool_end' | 'tool_error' | 'reasoning';
    content: string;
    timestamp: string;
    turnId: string;
    toolId?: string;
    toolName?: string;
    duration?: number;
    detail?: string;
  }>;
}

export interface SendMessageResponse {
  response: string;
  session_id: string;
  tools_used: string[];
}

export interface UploadFilesResponse {
  session_id: string;
  attachments: Attachment[];
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface MusicGenerateRequest {
  prompt: string;
  lyrics?: string | null;
  lyrics_optimizer?: boolean;
  is_instrumental?: boolean;
  count?: number;
  reference_audio_base64?: string | null;
  reference_audio_name?: string | null;
}

export interface MusicGenerateResult {
  filename: string;
  mime_type: string;
  model: string;
  provider: string;
  duration_ms?: number | null;
  trace_id?: string | null;
  reference_audio_name?: string | null;
}

export interface MusicGenerateResponse {
  attachment: Attachment;
  result: MusicGenerateResult;
  attachments?: Attachment[];
  results?: MusicGenerateResult[];
}

export interface VoiceCloneUploadResponse {
  file_id: number;
  filename: string;
  bytes: number;
  created_at?: number | null;
}

export interface VoiceCloneCreateRequest {
  file_id: number;
  voice_id?: string | null;
  preview_text?: string | null;
  need_noise_reduction?: boolean;
  need_volume_normalization?: boolean;
  language_boost?: string | null;
  source_filename?: string | null;
}

export interface VoiceCloneRecord {
  voice_id: string;
  model: string;
  provider: string;
  created_at: string;
  preview_text?: string | null;
  source_filename?: string | null;
  demo_audio_url?: string | null;
  demo_attachment_id?: string | null;
  last_kept_alive_at?: string | null;
  notes?: string | null;
  source?: string;
  display_name?: string | null;
}

export interface VoiceDesignCreateRequest {
  prompt: string;
  preview_text: string;
  voice_id?: string | null;
  display_name?: string | null;
}

export interface VoiceDesignCreateResponse extends VoiceCloneRecord {
  trace_id?: string | null;
}

export interface SkillSummary {
  name: string;
  description: string;
  source: 'workspace' | 'builtin';
  path: string;
  enabled: boolean;
  available: boolean;
  missing_requirements?: string | null;
  always?: boolean;
  emoji?: string | null;
}

export interface SkillSuggestion {
  id: string;
  kind: 'create' | 'update';
  name: string;
  description: string;
  body: string;
  markdown?: string | null;
  target_skill?: string | null;
  previous_markdown?: string | null;
  triggers: string[];
  source_session_id?: string | null;
  source_message?: string | null;
  created_at: string;
  path?: string | null;
  preview_markdown: string;
  diff_markdown?: string;
}

export interface SkillListResponse {
  items: SkillSummary[];
}

export interface SkillSuggestionListResponse {
  items: SkillSuggestion[];
}

export interface VoiceCloneCreateResponse extends VoiceCloneRecord {
  input_sensitive?: boolean;
  input_sensitive_type?: number | null;
  trace_id?: string | null;
}

export interface VoiceCloneListResponse {
  items: VoiceCloneRecord[];
}

export interface TtsSynthesizeRequest {
  text: string;
  voice_id: string;
  model?: string | null;
  speed?: number;
  volume?: number;
  pitch?: number;
  emotion?: string | null;
}

export interface TtsSynthesizeResponse {
  voice_id: string;
  model: string;
  provider: string;
  filename: string;
  mime_type: string;
  usage_characters?: number | null;
  trace_id?: string | null;
  attachment_id: string;
  attachment: Attachment;
}

export interface TtsVoiceOption {
  kind: 'cloned' | 'system';
  voice_id: string;
  label: string;
  gender?: string | null;
  description?: string | null;
  created_at?: string | null;
  model?: string | null;
  provider?: string | null;
  last_kept_alive_at?: string | null;
  demo_attachment_id?: string | null;
  demo_audio_url?: string | null;
  source_filename?: string | null;
  source?: string | null; // "clone" | "design" | ...
  display_name?: string | null;
}

export interface TtsVoiceListResponse {
  cloned: TtsVoiceOption[];
  system: TtsVoiceOption[];
}

export interface PendingToolApproval {
  approval_id: string;
  tool_id: string;
  tool_name: string;
  command: string;
  risk_reason: string;
  working_dir: string;
  timeout_s?: number;
  received_at_ms?: number;
}

export interface UserQuestionOption {
  label: string;
  description?: string;
}

export interface UserQuestionItem {
  question: string;
  header: string;
  multiSelect?: boolean;
  options: UserQuestionOption[];
}

export interface PendingUserQuestion {
  question_id: string;
  tool_id: string;
  questions: UserQuestionItem[];
  received_at_ms?: number;
}

export interface UserQuestionAnswer {
  selected: string | string[];
  notes?: string;
}

export interface StatusResponse {
  status: string;
  version: string;
  active_connections: number;
  channels: string[];
}

export type WSMessageType =
  | { type: 'connected'; session_id: string }
  | { type: 'message'; content: string; session_id: string; attachments?: Attachment[] }
  | { type: 'response'; content: string; channel: string; citations?: MessageCitation[]; attachments?: Attachment[] }
  | { type: 'response_start'; channel: string }
  | { type: 'response_delta'; content: string; channel: string }
  | { type: 'response_end'; content: string; channel: string; citations?: MessageCitation[]; attachments?: Attachment[] }
  | { type: 'tool'; content: string; channel: string }
  | { type: 'tool_start'; content: string; tool_id: string; tool_name: string; channel: string }
  | { type: 'tool_end'; content: string; tool_id: string; tool_name: string; duration: number; channel: string }
  | { type: 'tool_error'; content: string; tool_id: string; tool_name: string; detail?: string; channel: string }
  | { type: 'progress'; content: string }
  | { type: 'reasoning'; content: string; channel: string }
  | { type: 'file_edit_progress'; event: import('../stores/chatStore').FileEditEvent; channel: string }
  | { type: 'guidance_received'; content: string; channel: string }
  | { type: 'session_title_updated'; session_id: string; title: string; channel: string }
  | { type: 'approval_required'; approval_id: string; tool_id: string; tool_name: string; command: string; risk_reason: string; working_dir: string; timeout_s?: number; channel: string }
  | { type: 'user_question_required'; question_id: string; tool_id: string; questions: UserQuestionItem[]; channel: string }
  | { type: 'error'; content: string }
  | { type: 'pong' };
