export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

export interface Session {
  session_id: string;
  updated_at?: string;
  created_at?: string;
  message_count: number;
  first_message?: string;
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: Message[];
}

export interface SendMessageResponse {
  response: string;
  session_id: string;
  tools_used: string[];
}

export interface StatusResponse {
  status: string;
  version: string;
  active_connections: number;
  channels: string[];
}

export type WSMessageType =
  | { type: 'connected'; session_id: string }
  | { type: 'message'; content: string; session_id: string }
  | { type: 'response'; content: string; channel: string }
  | { type: 'tool'; content: string; channel: string }
  | { type: 'tool_start'; content: string; tool_id: string; tool_name: string; channel: string }
  | { type: 'tool_end'; content: string; tool_id: string; tool_name: string; duration: number; channel: string }
  | { type: 'progress'; content: string }
  | { type: 'error'; content: string }
  | { type: 'pong' };
