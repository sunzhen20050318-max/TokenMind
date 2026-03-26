export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp?: string;
  isStreaming?: boolean;
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
    type: 'progress' | 'tool_start' | 'tool_end';
    content: string;
    timestamp: string;
    turnId: string;
    toolId?: string;
    toolName?: string;
    duration?: number;
  }>;
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
  | { type: 'response_start'; channel: string }
  | { type: 'response_delta'; content: string; channel: string }
  | { type: 'response_end'; content: string; channel: string }
  | { type: 'tool'; content: string; channel: string }
  | { type: 'tool_start'; content: string; tool_id: string; tool_name: string; channel: string }
  | { type: 'tool_end'; content: string; tool_id: string; tool_name: string; duration: number; channel: string }
  | { type: 'progress'; content: string }
  | { type: 'error'; content: string }
  | { type: 'pong' };
