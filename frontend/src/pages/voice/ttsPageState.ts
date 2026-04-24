import type { TtsVoiceOption } from '../../types';

export const TTS_TEXT_LIMIT = 10000;

export interface TtsModelOption {
  value: string;
  label: string;
  description: string;
}

export const TTS_MODELS: TtsModelOption[] = [
  { value: 'speech-2.8-hd', label: 'Speech 2.8 · HD', description: '音质高，延迟稍高' },
  { value: 'speech-2.8-turbo', label: 'Speech 2.8 · Turbo', description: '延迟低，适合实时' },
  { value: 'speech-2.6-hd', label: 'Speech 2.6 · HD', description: '上一代高音质' },
  { value: 'speech-2.6-turbo', label: 'Speech 2.6 · Turbo', description: '上一代低延迟' },
];

export interface EmotionOption {
  value: string;
  label: string;
}

export const EMOTIONS: EmotionOption[] = [
  { value: '', label: '默认情绪' },
  { value: 'calm', label: '平静' },
  { value: 'happy', label: '愉快' },
  { value: 'sad', label: '悲伤' },
  { value: 'angry', label: '愤怒' },
  { value: 'fearful', label: '害怕' },
  { value: 'surprised', label: '惊讶' },
  { value: 'fluent', label: '流畅' },
  { value: 'whisper', label: '耳语' },
];

const MODEL_UNSUPPORTED_EMOTIONS: Record<string, readonly string[]> = {
  'speech-2.8-hd': ['whisper'],
  'speech-2.8-turbo': ['whisper'],
};

export function isTtsEmotionSupported(model: string, emotion: string): boolean {
  if (!emotion) return true;
  const unsupported = MODEL_UNSUPPORTED_EMOTIONS[model.trim().toLowerCase()] ?? [];
  return !unsupported.includes(emotion.trim().toLowerCase());
}

export function getEmotionOptionsForModel(model: string): EmotionOption[] {
  return EMOTIONS.filter((emotion) => isTtsEmotionSupported(model, emotion.value));
}

export interface TtsHistoryItem {
  id: string;
  attachment_id: string;
  voice_id: string;
  voice_label: string;
  model: string;
  text: string;
  usage_characters: number | null;
  created_at: string;
  filename: string;
  mime_type: string;
  trace_id: string | null;
}

const HISTORY_KEY = 'tokenmind:tts-history';

export function loadTtsHistory(
  storage: Pick<Storage, 'getItem'> = window.localStorage,
): TtsHistoryItem[] {
  try {
    const raw = storage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is TtsHistoryItem =>
        entry !== null &&
        typeof entry === 'object' &&
        typeof (entry as TtsHistoryItem).id === 'string' &&
        typeof (entry as TtsHistoryItem).attachment_id === 'string',
    );
  } catch {
    return [];
  }
}

export function saveTtsHistory(
  history: TtsHistoryItem[],
  storage: Pick<Storage, 'setItem'> = window.localStorage,
): void {
  try {
    storage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 50)));
  } catch {
    // Ignore quota errors.
  }
}

export function appendTtsHistory(
  history: TtsHistoryItem[],
  entry: TtsHistoryItem,
): TtsHistoryItem[] {
  const filtered = history.filter((item) => item.id !== entry.id);
  return [entry, ...filtered].slice(0, 50);
}

export function voiceOptionLabel(option: TtsVoiceOption): string {
  if (option.kind === 'system') {
    return `${option.label} · 系统音色`;
  }
  const created = option.created_at
    ? new Date(option.created_at).toLocaleDateString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
      })
    : '';

  if (option.source === 'design') {
    const name = option.display_name?.trim() || '设计音色';
    return created ? `${name} · ${created} 设计` : name;
  }
  const friendly = option.source_filename?.trim() || '我的克隆音色';
  return created ? `${friendly} · ${created} 克隆` : friendly;
}

export function groupVoiceOptions(
  options: TtsVoiceOption[],
): { cloned: TtsVoiceOption[]; system: TtsVoiceOption[] } {
  const cloned: TtsVoiceOption[] = [];
  const system: TtsVoiceOption[] = [];
  for (const option of options) {
    if (option.kind === 'system') {
      system.push(option);
    } else {
      cloned.push(option);
    }
  }
  return { cloned, system };
}

export function makeHistoryId(): string {
  return `tts_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
