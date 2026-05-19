import { create } from 'zustand';

export type ToastLevel = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  level: ToastLevel;
  message: string;
  title?: string;
  duration: number;
  createdAt: number;
}

interface ToastState {
  toasts: ToastItem[];
  pushToast: (
    message: string,
    options?: { level?: ToastLevel; title?: string; duration?: number },
  ) => string;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
}

const DEFAULT_DURATIONS: Record<ToastLevel, number> = {
  info: 3500,
  success: 3000,
  warning: 5000,
  error: 6000,
};

let counter = 0;
const nextId = () => {
  counter += 1;
  return `toast-${Date.now().toString(36)}-${counter}`;
};

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (message, options = {}) => {
    const id = nextId();
    const level: ToastLevel = options.level ?? 'info';
    const duration = options.duration ?? DEFAULT_DURATIONS[level];
    const item: ToastItem = {
      id,
      level,
      message,
      title: options.title,
      duration,
      createdAt: Date.now(),
    };
    set((state) => ({ toasts: [...state.toasts, item] }));
    return id;
  },
  dismissToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },
  clearToasts: () => set({ toasts: [] }),
}));

export const pushToast = (
  message: string,
  options?: { level?: ToastLevel; title?: string; duration?: number },
) => useToastStore.getState().pushToast(message, options);
