export interface Attachment {
  name: string;
  path: string;
  mime_type?: string;
  size?: number;
  category?: string;
  is_image?: boolean;
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
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: Message[];
  timeline_events: Array<{
    id: string;
    type: 'progress' | 'tool_start' | 'tool_end' | 'tool_error';
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

export interface StatusResponse {
  status: string;
  version: string;
  active_connections: number;
  channels: string[];
}

export type WSMessageType =
  | { type: 'connected'; session_id: string }
  | { type: 'message'; content: string; session_id: string; attachments?: Attachment[] }
  | { type: 'response'; content: string; channel: string; citations?: MessageCitation[] }
  | { type: 'response_start'; channel: string }
  | { type: 'response_delta'; content: string; channel: string }
  | { type: 'response_end'; content: string; channel: string; citations?: MessageCitation[] }
  | { type: 'tool'; content: string; channel: string }
  | { type: 'tool_start'; content: string; tool_id: string; tool_name: string; channel: string }
  | { type: 'tool_end'; content: string; tool_id: string; tool_name: string; duration: number; channel: string }
  | { type: 'tool_error'; content: string; tool_id: string; tool_name: string; detail?: string; channel: string }
  | { type: 'progress'; content: string }
  | { type: 'approval_required'; approval_id: string; tool_id: string; tool_name: string; command: string; risk_reason: string; working_dir: string; timeout_s?: number; channel: string }
  | { type: 'error'; content: string }
  | { type: 'pong' };
