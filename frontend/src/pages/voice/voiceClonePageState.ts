export const VOICE_CLONE_MIN_SECONDS = 10;
export const VOICE_CLONE_MAX_SECONDS = 5 * 60;
export const VOICE_CLONE_MAX_BYTES = 20 * 1024 * 1024;
export const VOICE_CLONE_ACCEPT_MIME = ['audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/x-m4a', 'audio/wav', 'audio/wave'];

const VOICE_CLONE_ID_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{7,255}$/;

export interface ValidationError {
  code:
    | 'file_missing'
    | 'file_too_large'
    | 'file_format_unsupported'
    | 'voice_id_invalid'
    | 'preview_too_long';
  message: string;
}

export interface VoiceCloneFormInput {
  file: File | null;
  voiceId: string;
  previewText: string;
  needNoiseReduction: boolean;
  needVolumeNormalization: boolean;
  languageBoost: string;
}

export function isSupportedCloneAudio(file: File | null | undefined): boolean {
  if (!file) {
    return false;
  }
  if (file.size > VOICE_CLONE_MAX_BYTES) {
    return false;
  }
  const mime = (file.type || '').toLowerCase();
  if (mime) {
    // When the browser supplies a MIME type, trust it — reject anything that is
    // not an explicitly allowed audio format.
    return VOICE_CLONE_ACCEPT_MIME.includes(mime);
  }
  // Fall back to extension only when no MIME is reported.
  const name = file.name.toLowerCase();
  return name.endsWith('.mp3') || name.endsWith('.m4a') || name.endsWith('.wav');
}

export function validateVoiceId(voiceId: string): ValidationError | null {
  const trimmed = voiceId.trim();
  if (!trimmed) {
    return null; // empty is allowed → backend auto-generates
  }
  if (!VOICE_CLONE_ID_PATTERN.test(trimmed)) {
    return {
      code: 'voice_id_invalid',
      message: 'voice_id 必须以字母开头，长度 8-256，仅可使用字母、数字、"-" 或 "_"',
    };
  }
  return null;
}

export function validateVoiceCloneForm(input: VoiceCloneFormInput): ValidationError[] {
  const errors: ValidationError[] = [];
  if (!input.file) {
    errors.push({ code: 'file_missing', message: '请先选择要克隆的音频文件' });
  } else {
    if (input.file.size > VOICE_CLONE_MAX_BYTES) {
      errors.push({
        code: 'file_too_large',
        message: `音频文件不能超过 ${VOICE_CLONE_MAX_BYTES / 1024 / 1024} MB`,
      });
    }
    if (!isSupportedCloneAudio(input.file)) {
      errors.push({
        code: 'file_format_unsupported',
        message: '仅支持 MP3、M4A、WAV 格式的音频文件',
      });
    }
  }
  const voiceIdError = validateVoiceId(input.voiceId);
  if (voiceIdError) {
    errors.push(voiceIdError);
  }
  if (input.previewText.length > 1000) {
    errors.push({
      code: 'preview_too_long',
      message: '预览文本不能超过 1000 字',
    });
  }
  return errors;
}

export interface ClonedVoiceRecord {
  voice_id: string;
  model: string;
  provider: string;
  created_at: string;
  demo_audio_url: string | null;
  preview_text: string | null;
  source_filename: string | null;
}

const CLONED_VOICE_STORAGE_KEY = 'tokenmind:voice-clones';

export function loadClonedVoiceHistory(
  storage: Pick<Storage, 'getItem'> = window.localStorage,
): ClonedVoiceRecord[] {
  try {
    const raw = storage.getItem(CLONED_VOICE_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((entry): entry is ClonedVoiceRecord => {
        return (
          entry !== null &&
          typeof entry === 'object' &&
          typeof (entry as ClonedVoiceRecord).voice_id === 'string' &&
          typeof (entry as ClonedVoiceRecord).created_at === 'string'
        );
      })
      .slice(0, 100);
  } catch {
    return [];
  }
}

export function saveClonedVoiceHistory(
  history: ClonedVoiceRecord[],
  storage: Pick<Storage, 'setItem'> = window.localStorage,
): void {
  try {
    storage.setItem(CLONED_VOICE_STORAGE_KEY, JSON.stringify(history.slice(0, 100)));
  } catch {
    // Ignore quota errors; history is best-effort.
  }
}

export function appendClonedVoice(
  history: ClonedVoiceRecord[],
  entry: ClonedVoiceRecord,
): ClonedVoiceRecord[] {
  const filtered = history.filter((item) => item.voice_id !== entry.voice_id);
  return [entry, ...filtered].slice(0, 100);
}

export interface ScenePrompt {
  id: string;
  label: string;
  icon: string;
  script: string;
}

export const SCENE_PROMPTS: ScenePrompt[] = [
  {
    id: 'random',
    label: '随机',
    icon: '🎲',
    script:
      '今天坐公交车上班，刚好有一个靠窗的位子。看着窗外的风景一路过去，街道上的人来来往往，每个人都在忙自己的事。到站了以后下车，觉得坐公交比开车有意思。',
  },
  {
    id: 'audiobook',
    label: '有声读物',
    icon: '📖',
    script:
      '那是一个宁静的午后，阳光透过树叶的缝隙洒在石板路上，斑驳的光影随着微风轻轻摇曳。他坐在长椅上翻开那本泛黄的书，故事的主人公从第一页开始，带着他去往一个未曾想象过的世界。',
  },
  {
    id: 'film',
    label: '影视配音',
    icon: '🎬',
    script:
      '当夜幕降临，整座城市陷入沉睡，只有他一个人还站在屋顶上。他知道真相已经太接近了，下一秒，一切都会改变。但无论如何，他都不会退缩。',
  },
  {
    id: 'vlog',
    label: 'Vlog 独白',
    icon: '🎥',
    script:
      '哈喽大家好，今天我来到了一个超级特别的地方，想跟大家一起分享一下。其实这里我已经念叨了很久，一直想亲自过来看看。走，咱们一起感受一下。',
  },
  {
    id: 'education',
    label: '教育培训',
    icon: '🎓',
    script:
      '同学们好，今天我们要学习的内容非常重要。在正式开始之前，请大家先把课本翻到第二十三页。我们会通过三个案例，来理解这一章里最核心的概念。',
  },
  {
    id: 'podcast',
    label: '电台播客',
    icon: '🎧',
    script:
      '欢迎收听本期节目，我是你的主播。今天我们要聊一个很多人都关心的话题——如何在快节奏的生活里，找到属于自己的那份从容。话不多说，我们开始吧。',
  },
  {
    id: 'cs',
    label: '智能客服',
    icon: '💬',
    script:
      '您好，感谢您的来电，我是您的专属客服助手。请问有什么可以帮您？您可以直接描述遇到的问题，我会立刻为您查询并处理。',
  },
];

export function getScenePrompt(id: string): ScenePrompt {
  return SCENE_PROMPTS.find((item) => item.id === id) ?? SCENE_PROMPTS[0];
}

export interface PreviewLanguageOption {
  value: string;
  label: string;
  defaultText: string;
}

export const PREVIEW_LANGUAGES: PreviewLanguageOption[] = [
  {
    value: 'Chinese',
    label: '中文 - 普通话',
    defaultText: '您好，很高兴能为您提供配音服务。选择您感兴趣的音色，让我们一起开启声音创作的奇妙之旅吧。',
  },
  {
    value: 'English',
    label: 'English',
    defaultText:
      'Hello, thanks for trying our voice cloning service. Pick a voice you like, and let us start creating together.',
  },
  {
    value: 'Japanese',
    label: '日本語',
    defaultText: 'こんにちは、ボイスクローンサービスへようこそ。お気に入りの声を選んで、一緒に声の世界を楽しみましょう。',
  },
];

export const PREVIEW_TEXT_LIMIT = 300;

const RECORD_MIME_CANDIDATES = [
  'audio/mp4',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/webm;codecs=opus',
  'audio/webm',
];

export function pickRecordMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') {
    return null;
  }
  for (const candidate of RECORD_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return null;
}

export function isMiniMaxCompatibleMime(mimeType: string | undefined | null): boolean {
  if (!mimeType) {
    return false;
  }
  const lower = mimeType.toLowerCase();
  return (
    lower.startsWith('audio/mp4') ||
    lower.startsWith('audio/mpeg') ||
    lower.startsWith('audio/mp3') ||
    lower.startsWith('audio/x-m4a') ||
    lower.startsWith('audio/wav') ||
    lower.startsWith('audio/wave')
  );
}

export function extensionForMime(mimeType: string): string {
  const lower = mimeType.toLowerCase();
  if (lower.startsWith('audio/mp4')) return 'm4a';
  if (lower.startsWith('audio/mpeg') || lower.startsWith('audio/mp3')) return 'mp3';
  if (lower.startsWith('audio/wav') || lower.startsWith('audio/wave')) return 'wav';
  if (lower.startsWith('audio/webm')) return 'webm';
  if (lower.startsWith('audio/ogg')) return 'ogg';
  return 'bin';
}

export function makeRecordedFilename(mimeType: string, prefix = 'clone-record'): string {
  const ext = extensionForMime(mimeType);
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return `${prefix}-${timestamp}.${ext}`;
}

export const VOICE_CLONE_INACTIVITY_DAYS = 7;

/** Return days until MiniMax will auto-delete a voice for inactivity. */
export function daysUntilExpiry(record: {
  created_at: string;
  last_kept_alive_at?: string | null;
}, now: Date = new Date()): number {
  const anchor = record.last_kept_alive_at ?? record.created_at;
  const anchorMs = Date.parse(anchor);
  if (!Number.isFinite(anchorMs)) {
    return VOICE_CLONE_INACTIVITY_DAYS;
  }
  const elapsedMs = now.getTime() - anchorMs;
  const elapsedDays = elapsedMs / (1000 * 60 * 60 * 24);
  return Math.max(0, Math.ceil(VOICE_CLONE_INACTIVITY_DAYS - elapsedDays));
}

export function expiryLabel(record: {
  created_at: string;
  last_kept_alive_at?: string | null;
}, now: Date = new Date()): string {
  const remaining = daysUntilExpiry(record, now);
  if (remaining <= 0) {
    return '可能已过期';
  }
  if (remaining === 1) {
    return '剩 1 天';
  }
  return `剩 ${remaining} 天`;
}

export function formatRecordingDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mm = Math.floor(safe / 60)
    .toString()
    .padStart(2, '0');
  const ss = (safe % 60).toString().padStart(2, '0');
  return `${mm}:${ss}`;
}
