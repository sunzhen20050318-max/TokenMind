import { create } from 'zustand';
import { browserAgentApi } from '../services/browserAgent';
import type {
  BrowserAgentEnvCheck,
  BrowserTaskDetailResponse,
  BrowserTaskListItem,
  CreateBrowserTaskRequest,
} from '../types/browserAgent';

/**
 * State for the Web Agent module. Survives across navigation so that a long
 * running browser task keeps progressing while the user is in chat / settings.
 *
 * M1 polls task detail every 2s when a task is selected and is in a non-final
 * state. M2 will replace this with a WebSocket subscription.
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
  detailPollHandle: number | null;

  submitInFlight: boolean;
  submitError: string | null;

  refreshEnvCheck: () => Promise<void>;
  refreshTasks: (params?: { projectId?: string }) => Promise<void>;
  selectTask: (taskId: string | null) => void;
  refreshDetail: () => Promise<void>;
  createTask: (payload: CreateBrowserTaskRequest) => Promise<string | null>;
  cancelTask: (taskId: string) => Promise<void>;
}

const POLL_INTERVAL_MS = 2000;
const FINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);

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
  detailPollHandle: null,

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
    const { detailPollHandle } = get();
    if (detailPollHandle !== null) {
      window.clearInterval(detailPollHandle);
    }

    if (!taskId) {
      set({
        selectedTaskId: null,
        detail: null,
        detailError: null,
        detailLoading: false,
        detailPollHandle: null,
      });
      return;
    }

    set({
      selectedTaskId: taskId,
      detail: null,
      detailError: null,
      detailLoading: true,
      detailPollHandle: null,
    });

    void get().refreshDetail();

    const handle = window.setInterval(() => {
      const state = get();
      if (state.selectedTaskId !== taskId) {
        window.clearInterval(handle);
        return;
      }
      const status = state.detail?.task.status;
      if (status && FINAL_STATUSES.has(status)) {
        window.clearInterval(handle);
        set({ detailPollHandle: null });
        return;
      }
      void get().refreshDetail();
    }, POLL_INTERVAL_MS);

    set({ detailPollHandle: handle });
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
      await get().refreshDetail();
    } catch (err) {
      set({
        detailError: err instanceof Error ? err.message : '取消任务失败',
      });
    }
  },
}));
