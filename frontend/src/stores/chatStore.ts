import { create } from 'zustand';
import type { Message, MessageCitation, Session } from '../types';
import { api } from '../services/api';
import type { KnowledgeBase } from '../types/knowledge';

export interface ToolCall {
  id: string;
  tool: string;
  status: 'running' | 'completed' | 'error';
  duration?: number;
  timestamp: string;
  turnId: string; // Associates this tool call with a specific user message timestamp
}

export interface TimelineEvent {
  id: string;
  type: 'progress' | 'tool_start' | 'tool_end' | 'tool_error';
  content: string;
  timestamp: string;
  turnId: string;
  toolId?: string;
  toolName?: string;
  duration?: number;
  detail?: string;
}

export interface ModelProvider {
  id: string;
  name: string;
  enabled: boolean;
  configured: boolean; // whether api_key/api_base is set
  apiKeyMasked: string;
  apiBase: string;
  defaultModel: string;
}

interface ChatState {
  currentSession: string | null;
  messages: Message[];
  sessions: Session[];
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
  activeTool: string | null;
  currentTurnId: string | null; // The turnId for the current conversation turn
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  modelProviders: ModelProvider[];
  activeModelId: string | null;
  modelProvidersStatus: 'idle' | 'loading' | 'ready' | 'error';
  availableKnowledgeBases: KnowledgeBase[];
  linkedKnowledgeBaseIds: string[];

  // Actions
  setCurrentSession: (sessionId: string) => void;
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  setLoading: (loading: boolean) => void;
  setConnected: (connected: boolean) => void;
  setError: (error: string | null) => void;
  setActiveTool: (tool: string | null) => void;
  addToolCall: (tool: string, toolId?: string) => string;
  completeToolCall: (id: string, duration: number) => void;
  failToolCall: (id: string) => void;
  completeAllRunningTools: (duration: number) => void;
  clearToolCalls: () => void;
  clearOldToolCalls: () => void;
  addTimelineEvent: (event: Omit<TimelineEvent, 'id' | 'timestamp' | 'turnId'>) => void;
  clearOldTimelineEvents: () => void;
  setCurrentTurnId: (turnId: string | null) => void;
  loadSessions: () => Promise<void>;
  loadHistory: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string | null) => Promise<void>;
  startStreamingAssistant: () => void;
  appendStreamingAssistant: (chunk: string) => void;
  finishStreamingAssistant: (content?: string, citations?: MessageCitation[]) => void;
  fetchModelProviders: () => Promise<void>;
  setActiveModel: (providerId: string, model?: string) => Promise<void>;
  updateProviderConfig: (providerId: string, config: { apiKey: string; apiBase: string }) => Promise<void>;
  loadKnowledgeBases: () => Promise<void>;
  loadLinkedKnowledgeBases: (sessionId: string) => Promise<void>;
  setLinkedKnowledgeBases: (knowledgeBaseIds: string[]) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSession: null,
  messages: [],
  sessions: [],
  isLoading: false,
  isConnected: false,
  error: null,
  activeTool: null,
  toolCalls: [],
  timelineEvents: [],
  currentTurnId: null,
  modelProviders: [],
  activeModelId: null,
  modelProvidersStatus: 'idle',
  availableKnowledgeBases: [],
  linkedKnowledgeBaseIds: [],

  setCurrentTurnId: (turnId) => {
    set({ currentTurnId: turnId });
  },

  setCurrentSession: (sessionId) => {
    // Add to sessions list if not exists
    const { sessions } = get();
    if (!sessions.find(s => s.session_id === sessionId)) {
      const newSession: Session = {
        session_id: sessionId,
        message_count: 0,
      };
      set({ sessions: [newSession, ...sessions] });
    }
    set({
      currentSession: sessionId,
      messages: [],
      error: null,
      activeTool: null,
      toolCalls: [],
      timelineEvents: [],
      currentTurnId: null,
      linkedKnowledgeBaseIds: [],
    });
    get().loadHistory(sessionId);
  },

  addMessage: (message) => {
    set((state) => {
      // Update message count for current session
      const updatedSessions = state.sessions.map(s =>
        s.session_id === state.currentSession
          ? { ...s, message_count: s.message_count + 1 }
          : s
      );
      return {
        messages: [...state.messages, message],
        sessions: updatedSessions,
      };
    });
  },

  clearMessages: () => {
    set((state) => ({
      messages: [],
      sessions: state.sessions.map(s =>
        s.session_id === state.currentSession
          ? { ...s, message_count: 0 }
          : s
      ),
    }));
  },

  setSessions: (sessions) => {
    set({ sessions });
  },

  addSession: (session) => {
    set((state) => ({
      sessions: [session, ...state.sessions],
    }));
  },

  setLoading: (isLoading) => {
    set({ isLoading });
  },

  setConnected: (isConnected) => {
    set({ isConnected });
  },

  setError: (error) => {
    set({ error });
  },

  setActiveTool: (activeTool) => {
    set({ activeTool });
  },

  addToolCall: (tool, toolId) => {
    // Use provided toolId if available, otherwise generate one
    const id = toolId || `tool-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const state = get();
    const currentTurnId = state.currentTurnId;

    // Only check for duplicates within the current turn
    if (currentTurnId) {
      // Check if this tool with this exact ID is already running in current turn
      if (state.toolCalls.some(tc => tc.id === id && tc.status === 'running' && tc.turnId === currentTurnId)) {
        return id;
      }
      // Also check if this tool name is already running in current turn (dedup by name)
      if (state.toolCalls.some(tc => tc.tool === tool && tc.status === 'running' && tc.turnId === currentTurnId)) {
        return state.toolCalls.find(tc => tc.tool === tool && tc.status === 'running' && tc.turnId === currentTurnId)?.id || '';
      }
    }

    const newCall: ToolCall = {
      id,
      tool,
      status: 'running',
      timestamp: new Date().toISOString(),
      turnId: currentTurnId || '',
    };
    set((state) => ({ toolCalls: [...state.toolCalls, newCall] }));
    return id;
  },

  completeToolCall: (id, duration) => {
    set((state) => ({
      toolCalls: state.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, status: 'completed' as const, duration } : tc
      ),
    }));
  },

  failToolCall: (id) => {
    set((state) => ({
      toolCalls: state.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, status: 'error' as const } : tc
      ),
    }));
  },

  completeAllRunningTools: (duration) => {
    // Only complete tools for the current turn
    set((state) => ({
      toolCalls: state.toolCalls.map((tc) =>
        tc.status === 'running' && tc.turnId === state.currentTurnId
          ? { ...tc, status: 'completed' as const, duration }
          : tc
      ),
    }));
  },

  clearToolCalls: () => {
    set({ toolCalls: [] });
  },

  // Clear only tool calls from previous turns (not the current one)
  clearOldToolCalls: () => {
    const state = get();
    set({
      toolCalls: state.toolCalls.filter(tc => tc.turnId === state.currentTurnId || tc.turnId === '')
    });
  },

  addTimelineEvent: (event) => {
    const turnId = get().currentTurnId || '';
    const newEvent: TimelineEvent = {
      id: `timeline-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      turnId,
      ...event,
    };
    set((state) => ({ timelineEvents: [...state.timelineEvents, newEvent] }));
  },

  clearOldTimelineEvents: () => {
    const state = get();
    set({
      timelineEvents: state.timelineEvents.filter(
        (evt) => evt.turnId === state.currentTurnId || evt.turnId === ''
      ),
    });
  },

  loadSessions: async () => {
    try {
      const { sessions } = await api.listSessions();
      set({ sessions });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load sessions' });
    }
  },

  loadHistory: async (sessionId) => {
    try {
      set({ isLoading: true });
      const { messages, timeline_events } = await api.getHistory(sessionId);
      set({
        messages,
        timelineEvents: timeline_events || [],
        toolCalls: [],
        currentTurnId: null,
        isLoading: false,
      });
    } catch (e) {
      // Session might not exist yet, that's ok
      set({ messages: [], timelineEvents: [], toolCalls: [], isLoading: false });
    }
  },

  deleteSession: async (sessionId) => {
    try {
      await api.deleteSession(sessionId);
      set((state) => ({
        sessions: state.sessions.filter((s) => s.session_id !== sessionId),
        currentSession: state.currentSession === sessionId ? null : state.currentSession,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete session' });
    }
  },

  renameSession: async (sessionId, title) => {
    try {
      const result = await api.renameSession(sessionId, title);
      set((state) => ({
        sessions: state.sessions.map((session) =>
          session.session_id === sessionId
            ? { ...session, title: result.title || undefined }
            : session
        ),
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to rename session' });
    }
  },

  startStreamingAssistant: () => {
    set((state) => ({
      messages: [
        ...state.messages,
        {
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          isStreaming: true,
        },
      ],
    }));
  },

  appendStreamingAssistant: (chunk) => {
    set((state) => {
      const messages = [...state.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant' && messages[i].isStreaming) {
          messages[i] = {
            ...messages[i],
            content: `${messages[i].content}${chunk}`,
          };
          return { messages };
        }
      }
      return {
        messages: [
          ...state.messages,
          {
            role: 'assistant',
            content: chunk,
            timestamp: new Date().toISOString(),
            isStreaming: true,
          },
        ],
      };
    });
  },

  finishStreamingAssistant: (content, citations) => {
    set((state) => {
      const messages = [...state.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant' && messages[i].isStreaming) {
          messages[i] = {
            ...messages[i],
            content: content ?? messages[i].content,
            isStreaming: false,
            citations: citations ?? messages[i].citations,
          };
          return { messages };
        }
      }
      if (content) {
        return {
          messages: [
            ...state.messages,
            {
              role: 'assistant',
              content,
              timestamp: new Date().toISOString(),
              isStreaming: false,
              citations,
            },
          ],
        };
      }
      return state;
    });
  },

  fetchModelProviders: async () => {
    try {
      set({ modelProvidersStatus: 'loading' });
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const providers = data.providers || {};
      const defaultProvider = data.defaults?.provider;

      const PROVIDER_NAMES: Record<string, string> = {
        deepseek: 'Deepseek',
        openrouter: 'OpenRouter',
        anthropic: 'Anthropic',
        openai: 'OpenAI',
        gemini: 'Gemini',
        zhipu: 'Zhipu',
        dashscope: 'DashScope',
        moonshot: 'Moonshot',
        minimax: 'MiniMax',
        ollama: 'Ollama',
        vllm: 'vLLM',
        groq: 'Groq',
        github_copilot: 'GitHub Copilot',
        openai_codex: 'OpenAI Codex',
        azure_openai: 'Azure OpenAI',
        custom: 'Custom',
        aihubmix: 'AiHubMix',
        siliconflow: 'SiliconFlow',
        volcengine: 'VolcEngine',
        byteplus: 'BytePlus',
      };

      // Show ALL providers from registry, mark configured ones
      const ALL_PROVIDER_IDS = Object.keys(PROVIDER_NAMES);
      const modelProviders: ModelProvider[] = ALL_PROVIDER_IDS.map((id) => {
        const p = (providers as Record<string, any>)[id];
        const isConfigured = p && (p.api_key !== '****' && p.api_key !== '' || p.api_base);
        return {
          id,
          name: PROVIDER_NAMES[id],
          enabled: id === defaultProvider,
          configured: !!isConfigured,
          apiKeyMasked: p?.api_key || '',
          apiBase: p?.api_base || '',
          defaultModel: p?.default_model || '',
        };
      });

      set({
        modelProviders,
        activeModelId: defaultProvider || null,
        modelProvidersStatus: 'ready',
      });
    } catch (e) {
      console.error('fetchModelProviders failed:', e);
      set({ modelProvidersStatus: 'error' });
    }
  },

  setActiveModel: async (providerId, model) => {
    try {
      const body: Record<string, string> = { provider: providerId };
      if (model) body.model = model;
      await fetch('/api/config/defaults', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      set((state) => ({
        activeModelId: providerId,
        modelProviders: state.modelProviders.map((p) => ({
          ...p,
          enabled: p.id === providerId,
        })),
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to set active model' });
    }
  },

  updateProviderConfig: async (providerId, config) => {
    try {
      await fetch(`/api/config/providers/${providerId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: config.apiKey || undefined,
          api_base: config.apiBase || undefined,
        }),
      });
      set((state) => ({
        modelProviders: state.modelProviders.map((p) =>
          p.id === providerId
            ? {
                ...p,
                configured: true,
                apiKeyMasked: config.apiKey ? '********' : p.apiKeyMasked,
                apiBase: config.apiBase || p.apiBase,
              }
            : p
        ),
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to update provider config' });
    }
  },

  loadKnowledgeBases: async () => {
    try {
      const payload = await api.getKnowledgeOverview();
      set({ availableKnowledgeBases: payload.items });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load knowledge bases' });
    }
  },

  loadLinkedKnowledgeBases: async (sessionId) => {
    try {
      const payload = await api.getSessionKnowledgeLinks(sessionId);
      set({ linkedKnowledgeBaseIds: payload.knowledge_base_ids });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load linked knowledge bases' });
    }
  },

  setLinkedKnowledgeBases: async (knowledgeBaseIds) => {
    const sessionId = get().currentSession;
    if (!sessionId) {
      return;
    }
    try {
      await api.updateSessionKnowledgeLinks(sessionId, knowledgeBaseIds);
      set({ linkedKnowledgeBaseIds: knowledgeBaseIds });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to update linked knowledge bases' });
    }
  },
}));
