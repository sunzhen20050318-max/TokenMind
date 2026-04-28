import { create } from 'zustand';
import { browserAgentApi } from '../services/browserAgent';
import type {
  BrowserAgentEnvCheck,
  BrowserArtifact,
  BrowserStep,
  BrowserStreamEvent,
  BrowserTaskDetailResponse,
  BrowserTaskListItem,
  BrowserTaskStatus,
  CreateBrowserTaskRequest,
} from '../types/browserAgent';

/**
 * State for the Web Agent module. Survives across navigation so that a long
 * running browser task keeps progressing while the user is in chat / settings.
 *
 * Detail subscriptions use a WebSocket: the initial GET fetches the historical
 * snapshot and then the WS streams live deltas. We only fall back to polling
 * if the WS open fails outright.
 */

interface BrowserAgentState {
  envCheck: BrowserAgentEnvCheck | null;
  envCheckLoading: boolean;
  envCheckError: string | null;

  tasks: BrowserTaskListItem[];
  tasksLoading: boolean;
  tasksError: string | null;

  selectedTaskId: string | null;
  detail: BrowserTaskDetailResponse | null;
  detailLoading: boolean;
  detailError: string | null;
  detailSocket: WebSocket | null;
  /** ID of the step the user clicked to "scrub" the screenshot replay. */
  focusedStepIndex: number | null;

  submitInFlight: boolean;
  submitError: string | null;

  refreshEnvCheck: () => Promise<void>;
  refreshTasks: (params?: { projectId?: string }) => Promise<void>;
  selectTask: (taskId: string | null) => void;
  refreshDetail: () => Promise<void>;
  focusStep: (stepIndex: number | null) => void;
  createTask: (payload: CreateBrowserTaskRequest) => Promise<string | null>;
  cancelTask: (taskId: string) => Promise<void>;
  takeoverTask: (taskId: string, reason?: string) => Promise<void>;
  resumeTask: (taskId: string) => Promise<void>;
  intervene: (
    taskId: string,
    action: Parameters<typeof browserAgentApi.intervene>[1],
    args: Record<string, unknown>,
  ) => Promise<boolean>;
}

const FINAL_STATUSES = new Set<BrowserTaskStatus>(['completed', 'failed', 'cancelled']);

function mergeStep(existing: BrowserStep[], incoming: BrowserStep): BrowserStep[] {
  const idx = existing.findIndex((s) => s.id === incoming.id || s.step_index === incoming.step_index);
  if (idx === -1) return [...existing, incoming];
  const next = existing.slice();
  next[idx] = incoming;
  return next;
}

function mergeArtifact(existing: BrowserArtifact[], incoming: BrowserArtifact): BrowserArtifact[] {
  if (existing.some((a) => a.id === incoming.id)) return existing;
  return [...existing, incoming];
}

export const useBrowserAgentStore = create<BrowserAgentState>((set, get) => ({
  envCheck: null,
  envCheckLoading: false,
  envCheckError: null,

  tasks: [],
  tasksLoading: false,
  tasksError: null,

  selectedTaskId: null,
  detail: null,
  detailLoading: false,
  detailError: null,
  detailSocket: null,
  focusedStepIndex: null,

  submitInFlight: false,
  submitError: null,

  async refreshEnvCheck() {
    set({ envCheckLoading: true, envCheckError: null });
    try {
      const result = await browserAgentApi.getEnvCheck();
      set({ envCheck: result, envCheckLoading: false });
    } catch (err) {
      set({
        envCheckLoading: false,
        envCheckError: err instanceof Error ? err.message : '环境检测失败',
      });
    }
  },

  async refreshTasks(params) {
    set({ tasksLoading: true, tasksError: null });
    try {
      const result = await browserAgentApi.listTasks(params);
      set({ tasks: result.items, tasksLoading: false });
    } catch (err) {
      set({
        tasksLoading: false,
        tasksError: err instanceof Error ? err.message : '加载任务失败',
      });
    }
  },

  selectTask(taskId) {
    const { detailSocket } = get();
    if (detailSocket) {
      detailSocket.close();
    }

    if (!taskId) {
      set({
        selectedTaskId: null,
        detail: null,
        detailError: null,
        detailLoading: false,
        detailSocket: null,
        focusedStepIndex: null,
      });
      return;
    }

    set({
      selectedTaskId: taskId,
      detail: null,
      detailError: null,
      detailLoading: true,
      detailSocket: null,
      focusedStepIndex: null,
    });

    void get().refreshDetail();

    let socket: WebSocket;
    try {
      socket = browserAgentApi.openStream(taskId);
    } catch (err) {
      // If WS construction throws (rare), fall back to no-stream mode and
      // surface the error in the detail panel.
      set({
        detailError: err instanceof Error ? err.message : 'WebSocket 连接失败',
      });
      return;
    }

    socket.onmessage = (event) => {
      let payload: BrowserStreamEvent;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      // Drop events for stale subscriptions (user switched tasks fast).
      if (get().selectedTaskId !== taskId) return;

      set((state) => {
        const detail = state.detail;
        if (!detail) return {};
        if (payload.type === 'step') {
          return {
            detail: {
              ...detail,
              steps: mergeStep(detail.steps, payload.step),
              task: { ...detail.task, step_count: payload.step.step_index },
            },
          };
        }
        if (payload.type === 'artifact') {
          return {
            detail: {
              ...detail,
              artifacts: mergeArtifact(detail.artifacts, payload.artifact),
            },
          };
        }
        if (payload.type === 'status') {
          return {
            detail: {
              ...detail,
              task: {
                ...detail.task,
                status: payload.status,
                result_summary: payload.result_summary ?? detail.task.result_summary,
                error_detail: payload.error ?? detail.task.error_detail,
              },
            },
          };
        }
        return {};
      });
    };

    socket.onerror = () => {
      // Stream errors aren't fatal — REST detail still works. Surface a hint.
      set((state) => ({
        detailError: state.detailError ?? '实时连接中断，下次进入会重新订阅',
      }));
    };

    socket.onclose = () => {
      set((state) => (state.detailSocket === socket ? { detailSocket: null } : {}));
    };

    set({ detailSocket: socket });
  },

  async refreshDetail() {
    const { selectedTaskId } = get();
    if (!selectedTaskId) return;
    try {
      const detail = await browserAgentApi.getTask(selectedTaskId);
      set((state) => {
        if (state.selectedTaskId !== selectedTaskId) return {};
        return { detail, detailLoading: false, detailError: null };
      });
    } catch (err) {
      set((state) => {
        if (state.selectedTaskId !== selectedTaskId) return {};
        return {
          detailLoading: false,
          detailError: err instanceof Error ? err.message : '加载任务详情失败',
        };
      });
    }
  },

  focusStep(stepIndex) {
    set({ focusedStepIndex: stepIndex });
  },

  async createTask(payload) {
    set({ submitInFlight: true, submitError: null });
    try {
      const result = await browserAgentApi.createTask(payload);
      set({ submitInFlight: false });
      await get().refreshTasks(payload.project_id ? { projectId: payload.project_id } : undefined);
      get().selectTask(result.task.id);
      return result.task.id;
    } catch (err) {
      set({
        submitInFlight: false,
        submitError: err instanceof Error ? err.message : '创建任务失败',
      });
      return null;
    }
  },

  async cancelTask(taskId) {
    try {
      await browserAgentApi.cancelTask(taskId);
      // Status update will arrive via WS; refresh as a fallback.
      await get().refreshDetail();
    } catch (err) {
      set({
        detailError: err instanceof Error ? err.message : '取消任务失败',
      });
    }
  },

  async takeoverTask(taskId, reason) {
    try {
      await browserAgentApi.takeoverTask(taskId, reason);
      // The transition to awaiting_user arrives via WS; no need to refresh here.
    } catch (err) {
      set({
        detailError: err instanceof Error ? err.message : '接管失败',
      });
    }
  },

  async resumeTask(taskId) {
    try {
      await browserAgentApi.resumeTask(taskId);
    } catch (err) {
      set({
        detailError: err instanceof Error ? err.message : '恢复 AI 失败',
      });
    }
  },

  async intervene(taskId, action, args) {
    try {
      await browserAgentApi.intervene(taskId, action, args);
      return true;
    } catch (err) {
      set({
        detailError: err instanceof Error ? err.message : '操作失败',
      });
      return false;
    }
  },
}));

/** Selector: pick the screenshot artifact tied to a given step (if any). */
export function selectScreenshotForStep(
  detail: BrowserTaskDetailResponse | null,
  stepIndex: number | null,
): BrowserArtifact | null {
  if (!detail || stepIndex == null) return null;
  return (
    detail.artifacts.find(
      (a) => a.step_index === stepIndex && a.kind === 'screenshot',
    ) ?? null
  );
}

/** Selector: latest screenshot in chronological order (for live panel). */
export function selectLatestScreenshot(
  detail: BrowserTaskDetailResponse | null,
): BrowserArtifact | null {
  if (!detail) return null;
  for (let i = detail.artifacts.length - 1; i >= 0; i--) {
    if (detail.artifacts[i].kind === 'screenshot') return detail.artifacts[i];
  }
  return null;
}

export { FINAL_STATUSES };
