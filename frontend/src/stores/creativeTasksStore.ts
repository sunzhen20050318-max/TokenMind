import { create } from 'zustand';
import { api } from '../services/api';
import type {
  MusicGenerateRequest,
  MusicGenerateResponse,
  TtsSynthesizeRequest,
  TtsSynthesizeResponse,
  VoiceCloneCreateRequest,
  VoiceCloneCreateResponse,
  VoiceDesignCreateRequest,
  VoiceDesignCreateResponse,
} from '../types';

/**
 * Shared store for "creative" long-running tasks (music generation, voice
 * cloning, TTS synthesis, voice design).
 *
 * Each task lives in the store, NOT in a page's local React state — this is
 * what lets a task survive when the user navigates away from the studio
 * (to chat / settings / asset library / another studio). Pages only render
 * the in-memory state; the actual API call is fire-and-forget from the
 * store action.
 */

export type CreativeTaskKind = 'music' | 'voice-clone' | 'tts' | 'voice-design';
export type CreativeTaskStatus = 'pending' | 'running' | 'success' | 'error';

interface BaseTaskFields<TKind extends CreativeTaskKind> {
  id: string;
  kind: TKind;
  status: CreativeTaskStatus;
  startedAt: number;
  finishedAt?: number;
  error?: string;
  /**
   * Free-form summary surfaced in the global indicator so the user can tell
   * at a glance what's running (e.g. "AI 励志说唱").
   */
  label: string;
}

export interface MusicTaskMeta {
  trackIds: string[];
  count: number;
  songName: string;
  description: string;
  modelLabel: string;
  providerLabel: string;
  generatedAt: string;
  pendingTitles: string[];
}

export interface MusicTask extends BaseTaskFields<'music'> {
  payload: MusicGenerateRequest & {
    reference_audio_base64: string | null;
    reference_audio_name: string | null;
  };
  meta: MusicTaskMeta;
  response?: MusicGenerateResponse;
}

export interface VoiceCloneTaskMeta {
  filename: string;
}

export interface VoiceCloneTask extends BaseTaskFields<'voice-clone'> {
  /**
   * The voice clone flow is two API calls (upload then create). We track which
   * sub-phase we're in so the page can show "上传中" vs "克隆中".
   */
  phase: 'uploading' | 'cloning' | 'done';
  payload: Omit<VoiceCloneCreateRequest, 'file_id'> & { previewText: string | null };
  meta: VoiceCloneTaskMeta;
  uploadedFileId?: number;
  response?: VoiceCloneCreateResponse;
}

export interface TtsTask extends BaseTaskFields<'tts'> {
  payload: TtsSynthesizeRequest;
  voiceLabel: string;
  response?: TtsSynthesizeResponse;
}

export interface VoiceDesignTask extends BaseTaskFields<'voice-design'> {
  payload: VoiceDesignCreateRequest;
  response?: VoiceDesignCreateResponse;
}

export type CreativeTask = MusicTask | VoiceCloneTask | TtsTask | VoiceDesignTask;

interface CreativeTasksState {
  tasks: Record<string, CreativeTask>;
  /** Insertion order so we can show recent-first lists per kind. */
  order: string[];

  // ── Music actions ──
  startMusicGeneration: (
    payload: MusicTask['payload'],
    meta: MusicTaskMeta,
  ) => string;

  // ── Voice clone actions ──
  startVoiceClone: (params: {
    file: File;
    request: Omit<VoiceCloneCreateRequest, 'file_id'>;
    label: string;
  }) => string;

  // ── TTS actions ──
  startTtsSynthesis: (payload: TtsSynthesizeRequest, voiceLabel: string) => string;

  // ── Voice design actions ──
  startVoiceDesign: (payload: VoiceDesignCreateRequest, label: string) => string;

  // ── Selectors / utilities ──
  acknowledgeTask: (taskId: string) => void;
  removeTask: (taskId: string) => void;
}

function nextId(kind: CreativeTaskKind): string {
  return `${kind}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useCreativeTasksStore = create<CreativeTasksState>((set, get) => ({
  tasks: {},
  order: [],

  startMusicGeneration: (payload, meta) => {
    const id = nextId('music');
    const task: MusicTask = {
      id,
      kind: 'music',
      status: 'running',
      startedAt: Date.now(),
      label: meta.songName.trim() || meta.description.trim() || 'AI 音乐生成',
      payload,
      meta,
    };
    set((state) => ({
      tasks: { ...state.tasks, [id]: task },
      order: [id, ...state.order],
    }));

    void (async () => {
      try {
        const response = await api.generateMusic(payload);
        set((state) => {
          const existing = state.tasks[id] as MusicTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'success',
                finishedAt: Date.now(),
                response,
              },
            },
          };
        });
      } catch (err) {
        set((state) => {
          const existing = state.tasks[id] as MusicTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'error',
                finishedAt: Date.now(),
                error: err instanceof Error ? err.message : '音乐生成失败',
              },
            },
          };
        });
      }
    })();

    return id;
  },

  startVoiceClone: ({ file, request, label }) => {
    const id = nextId('voice-clone');
    const task: VoiceCloneTask = {
      id,
      kind: 'voice-clone',
      status: 'running',
      phase: 'uploading',
      startedAt: Date.now(),
      label,
      payload: { ...request, previewText: request.preview_text ?? null },
      meta: { filename: file.name },
    };
    set((state) => ({
      tasks: { ...state.tasks, [id]: task },
      order: [id, ...state.order],
    }));

    void (async () => {
      try {
        const uploaded = await api.uploadVoiceCloneAudio(file);
        set((state) => {
          const existing = state.tasks[id] as VoiceCloneTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                phase: 'cloning',
                uploadedFileId: uploaded.file_id,
              },
            },
          };
        });
        const cloned = await api.createVoiceClone({
          ...request,
          file_id: uploaded.file_id,
        });
        set((state) => {
          const existing = state.tasks[id] as VoiceCloneTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'success',
                phase: 'done',
                finishedAt: Date.now(),
                response: cloned,
              },
            },
          };
        });
      } catch (err) {
        set((state) => {
          const existing = state.tasks[id] as VoiceCloneTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'error',
                finishedAt: Date.now(),
                error: err instanceof Error ? err.message : '声音克隆失败',
              },
            },
          };
        });
      }
    })();

    return id;
  },

  startTtsSynthesis: (payload, voiceLabel) => {
    const id = nextId('tts');
    const task: TtsTask = {
      id,
      kind: 'tts',
      status: 'running',
      startedAt: Date.now(),
      label: payload.text.slice(0, 40) || 'TTS 合成',
      payload,
      voiceLabel,
    };
    set((state) => ({
      tasks: { ...state.tasks, [id]: task },
      order: [id, ...state.order],
    }));

    void (async () => {
      try {
        const response = await api.synthesizeVoice(payload);
        set((state) => {
          const existing = state.tasks[id] as TtsTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'success',
                finishedAt: Date.now(),
                response,
              },
            },
          };
        });
      } catch (err) {
        set((state) => {
          const existing = state.tasks[id] as TtsTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'error',
                finishedAt: Date.now(),
                error: err instanceof Error ? err.message : '语音合成失败',
              },
            },
          };
        });
      }
    })();

    return id;
  },

  startVoiceDesign: (payload, label) => {
    const id = nextId('voice-design');
    const task: VoiceDesignTask = {
      id,
      kind: 'voice-design',
      status: 'running',
      startedAt: Date.now(),
      label,
      payload,
    };
    set((state) => ({
      tasks: { ...state.tasks, [id]: task },
      order: [id, ...state.order],
    }));

    void (async () => {
      try {
        const response = await api.designVoice(payload);
        set((state) => {
          const existing = state.tasks[id] as VoiceDesignTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'success',
                finishedAt: Date.now(),
                response,
              },
            },
          };
        });
      } catch (err) {
        set((state) => {
          const existing = state.tasks[id] as VoiceDesignTask | undefined;
          if (!existing) return {};
          return {
            tasks: {
              ...state.tasks,
              [id]: {
                ...existing,
                status: 'error',
                finishedAt: Date.now(),
                error: err instanceof Error ? err.message : '语音设计失败',
              },
            },
          };
        });
      }
    })();

    return id;
  },

  acknowledgeTask: (taskId) => {
    // Used by pages after they've consumed the result (e.g. inserted attachment
    // into their local list). Keeps the task in memory so other pages can still
    // see it in the global indicator until removed.
    const task = get().tasks[taskId];
    if (!task) return;
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: { ...task, finishedAt: task.finishedAt ?? Date.now() },
      },
    }));
  },

  removeTask: (taskId) => {
    set((state) => {
      if (!state.tasks[taskId]) return {};
      const { [taskId]: _removed, ...rest } = state.tasks;
      return {
        tasks: rest,
        order: state.order.filter((id) => id !== taskId),
      };
    });
  },
}));

// ─────────────────────────────────────────────────────────────────────────────
// Convenience selectors
// ─────────────────────────────────────────────────────────────────────────────

export function selectTasksByKind<TKind extends CreativeTaskKind>(
  kind: TKind,
): (state: CreativeTasksState) => Extract<CreativeTask, { kind: TKind }>[] {
  return (state) =>
    state.order
      .map((id) => state.tasks[id])
      .filter((task): task is Extract<CreativeTask, { kind: TKind }> => task?.kind === kind);
}

export function selectRunningCount(state: CreativeTasksState): number {
  let n = 0;
  for (const id of state.order) {
    if (state.tasks[id]?.status === 'running') n += 1;
  }
  return n;
}

export function selectRunningTasks(state: CreativeTasksState): CreativeTask[] {
  return state.order
    .map((id) => state.tasks[id])
    .filter((task): task is CreativeTask => !!task && task.status === 'running');
}
