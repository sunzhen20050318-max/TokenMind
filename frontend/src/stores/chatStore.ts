import { create } from 'zustand';
import type {
  Attachment,
  Message,
  MessageCitation,
  PendingBrowserHandoff,
  PendingToolApproval,
  PendingUserQuestion,
  Project,
  Session,
  TaskListSnapshot,
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

export interface FileEditEvent {
  version: number;
  call_id: string;
  tool: 'write_file' | 'edit_file';
  path: string;
  phase: 'start' | 'end' | 'error';
  added: number;
  deleted: number;
  approximate: boolean;
  status: 'editing' | 'done' | 'error';
  error?: string;
}

export interface TimelineEvent {
  id: string;
  type: 'progress' | 'tool_start' | 'tool_end' | 'tool_error' | 'reasoning' | 'file_edit_progress';
  content: string;
  timestamp: string;
  turnId: string;
  toolId?: string;
  toolName?: string;
  duration?: number;
  detail?: string;
  fileEdit?: FileEditEvent;
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
  activeWikiKbId: string | null;
  pendingApproval: PendingToolApproval | null;
  pendingUserQuestion: PendingUserQuestion | null;
  /**
   * Latest snapshot of the agent's task list for this session, or null
   * if the agent has not surfaced one yet (or cleared it). Each call to
   * the ``task_list`` tool replaces this; the UI renders the snapshot
   * as a single in-place bubble in the chat thread.
   */
  taskList: TaskListSnapshot | null;
  /**
   * If the user manually dismissed (×) the task list bubble, we remember
   * that id so subsequent updates from the agent within the same turn
   * don't pop the bubble back. A fresh ``task_list_id`` (next turn)
   * clears this implicitly.
   */
  dismissedTaskListId: string | null;
  /**
   * Number of leading messages that have been consolidated into
   * HISTORY.md/MEMORY.md and are therefore not part of the LLM's
   * working context anymore. The UI folds ``messages[0:consolidatedOffset]``
   * into a single "已固化 N 条历史" placeholder. Mirrors the backend's
   * ``Session.last_consolidated``.
   */
  consolidatedOffset: number;
  /**
   * Reply style chosen via /personality. ``null`` means "let the model
   * use its default voice". Mirrors backend ``Session.personality``.
   */
  personality: 'warm' | 'pragmatic' | null;
  /**
   * Plan-mode toggle (input-bar button). When true, the system prompt
   * tells the agent to call ``task_list`` before non-trivial multi-step
   * work. Mirrors backend ``Session.plan_mode``.
   */
  planMode: boolean;
  /**
   * Messages typed while the agent was busy. Auto-flushed (one at a time)
   * when ``isLoading`` flips back to ``false``. See ``ChatWindow`` for the
   * drain effect.
   */
  pendingMessages: PendingChatMessage[];
  sessionExecTrusted: boolean;
  /**
   * Token-usage snapshot from this session's most recent LLM call, shown in
   * /status. Per-session: snapshotted on navigation away and restored on
   * return so a fresh session doesn't inherit a previous session's numbers.
   * ``loadHistory`` reloads them from the backend for sessions not in memory.
   */
  lastPromptTokens: number | null;
  lastPromptAt: string | null;
  lastPromptModel: string | null;
}

export interface PendingChatMessage {
  id: string;
  content: string;
  queuedAt: string;
}

const EMPTY_SLICE: SessionSlice = {
  messages: [],
  toolCalls: [],
  timelineEvents: [],
  activeTool: null,
  isLoading: false,
  currentTurnId: null,
  linkedKnowledgeBaseIds: [],
  activeWikiKbId: null,
  pendingApproval: null,
  pendingUserQuestion: null,
  taskList: null,
  dismissedTaskListId: null,
  consolidatedOffset: 0,
  personality: null,
  planMode: false,
  pendingMessages: [],
  sessionExecTrusted: false,
  lastPromptTokens: null,
  lastPromptAt: null,
  lastPromptModel: null,
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
  /** Per-session WebSocket connection state. Updated reactively by the
   * orchestrator so components can subscribe — `isConnected` above is the
   * legacy single-session flag still kept for compatibility. */
  connectedSessions: Set<string>;
  error: string | null;
  activeTool: string | null;
  currentTurnId: string | null; // The turnId for the current conversation turn
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  pendingApproval: PendingToolApproval | null;
  pendingUserQuestion: PendingUserQuestion | null;
  taskList: TaskListSnapshot | null;
  dismissedTaskListId: string | null;
  consolidatedOffset: number;
  personality: 'warm' | 'pragmatic' | null;
  planMode: boolean;
  pendingMessages: PendingChatMessage[];
  sessionExecTrusted: boolean;
  sessionsState: Record<string, SessionSlice>;
  modelProviders: ModelProvider[];
  activeModelId: string | null;
  modelProvidersStatus: 'idle' | 'loading' | 'ready' | 'error';
  /** TokenMind's *soft* auto-/compact threshold. NOT the model's
   *  hardware context limit — sourced from ``agents.defaults.context_window_tokens``. */
  compactionThresholdTokens: number | null;
  /** Precise prompt-token count from the most recent LLM call (input +
   *  cached), straight from the provider's usage payload. */
  lastPromptTokens: number | null;
  lastPromptAt: string | null;
  lastPromptModel: string | null;
  /** Global single-handoff state. The browser tool requests a handoff
   *  when it hits a login / verification gate; the user resolves it via
   *  the modal. Carries session_id so the modal only shows in the
   *  originating chat. */
  pendingBrowserHandoff: PendingBrowserHandoff | null;
  creativeCapabilities: CreativeSettings | null;
  availableKnowledgeBases: KnowledgeBase[];
  linkedKnowledgeBaseIds: string[];
  activeWikiKbId: string | null;
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
  setActiveProjectInstructions: (instructions: string) => void;
  leaveProject: () => void;
  setLoading: (loading: boolean) => void;
  setConnected: (connected: boolean) => void;
  setSessionConnected: (sessionId: string, connected: boolean) => void;
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
  applySessionTitle: (sessionId: string, title: string) => void;
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
  setActiveWikiKb: (sessionId: string, kbId: string | null) => Promise<void>;
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
  /**
   * Update-or-insert a file_edit_progress timeline event for the given
   * call_id. Streaming generates dozens of these per file edit; we keep a
   * single timeline row per call_id and mutate its diff counts in place
   * so the UI shows a rolling +N/-M counter instead of a spammy log.
   */
  applySessionFileEditProgress: (
    sessionId: string,
    event: FileEditEvent,
  ) => void;
  addSessionMessage: (sessionId: string, message: Message) => void;

  setSessionPendingApproval: (sessionId: string, approval: PendingToolApproval | null) => void;
  setSessionPendingUserQuestion: (sessionId: string, question: PendingUserQuestion | null) => void;
  setSessionTaskList: (sessionId: string, snapshot: TaskListSnapshot | null) => void;
  dismissSessionTaskList: (sessionId: string) => void;
  /** Apply a server-pushed compaction: bump the visible offset so the
   *  consolidated portion folds into a placeholder. */
  applySessionCompacted: (sessionId: string, offset: number) => void;
  /** User-initiated /compact: POSTs to the backend then mirrors the new
   *  offset locally. Returns the number of messages that were compacted
   *  (0 if nothing eligible). */
  compactSession: (sessionId: string) => Promise<number>;
  /** /personality picker: PATCH the session and mirror locally. ``null``
   *  resets to the system default. */
  setSessionPersonality: (sessionId: string, personality: 'warm' | 'pragmatic' | null) => Promise<void>;
  /** WS-driven update of last_prompt_tokens for the current session.
   *  Ignored when ``sessionId`` doesn't match the foreground session
   *  (background sessions re-hydrate from API on next switch). */
  applySessionUsage: (
    sessionId: string,
    usage: { last_prompt_tokens: number; last_prompt_at: string | null; last_prompt_model: string | null },
  ) => void;
  setPendingBrowserHandoff: (handoff: PendingBrowserHandoff | null) => void;
  /** Plan-mode toggle (input-bar button + /plan command later). PATCH +
   *  mirror. */
  setSessionPlanMode: (sessionId: string, enabled: boolean) => Promise<void>;
  enqueuePendingMessage: (sessionId: string, content: string) => void;
  removePendingMessage: (sessionId: string, id: string) => void;
  shiftPendingMessage: (sessionId: string) => PendingChatMessage | null;
  clearPendingMessages: (sessionId: string) => void;
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
  connectedSessions: new Set<string>(),
  error: null,
  activeTool: null,
  toolCalls: [],
  timelineEvents: [],
  currentTurnId: null,
  pendingApproval: null,
  pendingUserQuestion: null,
  taskList: null,
  dismissedTaskListId: null,
  consolidatedOffset: 0,
  personality: null,
  planMode: false,
  pendingMessages: [],
  sessionExecTrusted: false,
  sessionsState: {},
  modelProviders: [],
  activeModelId: null,
  modelProvidersStatus: 'idle',
  compactionThresholdTokens: null,
  lastPromptTokens: null,
  pendingBrowserHandoff: null,
  lastPromptAt: null,
  lastPromptModel: null,
  creativeCapabilities: null,
  availableKnowledgeBases: [],
  linkedKnowledgeBaseIds: [],
  activeWikiKbId: null,
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
      // Stamp the optimistic entry with "now" so the sidebar's time-bucket
      // grouping puts a brand-new session under "今天" instead of falling
      // back to "更早" (which is what happens when ``updated_at`` /
      // ``created_at`` are undefined). The backend will overwrite these
      // with its own timestamps the next time loadSessions() refreshes.
      const nowIso = new Date().toISOString();
      const newSession: Session = {
        session_id: sessionId,
        message_count: 0,
        project_id: shouldTreatAsProject ? resolvedProjectId || undefined : undefined,
        created_at: nowIso,
        updated_at: nowIso,
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
        activeWikiKbId: state.activeWikiKbId,
        pendingApproval: state.pendingApproval,
        pendingUserQuestion: state.pendingUserQuestion,
        taskList: state.taskList,
        dismissedTaskListId: state.dismissedTaskListId,
        consolidatedOffset: state.consolidatedOffset,
        personality: state.personality,
        planMode: state.planMode,
        pendingMessages: state.pendingMessages,
        sessionExecTrusted: state.sessionExecTrusted,
        lastPromptTokens: state.lastPromptTokens,
        lastPromptAt: state.lastPromptAt,
        lastPromptModel: state.lastPromptModel,
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
      activeWikiKbId: restored?.activeWikiKbId ?? null,
      pendingApproval: restored?.pendingApproval ?? null,
      pendingUserQuestion: restored?.pendingUserQuestion ?? null,
      taskList: restored?.taskList ?? null,
      dismissedTaskListId: restored?.dismissedTaskListId ?? null,
      consolidatedOffset: restored?.consolidatedOffset ?? 0,
      personality: restored?.personality ?? null,
      planMode: restored?.planMode ?? false,
      pendingMessages: restored?.pendingMessages ?? [],
      sessionExecTrusted: restored?.sessionExecTrusted ?? false,
      lastPromptTokens: restored?.lastPromptTokens ?? null,
      lastPromptAt: restored?.lastPromptAt ?? null,
      lastPromptModel: restored?.lastPromptModel ?? null,
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
        activeWikiKbId: null,
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
          activeWikiKbId: deletingActiveProject ? null : state.activeWikiKbId,
        };
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete project' });
    }
  },

  setActiveProjectInstructions: (instructions) => {
    set((state) => {
      const next = state.activeProject ? { ...state.activeProject, instructions } : state.activeProject;
      return {
        activeProject: next,
        projects: state.projects.map((project) =>
          project.id === state.activeProjectId ? { ...project, instructions } : project,
        ),
      };
    });
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

  setSessionConnected: (sessionId, connected) => {
    set((state) => {
      const has = state.connectedSessions.has(sessionId);
      if (has === connected) return state;
      const next = new Set(state.connectedSessions);
      if (connected) next.add(sessionId);
      else next.delete(sessionId);
      return { connectedSessions: next };
    });
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
      const {
        messages,
        timeline_events,
        consolidated_offset,
        personality,
        plan_mode,
        compaction_threshold_tokens,
        last_prompt_tokens,
        last_prompt_at,
        last_prompt_model,
      } = await api.getHistory(sessionId);
      set({
        messages,
        timelineEvents: timeline_events || [],
        toolCalls: [],
        currentTurnId: null,
        consolidatedOffset: consolidated_offset ?? 0,
        personality: personality ?? null,
        planMode: !!plan_mode,
        compactionThresholdTokens: compaction_threshold_tokens || null,
        lastPromptTokens: last_prompt_tokens || null,
        lastPromptAt: last_prompt_at || null,
        lastPromptModel: last_prompt_model || null,
        isLoading: false,
      });
    } catch (e) {
      // Session might not exist yet, that's ok
      set({
        messages: [],
        timelineEvents: [],
        toolCalls: [],
        consolidatedOffset: 0,
        personality: null,
        planMode: false,
        lastPromptTokens: null,
        lastPromptAt: null,
        lastPromptModel: null,
        isLoading: false,
      });
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
    // Mirror the backend logic locally so the UI updates instantly: a user
    // message takes the entire assistant turn it triggered with it (the
    // assistant tool-call message + any tool responses + the final
    // assistant content message), stopping at the next user message.
    const trim = (messages: Message[]): Message[] => {
      const idx = messages.findIndex((m) => m.timestamp === timestamp);
      if (idx === -1) return messages;
      if (messages[idx].role !== 'user') return messages;
      let end = idx + 1;
      while (end < messages.length && messages[end].role !== 'user') {
        end += 1;
      }
      return [...messages.slice(0, idx), ...messages.slice(end)];
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

  applySessionTitle: (sessionId, title) => {
    // Pure local update from a server-pushed auto-summarized title — no
    // PUT roundtrip, the backend already persisted.
    const trimmed = title.trim();
    if (!trimmed) return;
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.session_id === sessionId
          ? { ...session, title: trimmed }
          : session,
      ),
      projectSessions: state.projectSessions.map((session) =>
        session.session_id === sessionId
          ? { ...session, title: trimmed }
          : session,
      ),
    }));
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
        mimo: 'MiMo',
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

  setActiveWikiKb: async (sessionId, kbId) => {
    try {
      const result = await api.patchSession(sessionId, { active_wiki_kb_id: kbId });
      applySliceUpdate(set, get, sessionId, () => ({
        activeWikiKbId: result.active_wiki_kb_id,
      }));
    } catch (e) {
      console.error('Failed to set active wiki KB', e);
      set({ error: e instanceof Error ? e.message : 'Failed to set active wiki KB' });
      throw e;
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
        activeWikiKbId: state.activeWikiKbId,
        pendingApproval: state.pendingApproval,
        pendingUserQuestion: state.pendingUserQuestion,
        taskList: state.taskList,
        dismissedTaskListId: state.dismissedTaskListId,
        consolidatedOffset: state.consolidatedOffset,
        personality: state.personality,
        planMode: state.planMode,
        pendingMessages: state.pendingMessages,
        sessionExecTrusted: state.sessionExecTrusted,
        lastPromptTokens: state.lastPromptTokens,
        lastPromptAt: state.lastPromptAt,
        lastPromptModel: state.lastPromptModel,
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

  applySessionFileEditProgress: (sessionId, event) => {
    applySliceUpdate(set, get, sessionId, (slice) => {
      const turnId = slice.currentTurnId || '';
      const callId = event.call_id;
      const existing = slice.timelineEvents.findIndex(
        (e) => e.type === 'file_edit_progress' && e.fileEdit?.call_id === callId,
      );
      if (existing >= 0) {
        const updated = slice.timelineEvents.slice();
        updated[existing] = {
          ...updated[existing],
          fileEdit: event,
          content: event.path,
          detail: event.error || updated[existing].detail,
        };
        return { timelineEvents: updated };
      }
      const newEvent: TimelineEvent = {
        id: `file-edit-${callId}-${Date.now()}`,
        type: 'file_edit_progress',
        content: event.path,
        timestamp: new Date().toISOString(),
        turnId,
        toolId: callId,
        toolName: event.tool,
        fileEdit: event,
        detail: event.error,
      };
      return { timelineEvents: [...slice.timelineEvents, newEvent] };
    });
  },

  setSessionPendingApproval: (sessionId, approval) => {
    applySliceUpdate(set, get, sessionId, () => ({ pendingApproval: approval }));
  },

  setSessionPendingUserQuestion: (sessionId, question) => {
    applySliceUpdate(set, get, sessionId, () => ({ pendingUserQuestion: question }));
  },

  setSessionTaskList: (sessionId, snapshot) => {
    applySliceUpdate(set, get, sessionId, (slice) => {
      // If user dismissed the bubble for this exact id, swallow updates
      // to avoid re-popping mid-turn. A fresh id (next turn) implicitly
      // clears the dismissed flag.
      if (snapshot && slice.dismissedTaskListId === snapshot.task_list_id) {
        return {};
      }
      const clearedDismiss =
        snapshot && slice.dismissedTaskListId && slice.dismissedTaskListId !== snapshot.task_list_id;
      return clearedDismiss
        ? { taskList: snapshot, dismissedTaskListId: null }
        : { taskList: snapshot };
    });
  },

  dismissSessionTaskList: (sessionId) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      taskList: null,
      dismissedTaskListId: slice.taskList?.task_list_id ?? slice.dismissedTaskListId,
    }));
  },

  applySessionCompacted: (sessionId, offset) => {
    if (typeof offset !== 'number' || offset < 0) return;
    applySliceUpdate(set, get, sessionId, (slice) => {
      // Never regress — concurrent multi-tab compaction or stale WS
      // frames could otherwise unfold the placeholder.
      const next = Math.max(slice.consolidatedOffset, offset);
      if (next === slice.consolidatedOffset) return {};
      return { consolidatedOffset: next };
    });
  },

  compactSession: async (sessionId) => {
    try {
      const result = await api.compactSession(sessionId);
      if (result.messages_compacted > 0) {
        // The WS frame from the backend will redundantly call
        // applySessionCompacted too; ours just makes the UI feel
        // instant. Both are idempotent thanks to the max() guard above.
        get().applySessionCompacted(sessionId, result.consolidated_offset);
      }
      return result.messages_compacted;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to compact session' });
      return 0;
    }
  },

  setSessionPersonality: async (sessionId, personality) => {
    try {
      await api.patchSession(sessionId, { personality });
      applySliceUpdate(set, get, sessionId, () => ({ personality }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to set personality' });
    }
  },

  applySessionUsage: (sessionId, usage) => {
    // Only the foreground session is mirrored in top-level fields, and
    // /status only reads from the foreground session anyway. Background
    // sessions re-fetch their numbers via loadHistory when activated.
    if (get().currentSession !== sessionId) return;
    if (!usage.last_prompt_tokens || usage.last_prompt_tokens <= 0) return;
    set({
      lastPromptTokens: usage.last_prompt_tokens,
      lastPromptAt: usage.last_prompt_at,
      lastPromptModel: usage.last_prompt_model,
    });
  },

  setPendingBrowserHandoff: (handoff) => {
    set({ pendingBrowserHandoff: handoff });
  },

  setSessionPlanMode: async (sessionId, enabled) => {
    try {
      await api.patchSession(sessionId, { plan_mode: enabled });
      applySliceUpdate(set, get, sessionId, () => ({ planMode: enabled }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to set plan mode' });
    }
  },

  addSessionMessage: (sessionId, message) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      messages: [...slice.messages, message],
    }));
  },

  enqueuePendingMessage: (sessionId, content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const entry: PendingChatMessage = {
      id: `pending-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      content: trimmed,
      queuedAt: new Date().toISOString(),
    };
    applySliceUpdate(set, get, sessionId, (slice) => ({
      pendingMessages: [...slice.pendingMessages, entry],
    }));
  },

  removePendingMessage: (sessionId, id) => {
    applySliceUpdate(set, get, sessionId, (slice) => ({
      pendingMessages: slice.pendingMessages.filter((item) => item.id !== id),
    }));
  },

  clearPendingMessages: (sessionId) => {
    applySliceUpdate(set, get, sessionId, () => ({ pendingMessages: [] }));
  },

  shiftPendingMessage: (sessionId) => {
    const state = get();
    const slice =
      state.currentSession === sessionId
        ? ({
            messages: state.messages,
            toolCalls: state.toolCalls,
            timelineEvents: state.timelineEvents,
            activeTool: state.activeTool,
            isLoading: state.isLoading,
            currentTurnId: state.currentTurnId,
            linkedKnowledgeBaseIds: state.linkedKnowledgeBaseIds,
            activeWikiKbId: state.activeWikiKbId,
            pendingApproval: state.pendingApproval,
            pendingUserQuestion: state.pendingUserQuestion,
            taskList: state.taskList,
            dismissedTaskListId: state.dismissedTaskListId,
            consolidatedOffset: state.consolidatedOffset,
            pendingMessages: state.pendingMessages,
            sessionExecTrusted: state.sessionExecTrusted,
          } as SessionSlice)
        : state.sessionsState[sessionId];
    if (!slice || slice.pendingMessages.length === 0) return null;
    const [head, ...rest] = slice.pendingMessages;
    applySliceUpdate(set, get, sessionId, () => ({ pendingMessages: rest }));
    return head;
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
      activeWikiKbId: state.activeWikiKbId,
      pendingApproval: state.pendingApproval,
      pendingUserQuestion: state.pendingUserQuestion,
      taskList: state.taskList,
      dismissedTaskListId: state.dismissedTaskListId,
      consolidatedOffset: state.consolidatedOffset,
      personality: state.personality,
      planMode: state.planMode,
      pendingMessages: state.pendingMessages,
      sessionExecTrusted: state.sessionExecTrusted,
      lastPromptTokens: state.lastPromptTokens,
      lastPromptAt: state.lastPromptAt,
      lastPromptModel: state.lastPromptModel,
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
