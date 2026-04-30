import { create } from 'zustand';
import type {
  Attachment,
  Message,
  MessageCitation,
  PendingToolApproval,
  Project,
  Session,
} from '../types';
import { api } from '../services/api';
import type { CreativeSettings } from '../types/config';
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

/**
 * Snapshot of "transient per-session" state. The foreground session keeps
 * a mirror in the top-level fields (for compat with existing components);
 * background sessions store theirs here so navigation away from chat does
 * not drop in-flight work.
 */
export interface SessionSlice {
  messages: Message[];
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  activeTool: string | null;
  isLoading: boolean;
  currentTurnId: string | null;
  linkedKnowledgeBaseIds: string[];
  pendingApproval: PendingToolApproval | null;
  sessionExecTrusted: boolean;
}

const EMPTY_SLICE: SessionSlice = {
  messages: [],
  toolCalls: [],
  timelineEvents: [],
  activeTool: null,
  isLoading: false,
  currentTurnId: null,
  linkedKnowledgeBaseIds: [],
  pendingApproval: null,
  sessionExecTrusted: false,
};

interface ChatState {
  currentSession: string | null;
  messages: Message[];
  sessions: Session[];
  projects: Project[];
  activeProjectId: string | null;
  activeProject: Project | null;
  projectSessions: Session[];
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
  activeTool: string | null;
  currentTurnId: string | null; // The turnId for the current conversation turn
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  pendingApproval: PendingToolApproval | null;
  sessionExecTrusted: boolean;
  sessionsState: Record<string, SessionSlice>;
  modelProviders: ModelProvider[];
  activeModelId: string | null;
  modelProvidersStatus: 'idle' | 'loading' | 'ready' | 'error';
  creativeCapabilities: CreativeSettings | null;
  availableKnowledgeBases: KnowledgeBase[];
  linkedKnowledgeBaseIds: string[];
  pendingSessionStarter: { sessionId: string; message: string } | null;
  previewAttachment: Attachment | null;

  // Actions
  setCurrentSession: (sessionId: string) => void;
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setSessions: (sessions: Session[]) => void;
  setProjectSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  loadProjects: () => Promise<void>;
  openProject: (projectId: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  leaveProject: () => void;
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
  deleteSessionMessage: (sessionId: string, timestamp: string) => Promise<void>;
  renameSession: (sessionId: string, title: string | null) => Promise<void>;
  startStreamingAssistant: () => void;
  appendStreamingAssistant: (chunk: string) => void;
  finishStreamingAssistant: (content?: string, citations?: MessageCitation[], attachments?: Message['attachments']) => void;
  updateAttachment: (attachmentId: string, nextAttachment: NonNullable<Message['attachments']>[number]) => void;
  fetchModelProviders: () => Promise<void>;
  setActiveModel: (providerId: string, model?: string) => Promise<void>;
  updateProviderConfig: (providerId: string, config: { apiKey: string; apiBase: string }) => Promise<void>;
  loadCreativeCapabilities: () => Promise<void>;
  setCreativeCapabilities: (creative: CreativeSettings) => void;
  loadKnowledgeBases: () => Promise<void>;
  loadLinkedKnowledgeBases: (sessionId: string) => Promise<void>;
  setLinkedKnowledgeBases: (knowledgeBaseIds: string[]) => Promise<void>;
  queuePendingSessionStarter: (sessionId: string, message: string) => void;
  clearPendingSessionStarter: (sessionId?: string) => void;
  openAttachmentPreview: (attachment: Attachment) => void;
  closeAttachmentPreview: () => void;

  // ── Per-session mutators (used by WebSocket pool for any session) ──
  /** Returns true if the session is the current foreground session. */
  isCurrentSession: (sessionId: string) => boolean;
  /** Read-only snapshot of a session's slice (foreground or background). */
  getSessionSlice: (sessionId: string) => SessionSlice;
  ensureSessionSlice: (sessionId: string) => void;

  setSessionLoading: (sessionId: string, loading: boolean) => void;
  setSessionActiveTool: (sessionId: string, tool: string | null) => void;
  setSessionCurrentTurnId: (sessionId: string, turnId: string | null) => void;

  startSessionStreamingAssistant: (sessionId: string) => void;
  appendSessionStreamingAssistant: (sessionId: string, chunk: string) => void;
  finishSessionStreamingAssistant: (
    sessionId: string,
    content?: string,
    citations?: MessageCitation[],
    attachments?: Message['attachments'],
  ) => void;

  addSessionToolCall: (sessionId: string, tool: string, toolId?: string) => string;
  completeSessionToolCall: (sessionId: string, id: string, duration: number) => void;
  failSessionToolCall: (sessionId: string, id: string) => void;
  completeAllSessionRunningTools: (sessionId: string, duration: number) => void;
  addSessionTimelineEvent: (
    sessionId: string,
    event: Omit<TimelineEvent, 'id' | 'timestamp' | 'turnId'>,
  ) => void;

  setSessionPendingApproval: (sessionId: string, approval: PendingToolApproval | null) => void;
  setSessionExecTrusted: (sessionId: string, trusted: boolean) => void;
  setSessionError: (sessionId: string, error: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSession: null,
  messages: [],
  sessions: [],
  projects: [],
  activeProjectId: null,
  activeProject: null,
  projectSessions: [],
  isLoading: false,
  isConnected: false,
  error: null,
  activeTool: null,
  toolCalls: [],
  timelineEvents: [],
  currentTurnId: null,
  pendingApproval: null,
  sessionExecTrusted: false,
  sessionsState: {},
  modelProviders: [],
  activeModelId: null,
  modelProvidersStatus: 'idle',
  creativeCapabilities: null,
  availableKnowledgeBases: [],
  linkedKnowledgeBaseIds: [],
  pendingSessionStarter: null,
  previewAttachment: null,

  setCurrentTurnId: (turnId) => {
    set({ currentTurnId: turnId });
  },

  openAttachmentPreview: (attachment) => {
    set({ previewAttachment: attachment });
  },

  closeAttachmentPreview: () => {
    set({ previewAttachment: null });
  },

  queuePendingSessionStarter: (sessionId, message) => {
    set({
      pendingSessionStarter: {
        sessionId,
        message,
      },
    });
  },

  clearPendingSessionStarter: (sessionId) => {
    set((state) => {
      if (!state.pendingSessionStarter) {
        return state;
      }

      if (sessionId && state.pendingSessionStarter.sessionId !== sessionId) {
        return state;
      }

      return { pendingSessionStarter: null };
    });
  },

  setCurrentSession: (sessionId) => {
    const state = get();
    const { sessions, projectSessions, activeProjectId, activeProject, projects } = state;
    const existingGlobal = sessions.find((session) => session.session_id === sessionId);
    const existingProject = projectSessions.find((session) => session.session_id === sessionId);
    const resolvedProjectId = existingProject?.project_id || activeProjectId || null;
    const resolvedProject =
      (resolvedProjectId ? projects.find((project) => project.id === resolvedProjectId) : null) ||
      activeProject;
    const shouldTreatAsProject = !!existingProject || (!!resolvedProjectId && !existingGlobal);

    if (!existingGlobal && !existingProject) {
      const newSession: Session = {
        session_id: sessionId,
        message_count: 0,
        project_id: shouldTreatAsProject ? resolvedProjectId || undefined : undefined,
      };
      if (shouldTreatAsProject) {
        set((current) => ({ projectSessions: [newSession, ...current.projectSessions] }));
      } else {
        set((current) => ({ sessions: [newSession, ...current.sessions] }));
      }
    }

    // Snapshot the previous foreground session into sessionsState so its
    // in-flight task progress survives the navigation away.
    const previousId = state.currentSession;
    const nextSessionsState = { ...state.sessionsState };
    if (previousId && previousId !== sessionId) {
      nextSessionsState[previousId] = {
        messages: state.messages,
        toolCalls: state.toolCalls,
        timelineEvents: state.timelineEvents,
        activeTool: state.activeTool,
        isLoading: state.isLoading,
        currentTurnId: state.currentTurnId,
        linkedKnowledgeBaseIds: state.linkedKnowledgeBaseIds,
        pendingApproval: state.pendingApproval,
        sessionExecTrusted: state.sessionExecTrusted,
      };
    }

    const restored = nextSessionsState[sessionId];
    set({
      currentSession: sessionId,
      sessionsState: nextSessionsState,
      messages: restored?.messages ?? [],
      toolCalls: restored?.toolCalls ?? [],
      timelineEvents: restored?.timelineEvents ?? [],
      activeTool: restored?.activeTool ?? null,
      isLoading: restored?.isLoading ?? false,
      currentTurnId: restored?.currentTurnId ?? null,
      linkedKnowledgeBaseIds: restored?.linkedKnowledgeBaseIds ?? [],
      pendingApproval: restored?.pendingApproval ?? null,
      sessionExecTrusted: restored?.sessionExecTrusted ?? false,
      error: null,
      activeProjectId: shouldTreatAsProject ? resolvedProjectId : null,
      activeProject: shouldTreatAsProject ? resolvedProject : null,
    });

    // Only fetch history when we don't already have a slice in memory — otherwise
    // we'd clobber the live streaming progress accumulated in the background.
    if (!restored) {
      get().loadHistory(sessionId);
    }
  },

  addMessage: (message) => {
    set((state) => {
      const firstMessage =
        message.role === 'user' && typeof message.content === 'string' ? message.content : undefined;
      const updatedSessions = state.sessions.map((session) =>
        session.session_id === state.currentSession
          ? {
              ...session,
              message_count: session.message_count + 1,
              first_message: session.first_message || firstMessage,
            }
          : session
      );
      const updatedProjectSessions = state.projectSessions.map((session) =>
        session.session_id === state.currentSession
          ? {
              ...session,
              message_count: session.message_count + 1,
              first_message: session.first_message || firstMessage,
            }
          : session
      );
      return {
        messages: [...state.messages, message],
        sessions: updatedSessions,
        projectSessions: updatedProjectSessions,
      };
    });
  },

  clearMessages: () => {
    set((state) => ({
      messages: [],
      sessions: state.sessions.map((session) =>
        session.session_id === state.currentSession
          ? { ...session, message_count: 0 }
          : session
      ),
      projectSessions: state.projectSessions.map((session) =>
        session.session_id === state.currentSession
          ? { ...session, message_count: 0 }
          : session
      ),
    }));
  },

  setSessions: (sessions) => {
    set({ sessions });
  },

  setProjectSessions: (projectSessions) => {
    set({ projectSessions });
  },

  addSession: (session) => {
    set((state) => ({
      sessions: [session, ...state.sessions],
    }));
  },

  loadProjects: async () => {
    try {
      const payload = await api.listProjects();
      set((state) => ({
        projects: payload.items,
        activeProject:
          state.activeProjectId != null
            ? payload.items.find((project) => project.id === state.activeProjectId) || state.activeProject
            : null,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load projects' });
    }
  },

  openProject: async (projectId) => {
    try {
      const payload = await api.getProject(projectId);
      set({
        activeProjectId: payload.project.id,
        activeProject: payload.project,
        projectSessions: payload.sessions,
        currentSession: null,
        messages: [],
        toolCalls: [],
        timelineEvents: [],
        currentTurnId: null,
        linkedKnowledgeBaseIds: [],
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to open project' });
    }
  },

  deleteProject: async (projectId) => {
    try {
      await api.deleteProject(projectId);
      set((state) => {
        const deletingActiveProject = state.activeProjectId === projectId;
        return {
          projects: state.projects.filter((project) => project.id !== projectId),
          activeProjectId: deletingActiveProject ? null : state.activeProjectId,
          activeProject: deletingActiveProject ? null : state.activeProject,
          projectSessions: deletingActiveProject ? [] : state.projectSessions,
          currentSession: deletingActiveProject ? null : state.currentSession,
          messages: deletingActiveProject ? [] : state.messages,
          toolCalls: deletingActiveProject ? [] : state.toolCalls,
          timelineEvents: deletingActiveProject ? [] : state.timelineEvents,
          currentTurnId: deletingActiveProject ? null : state.currentTurnId,
          linkedKnowledgeBaseIds: deletingActiveProject ? [] : state.linkedKnowledgeBaseIds,
        };
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete project' });
    }
  },

  leaveProject: () => {
    set({
      activeProjectId: null,
      activeProject: null,
      projectSessions: [],
    });
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
        projectSessions: state.projectSessions.filter((s) => s.session_id !== sessionId),
        currentSession: state.currentSession === sessionId ? null : state.currentSession,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete session' });
    }
  },

  deleteSessionMessage: async (sessionId, timestamp) => {
    try {
      await api.deleteSessionMessage(sessionId, timestamp);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete message' });
      return;
    }
    // Mirror the backend's delete-with-tool-scaffolding behaviour locally so
    // the UI updates instantly without a refetch:
    //  • user message → drop just that one
    //  • assistant message → drop it plus any directly-preceding
    //    tool-call/tool-response messages (one logical turn)
    const trim = (messages: Message[]): Message[] => {
      const idx = messages.findIndex((m) => m.timestamp === timestamp);
      if (idx === -1) return messages;
      const target = messages[idx];
      if (target.role === 'user') {
        return messages.filter((_, i) => i !== idx);
      }
      if (target.role === 'assistant') {
        let start = idx;
        while (start > 0) {
          const prev = messages[start - 1];
          if (prev.role === 'tool') {
            start -= 1;
            continue;
          }
          if (prev.role === 'assistant' && Array.isArray(prev.tool_calls) && prev.tool_calls.length > 0) {
            start -= 1;
            continue;
          }
          break;
        }
        return [...messages.slice(0, start), ...messages.slice(idx + 1)];
      }
      return messages;
    };

    set((state) => {
      const isForeground = state.currentSession === sessionId;
      const slice = state.sessionsState[sessionId];
      const next: Partial<ChatState> = {};
      if (isForeground) {
        next.messages = trim(state.messages);
      }
      if (slice) {
        next.sessionsState = {
          ...state.sessionsState,
          [sessionId]: {
            ...slice,
            messages: trim(slice.messages),
          },
        };
      }
      return next;
    });
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
        projectSessions: state.projectSessions.map((session) =>
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

  finishStreamingAssistant: (content, citations, attachments) => {
    set((state) => {
      const messages = [...state.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant' && messages[i].isStreaming) {
          messages[i] = {
            ...messages[i],
            content: content ?? messages[i].content,
            isStreaming: false,
            citations: citations ?? messages[i].citations,
            attachments: attachments ?? messages[i].attachments,
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
              attachments,
            },
          ],
        };
      }
      return state;
    });
  },

  updateAttachment: (attachmentId, nextAttachment) => {
    set((state) => ({
      messages: state.messages.map((message) => ({
        ...message,
        attachments: message.attachments?.map((attachment) =>
          attachment.id === attachmentId ? { ...attachment, ...nextAttachment } : attachment
        ),
      })),
    }));
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
        siliconflow: 'SiliconFlow',
        custom: '自定义',
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

  loadCreativeCapabilities: async () => {
    try {
      const config = await api.getConfig();
      set({ creativeCapabilities: config.creative });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load creative capabilities' });
    }
  },

  setCreativeCapabilities: (creative) => {
    set({ creativeCapabilities: creative });
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

  // ───────────────────── Per-session helpers ─────────────────────

  isCurrentSession: (sessionId) => get().currentSession === sessionId,

  getSessionSlice: (sessionId) => {
    const state = get();
    if (state.currentSession === sessionId) {
      return {
        messages: state.messages,
        toolCalls: state.toolCalls,
        timelineEvents: state.timelineEvents,
        activeTool: state.activeTool,
        isLoading: state.isLoading,
        currentTurnId: state.currentTurnId,
        linkedKnowledgeBaseIds: state.linkedKnowledgeBaseIds,
        pendingApproval: state.pendingApproval,
        sessionExecTrusted: state.sessionExecTrusted,
      };
    }
    return state.sessionsState[sessionId] ?? EMPTY_SLICE;
  },

  ensureSessionSlice: (sessionId) => {
    const state = get();
    if (state.currentSession === sessionId) return;
    if (state.sessionsState[sessionId]) return;
    set((current) => ({
      sessionsState: { ...current.sessionsState, [sessionId]: { ...EMPTY_SLICE } },
    }));
  },

  setSessionLoading: (sessionId, loading) => {
    applySliceUpdate(set, get, sessionId, () => ({ isLoading: loading }));
  },

  setSessionActiveTool: (sessionId, tool) => {
    applySliceUpdate(set, get, sessionId, () => ({ activeTool: tool }));
  },

  setSessionCurrentTurnId: (sessionId, turnId) => {
    applySliceUpdate(set, get, sessionId, () => ({ currentTurnId: turnId }));
  },

  startSessionStreamingAssistant: (sessionId) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      messages: [
        ...slice.messages,
        {
          role: 'assistant' as const,
          content: '',
          timestamp: new Date().toISOString(),
          isStreaming: true,
        },
      ],
    }));
  },

  appendSessionStreamingAssistant: (sessionId, chunk) => {
    applySliceUpdate(set, get, sessionId, (slice) => {
      const messages = [...slice.messages];
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
          ...slice.messages,
          {
            role: 'assistant' as const,
            content: chunk,
            timestamp: new Date().toISOString(),
            isStreaming: true,
          },
        ],
      };
    });
  },

  finishSessionStreamingAssistant: (sessionId, content, citations, attachments) => {
    applySliceUpdate(set, get, sessionId, (slice) => {
      const messages = [...slice.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant' && messages[i].isStreaming) {
          messages[i] = {
            ...messages[i],
            content: content ?? messages[i].content,
            isStreaming: false,
            citations: citations ?? messages[i].citations,
            attachments: attachments ?? messages[i].attachments,
          };
          return { messages };
        }
      }
      if (content) {
        return {
          messages: [
            ...slice.messages,
            {
              role: 'assistant' as const,
              content,
              timestamp: new Date().toISOString(),
              isStreaming: false,
              citations,
              attachments,
            },
          ],
        };
      }
      return {};
    });
  },

  addSessionToolCall: (sessionId, tool, toolId) => {
    const id = toolId || `tool-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    let resolvedId = id;
    applySliceUpdate(set, get, sessionId, (slice) => {
      const turnId = slice.currentTurnId;
      if (turnId) {
        const dupById = slice.toolCalls.find(
          (tc) => tc.id === id && tc.status === 'running' && tc.turnId === turnId,
        );
        if (dupById) {
          resolvedId = dupById.id;
          return {};
        }
        const dupByName = slice.toolCalls.find(
          (tc) => tc.tool === tool && tc.status === 'running' && tc.turnId === turnId,
        );
        if (dupByName) {
          resolvedId = dupByName.id;
          return {};
        }
      }
      const newCall: ToolCall = {
        id,
        tool,
        status: 'running',
        timestamp: new Date().toISOString(),
        turnId: turnId || '',
      };
      return { toolCalls: [...slice.toolCalls, newCall] };
    });
    return resolvedId;
  },

  completeSessionToolCall: (sessionId, id, duration) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      toolCalls: slice.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, status: 'completed' as const, duration } : tc,
      ),
    }));
  },

  failSessionToolCall: (sessionId, id) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      toolCalls: slice.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, status: 'error' as const } : tc,
      ),
    }));
  },

  completeAllSessionRunningTools: (sessionId, duration) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      toolCalls: slice.toolCalls.map((tc) =>
        tc.status === 'running' && tc.turnId === slice.currentTurnId
          ? { ...tc, status: 'completed' as const, duration }
          : tc,
      ),
    }));
  },

  addSessionTimelineEvent: (sessionId, event) => {
    applySliceUpdate(set, get, sessionId, (slice) => {
      const turnId = slice.currentTurnId || '';
      const newEvent: TimelineEvent = {
        id: `timeline-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        turnId,
        ...event,
      };
      return { timelineEvents: [...slice.timelineEvents, newEvent] };
    });
  },

  setSessionPendingApproval: (sessionId, approval) => {
    applySliceUpdate(set, get, sessionId, () => ({ pendingApproval: approval }));
  },

  setSessionExecTrusted: (sessionId, trusted) => {
    applySliceUpdate(set, get, sessionId, () => ({ sessionExecTrusted: trusted }));
  },

  setSessionError: (sessionId, error) => {
    if (get().currentSession === sessionId) {
      set({ error });
    }
    // Background sessions surface errors lazily — store on the slice so the
    // sidebar / orchestrator can flag them if needed.
    applySliceUpdate(set, get, sessionId, () => ({}));
  },
}));

/**
 * Apply a slice update either to the foreground top-level fields (when the
 * sessionId matches the current session) or to the appropriate background
 * slice in `sessionsState`. Keeps both paths in lockstep.
 */
function applySliceUpdate(
  set: (partial: Partial<ChatState>) => void,
  get: () => ChatState,
  sessionId: string,
  updater: (slice: SessionSlice) => Partial<SessionSlice>,
): void {
  const state = get();
  if (state.currentSession === sessionId) {
    const currentSlice: SessionSlice = {
      messages: state.messages,
      toolCalls: state.toolCalls,
      timelineEvents: state.timelineEvents,
      activeTool: state.activeTool,
      isLoading: state.isLoading,
      currentTurnId: state.currentTurnId,
      linkedKnowledgeBaseIds: state.linkedKnowledgeBaseIds,
      pendingApproval: state.pendingApproval,
      sessionExecTrusted: state.sessionExecTrusted,
    };
    const patch = updater(currentSlice);
    set(patch);
    return;
  }

  const existing = state.sessionsState[sessionId] ?? EMPTY_SLICE;
  const patch = updater(existing);
  if (Object.keys(patch).length === 0 && state.sessionsState[sessionId]) {
    return;
  }
  const merged: SessionSlice = { ...existing, ...patch };
  set({
    sessionsState: { ...state.sessionsState, [sessionId]: merged },
  });
}
