import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../services/api';
import type { UploadProgress } from '../../types';
import type { KnowledgeBase } from '../../types/knowledge';
import { KnowledgeMenu } from './KnowledgeMenu';
import { ContextGaugeRing } from './ContextGaugeRing';
import { hasFileTransfer } from './inputAreaDrag';
import { SlashCommandMenu, type SlashCommandOption } from './SlashCommandMenu';
import './inputArea.css';

export type { SlashCommandOption } from './SlashCommandMenu';

export interface DraftAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
}

export interface ComposerModelOption {
  id: string;
  label: string;
  configured: boolean;
}

export interface ComposerReasoningOption {
  value: string;
  label: string;
}

export interface ComposerKnowledgeOption {
  id: string;
  name: string;
  description?: string;
}

interface InputAreaProps {
  onSend: (message: string) => void | Promise<void>;
  onStop?: () => void;
  /** Generic disable hatch (e.g. parent wants the entire composer dark). */
  disabled?: boolean;
  /** WebSocket is not OPEN. Lets the user keep typing/dropping files but
   * prevents send (the message would be lost). The reconnect banner is
   * rendered by the parent above the composer. */
  connectionDown?: boolean;
  isStreaming?: boolean;
  isUploading?: boolean;
  value: string;
  onChange: (value: string) => void;
  focusSignal?: number;
  attachments?: DraftAttachment[];
  uploadProgress?: UploadProgress | null;
  onSelectFiles?: (files: FileList) => void;
  onRemoveAttachment?: (id: string) => void;
  composerMode?: 'launch' | 'active';
  modelOptions?: ComposerModelOption[];
  activeModelId?: string | null;
  modelStatus?: 'idle' | 'loading' | 'ready' | 'error';
  onSelectModel?: (providerId: string) => void;
  reasoningOptions?: ComposerReasoningOption[];
  activeReasoning?: string | null;
  onSelectReasoning?: (value: string) => void;
  knowledgeOptions?: ComposerKnowledgeOption[];
  linkedKnowledgeBaseIds?: string[];
  onUpdateLinkedKnowledgeBases?: (knowledgeBaseIds: string[]) => void;
  availableWikiKbs?: KnowledgeBase[];
  activeWikiKbId?: string | null;
  onSetActiveWikiKb?: (kbId: string | null) => void;
  externalDragActive?: boolean;
  /**
   * Messages the user typed while the agent was busy. Rendered as chips
   * above the textarea; auto-flushed by the parent once the agent finishes.
   */
  pendingMessages?: ReadonlyArray<{ id: string; content: string }>;
  onCancelPendingMessage?: (id: string) => void;
  /**
   * Promote a pending message to "real-time guidance" — sent immediately
   * to the running agent without spawning a new turn.
   */
  onSendGuidance?: (id: string, content: string) => void;
  /**
   * Available slash commands. When non-empty, typing ``/`` at the very
   * start of the textarea opens a dropdown above the composer. Selecting
   * an option calls ``onSlashCommandSelect`` with the bare command name
   * (no leading slash). Free-form text typed after the command (e.g.
   * ``/skill some text``) is delivered to the second arg on submit.
   */
  slashCommands?: ReadonlyArray<SlashCommandOption>;
  onSlashCommandSelect?: (name: string, args?: string) => void;
  /**
   * Plan-mode toggle. When ``planMode`` is true the icon glows and the
   * agent is forced (via system-prompt constraint) to call ``task_list``
   * before non-trivial multi-step work. ``onTogglePlanMode`` flips the
   * underlying session preference.
   */
  planMode?: boolean;
  onTogglePlanMode?: () => void;
  /** Last LLM call's prompt-token count, for the context-remaining ring. */
  lastPromptTokens?: number | null;
  /** Soft compaction threshold (config-driven), for the context ring. */
  contextThreshold?: number | null;
  /** Clicking the context ring compacts earlier history (same as /compact). */
  onCompactContext?: () => void;
  /** A compaction is already running — disable the ring. */
  compacting?: boolean;
}

interface InlineSelectOption {
  value: string;
  label: string;
}

interface ComposerModelMenuProps {
  modelOptions: InlineSelectOption[];
  activeModelId: string;
  modelPlaceholder: string;
  onSelectModel: (value: string) => void;
  reasoningOptions: InlineSelectOption[];
  activeReasoning: string;
  onSelectReasoning: (value: string) => void;
  disabled?: boolean;
}

function formatFileSize(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / 1024 ** exponent;

  return `${value >= 100 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`;
}

const CheckIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const ChevronIcon: React.FC<{ direction?: 'down' | 'right' }> = ({ direction = 'down' }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    {direction === 'right' ? (
      <polyline points="9 6 15 12 9 18" />
    ) : (
      <polyline points="6 9 12 15 18 9" />
    )}
  </svg>
);

/**
 * Consolidated model selector — a single compact pill (``<model> · <effort>``)
 * that opens one panel containing the active model, an expandable "Effort"
 * section, and an expandable "More models" section. Replaces the previous
 * row of separate inline selects so the composer footer stays uncluttered.
 */
const ComposerModelMenu: React.FC<ComposerModelMenuProps> = ({
  modelOptions,
  activeModelId,
  modelPlaceholder,
  onSelectModel,
  reasoningOptions,
  activeReasoning,
  onSelectReasoning,
  disabled = false,
}) => {
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<'effort' | 'models' | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const activeModelLabel =
    modelOptions.find((option) => option.value === activeModelId)?.label || modelPlaceholder;
  const otherModels = modelOptions.filter((option) => option.value !== activeModelId);
  const activeEffortLabel = reasoningOptions.find(
    (option) => option.value === activeReasoning,
  )?.label;

  useEffect(() => {
    if (!open) {
      setSection(null);
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  return (
    <div className="composer__model-menu" ref={rootRef}>
      <button
        type="button"
        className="composer__inline-trigger composer__model-trigger"
        disabled={disabled}
        onClick={() => setOpen((state) => !state)}
        aria-expanded={open}
      >
        <span className="composer__model-name">{activeModelLabel}</span>
        {activeEffortLabel ? (
          <span className="composer__model-effort">{activeEffortLabel}</span>
        ) : null}
        <ChevronIcon />
      </button>

      {open ? (
        <div className="composer__model-popover">
          <div className="composer__model-panel">
            <button
              type="button"
              className="composer__inline-option is-selected"
              onClick={() => setOpen(false)}
            >
              <span>{activeModelLabel}</span>
              <CheckIcon />
            </button>

            {reasoningOptions.length > 0 ? (
              <button
                type="button"
                className={`composer__model-section ${section === 'effort' ? 'is-open' : ''}`}
                onClick={() => setSection((s) => (s === 'effort' ? null : 'effort'))}
                aria-expanded={section === 'effort'}
              >
                <span>Effort</span>
                <span className="composer__model-section-value">
                  {activeEffortLabel || '关闭'}
                  <ChevronIcon direction="right" />
                </span>
              </button>
            ) : null}

            {otherModels.length > 0 ? (
              <button
                type="button"
                className={`composer__model-section ${section === 'models' ? 'is-open' : ''}`}
                onClick={() => setSection((s) => (s === 'models' ? null : 'models'))}
                aria-expanded={section === 'models'}
              >
                <span>More models</span>
                <ChevronIcon direction="right" />
              </button>
            ) : null}
          </div>

          {section === 'effort' && reasoningOptions.length > 0 ? (
            <div className="composer__model-flyout">
              {reasoningOptions.map((option) => {
                const selected = option.value === activeReasoning;
                return (
                  <button
                    key={option.value || 'off'}
                    type="button"
                    className={`composer__inline-option composer__model-suboption ${selected ? 'is-selected' : ''}`}
                    onClick={() => {
                      onSelectReasoning(option.value);
                      setOpen(false);
                    }}
                  >
                    <span>{option.label}</span>
                    {selected ? <CheckIcon /> : null}
                  </button>
                );
              })}
            </div>
          ) : null}

          {section === 'models' && otherModels.length > 0 ? (
            <div className="composer__model-flyout">
              {otherModels.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="composer__inline-option composer__model-suboption"
                  onClick={() => {
                    onSelectModel(option.value);
                    setOpen(false);
                  }}
                >
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export const InputArea: React.FC<InputAreaProps> = ({
  onSend,
  onStop,
  disabled,
  connectionDown,
  isStreaming,
  isUploading,
  value,
  onChange,
  focusSignal,
  attachments = [],
  uploadProgress,
  onSelectFiles,
  onRemoveAttachment,
  composerMode = 'active',
  modelOptions = [],
  activeModelId,
  modelStatus = 'idle',
  onSelectModel,
  reasoningOptions = [],
  activeReasoning,
  onSelectReasoning,
  knowledgeOptions = [],
  linkedKnowledgeBaseIds = [],
  onUpdateLinkedKnowledgeBases,
  availableWikiKbs = [],
  activeWikiKbId = null,
  onSetActiveWikiKb,
  externalDragActive = false,
  pendingMessages = [],
  onCancelPendingMessage,
  onSendGuidance,
  slashCommands = [],
  onSlashCommandSelect,
  planMode = false,
  onTogglePlanMode,
  lastPromptTokens = null,
  contextThreshold = null,
  onCompactContext,
  compacting = false,
}) => {
  // Pending list collapses by default once it would dominate the screen.
  const [pendingExpanded, setPendingExpanded] = useState(false);
  useEffect(() => {
    // When the queue empties, reset to collapsed so it expands fresh next time.
    if (pendingMessages.length === 0) setPendingExpanded(false);
  }, [pendingMessages.length]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);

  // ── Voice input (mic → faster-whisper → composer text) ────────────────
  const [voiceState, setVoiceState] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  onChangeRef.current = onChange;
  valueRef.current = value;

  const stopAudioStream = () => {
    audioStreamRef.current?.getTracks().forEach((track) => track.stop());
    audioStreamRef.current = null;
  };

  // Tear down any live recording if the composer unmounts mid-capture.
  useEffect(() => {
    return () => {
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        // already stopped
      }
      stopAudioStream();
    };
  }, []);

  const appendTranscript = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const current = valueRef.current;
    const needsSpace = current.length > 0 && !/\s$/.test(current);
    onChangeRef.current(`${current}${needsSpace ? ' ' : ''}${trimmed}`);
  };

  const startRecording = async () => {
    setVoiceError(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setVoiceError('当前浏览器不支持录音');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stopAudioStream();
        const chunks = audioChunksRef.current;
        audioChunksRef.current = [];
        if (chunks.length === 0) {
          setVoiceState('idle');
          return;
        }
        const mime = recorder.mimeType || 'audio/webm';
        const blob = new Blob(chunks, { type: mime });
        const ext = mime.includes('ogg') ? 'ogg' : mime.includes('mp4') ? 'mp4' : 'webm';
        setVoiceState('transcribing');
        try {
          const text = await api.transcribeAudio(blob, `voice.${ext}`);
          appendTranscript(text);
          if (!text.trim()) setVoiceError('没有识别到语音');
        } catch (err) {
          setVoiceError(err instanceof Error ? err.message : '语音转写失败');
        } finally {
          setVoiceState('idle');
        }
      };
      recorder.start();
      setVoiceState('recording');
    } catch {
      stopAudioStream();
      setVoiceState('idle');
      setVoiceError('无法访问麦克风，请检查权限');
    }
  };

  const stopRecording = () => {
    try {
      mediaRecorderRef.current?.stop();
    } catch {
      stopAudioStream();
      setVoiceState('idle');
    }
  };

  const toggleRecording = () => {
    if (voiceState === 'recording') {
      stopRecording();
    } else if (voiceState === 'idle') {
      void startRecording();
    }
  };
  // Connection-down keeps the textarea fully usable (so the user isn't
  // trapped while we silently reconnect) but blocks send — sending would
  // drop the message because the WS isn't OPEN.
  const canSubmit =
    (!!value.trim() || attachments.length > 0) &&
    !disabled &&
    !connectionDown &&
    !isUploading;
  const [isDragActive, setIsDragActive] = useState(false);
  const effectiveDragActive = isDragActive || externalDragActive;
  const showLocalDropIndicator = isDragActive && !externalDragActive;

  const availableModels = useMemo(
    () => modelOptions.filter((option) => option.configured || option.id === activeModelId),
    [activeModelId, modelOptions]
  );

  const modelSelectOptions = useMemo<InlineSelectOption[]>(
    () => availableModels.map((option) => ({ value: option.id, label: option.label })),
    [availableModels]
  );

  const reasoningSelectOptions = useMemo<InlineSelectOption[]>(
    () => reasoningOptions.map((option) => ({ value: option.value, label: option.label })),
    [reasoningOptions]
  );

  const modelPlaceholder =
    modelStatus === 'loading'
      ? '正在读取模型...'
      : availableModels.length === 0
        ? '未配置模型'
        : '选择模型';

  // ── Slash-command menu ────────────────────────────────────────────────
  // Open the menu only when the textarea starts with "/" and the user
  // hasn't typed a space or newline yet — exactly the moment when the
  // dropdown can still resolve to a single command. Pure derived state
  // (no extra flag), so it auto-closes the instant the predicate breaks.
  const slashOpen =
    slashCommands.length > 0 &&
    value.startsWith('/') &&
    !value.includes(' ') &&
    !value.includes('\n');
  const slashQuery = slashOpen ? value.slice(1).toLowerCase() : '';
  const slashMatches = useMemo<SlashCommandOption[]>(() => {
    if (!slashOpen) return [];
    if (!slashQuery) return [...slashCommands];
    return slashCommands.filter((c) => c.name.toLowerCase().includes(slashQuery));
  }, [slashOpen, slashQuery, slashCommands]);
  const [slashIndex, setSlashIndex] = useState(0);
  useEffect(() => {
    // Reset the highlight whenever the visible match-set shifts so the
    // selection never points past the end of the list.
    setSlashIndex(0);
  }, [slashQuery, slashMatches.length]);

  const dispatchSlashCommand = (option: SlashCommandOption, args: string = '') => {
    onSlashCommandSelect?.(option.name, args);
    onChange('');
  };

  // Recognise ``/<name>`` or ``/<name> <args...>`` typed by hand —
  // the dropdown auto-closes once a space appears, but the user may
  // still want to fire the command. We only intercept names that are
  // actually registered (otherwise random text starting with "/" would
  // be eaten).
  const tryDispatchTypedSlash = (raw: string): boolean => {
    if (!slashCommands.length) return false;
    const match = raw.match(/^\/([\w\-:]+)(?:\s+([\s\S]+))?$/);
    if (!match) return false;
    const [, name, args] = match;
    const cmd = slashCommands.find((c) => c.name.toLowerCase() === name.toLowerCase());
    if (!cmd) return false;
    onSlashCommandSelect?.(cmd.name, args ?? '');
    onChange('');
    return true;
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed && tryDispatchTypedSlash(trimmed)) {
      return;
    }
    if (canSubmit) {
      void onSend(trimmed);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (slashOpen && slashMatches.length > 0) {
      if (event.nativeEvent.isComposing) {
        // IME composition (Chinese pinyin etc.) — let it through.
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onChange('');
        return;
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSlashIndex((i) => Math.min(slashMatches.length - 1, i + 1));
        return;
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSlashIndex((i) => Math.max(0, i - 1));
        return;
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        const cmd = slashMatches[Math.min(slashIndex, slashMatches.length - 1)];
        if (cmd) dispatchSlashCommand(cmd);
        return;
      }
    }
    if (event.key !== 'Enter') return;
    if (event.nativeEvent.isComposing) return;
    if (event.shiftKey) return;
    event.preventDefault();
    handleSubmit(event);
  };

  useEffect(() => {
    if (!textareaRef.current) {
      return;
    }

    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
  }, [value]);

  useEffect(() => {
    if (!textareaRef.current || focusSignal === undefined) {
      return;
    }

    textareaRef.current.focus();
    const length = textareaRef.current.value.length;
    textareaRef.current.setSelectionRange(length, length);
  }, [focusSignal]);

  const resetDragState = () => {
    dragDepthRef.current = 0;
    setIsDragActive(false);
  };

  const handleDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    if (disabled || isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current += 1;
    setIsDragActive(true);
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (disabled || isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
    if (!isDragActive) {
      setIsDragActive(true);
    }
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    if (!hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    if (disabled || isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const files = event.dataTransfer?.files;
    resetDragState();
    if (files && files.length > 0) {
      onSelectFiles?.(files);
    }
  };

  return (
    <form
      className={`composer composer--${composerMode} ${isUploading ? 'is-uploading' : ''}`}
      onSubmit={handleSubmit}
    >
      {pendingMessages.length > 0 ? (
        <div className="composer__pending" aria-label="待发送消息队列">
          <button
            type="button"
            className="composer__pending-head"
            onClick={() => setPendingExpanded((value) => !value)}
            aria-expanded={pendingExpanded}
          >
            <span className="composer__pending-head-label">
              <span>待发送 {pendingMessages.length} 条</span>
              <span className="composer__pending-hint">
                {pendingExpanded ? '点击收起' : '当前任务结束后会自动发出'}
              </span>
            </span>
            <span className={`composer__pending-caret ${pendingExpanded ? 'is-open' : ''}`}>▾</span>
          </button>
          {pendingExpanded ? (
            <ul className="composer__pending-list" role="list">
              {pendingMessages.map((item) => (
                <li className="composer__pending-item" role="listitem" key={item.id}>
                  <span className="composer__pending-text" title={item.content}>
                    {item.content}
                  </span>
                  {onSendGuidance && isStreaming ? (
                    <button
                      type="button"
                      className="composer__pending-guide"
                      onClick={() => onSendGuidance(item.id, item.content)}
                      aria-label="作为实时引导发送给 AI"
                      title="作为实时引导发送 — 不打断当前任务，AI 下一步会看到"
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M9 18h6" />
                        <path d="M10 22h4" />
                        <path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.2 1 2v1.3h6v-1.3c0-.8.4-1.5 1-2A7 7 0 0 0 12 2z" />
                      </svg>
                    </button>
                  ) : null}
                  {onCancelPendingMessage ? (
                    <button
                      type="button"
                      className="composer__pending-cancel"
                      onClick={() => onCancelPendingMessage(item.id)}
                      aria-label="撤销这条排队消息"
                      title="撤销"
                    >
                      ×
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {attachments.length > 0 ? (
        <div className="composer__attachments">
          <div className="composer__attachment-list">
            {attachments.map((attachment) => (
              <div className="composer__attachment" key={attachment.id}>
                <span className="composer__attachment-name">{attachment.name}</span>
                <span className="composer__attachment-size">{formatFileSize(attachment.size)}</span>
                <button
                  type="button"
                  disabled={!!isUploading}
                  onClick={() => onRemoveAttachment?.(attachment.id)}
                  className="composer__attachment-remove"
                  aria-label={`移除 ${attachment.name}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          {isUploading && uploadProgress ? (
            <div className="composer__upload">
              <div className="composer__upload-meta">
                <span>
                  正在上传 {attachments.length} 个文件 · {formatFileSize(uploadProgress.loaded)} /{' '}
                  {formatFileSize(uploadProgress.total)}
                </span>
                <strong>{uploadProgress.percent}%</strong>
              </div>
              <div className="composer__upload-track">
                <div
                  className="composer__upload-fill"
                  style={{ width: `${uploadProgress.percent}%` }}
                />
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {slashOpen && slashMatches.length > 0 ? (
        <SlashCommandMenu
          options={slashMatches}
          selectedIndex={Math.min(slashIndex, slashMatches.length - 1)}
          onHover={setSlashIndex}
          onSelect={dispatchSlashCommand}
        />
      ) : null}

      <div
        className={`composer__surface ${effectiveDragActive ? 'is-drag-active' : ''}`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {showLocalDropIndicator ? (
          <div className="composer__drop-indicator" aria-hidden="true">
            <strong>松开以上传文件</strong>
            <span>文件会直接加入当前输入框附件区</span>
          </div>
        ) : null}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.ppt,.pptx,.xls,.xlsx,.csv,.md,.markdown,.txt,.json,.yaml,.yml,.xml,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg"
          className="composer__file-input"
          onChange={(event) => {
            if (event.target.files && event.target.files.length > 0) {
              onSelectFiles?.(event.target.files);
              event.target.value = '';
            }
          }}
        />

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isUploading
              ? '正在上传文件...'
              : composerMode === 'launch'
                ? '想让 TokenMind 帮你处理什么？'
                : '继续和 TokenMind 对话'
          }
          disabled={!!disabled || !!isUploading}
          rows={1}
          className="composer__textarea"
        />

        {voiceState === 'recording' ? (
          <div className="composer__voice-status" role="status">
            <span className="composer__voice-dot" /> 正在录音 · 点击麦克风结束并转写
          </div>
        ) : voiceState === 'transcribing' ? (
          <div className="composer__voice-status" role="status">
            正在转写语音…
          </div>
        ) : voiceError ? (
          <div className="composer__voice-status composer__voice-status--error" role="alert">
            {voiceError}
          </div>
        ) : null}

        <div className="composer__footer">
          <div className="composer__footer-left">
            <button
              type="button"
              disabled={!!disabled || !!isUploading}
              onClick={() => fileInputRef.current?.click()}
              className="composer__icon-button"
              aria-label="上传文件"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 5v14" />
                <path d="M5 12h14" />
              </svg>
            </button>

            <KnowledgeMenu
              ragOptions={knowledgeOptions}
              linkedRagIds={linkedKnowledgeBaseIds}
              onUpdateLinkedRag={(ids) => onUpdateLinkedKnowledgeBases?.(ids)}
              wikiOptions={availableWikiKbs}
              activeWikiId={activeWikiKbId}
              onSetActiveWiki={(id) => onSetActiveWikiKb?.(id)}
              disabled={!!disabled || !!isUploading}
            />

            <ContextGaugeRing
              lastPromptTokens={lastPromptTokens}
              threshold={contextThreshold}
              onCompact={onCompactContext}
              busy={compacting}
            />
          </div>

          <div className="composer__footer-right">
            {/* Plan-mode stays a standalone icon (not in the reference image
                but kept on request) — labeled chip so new users recognise it. */}
            {onTogglePlanMode ? (
              <button
                type="button"
                disabled={!!disabled || !!isUploading}
                onClick={onTogglePlanMode}
                aria-pressed={planMode}
                aria-label={planMode ? '关闭计划模式' : '开启计划模式'}
                title={
                  planMode
                    ? '计划模式开启 — Agent 会先列任务再执行（点击关闭）'
                    : '开启计划模式 — Agent 会在多步任务前先列出 task_list'
                }
                className={`composer__chip-button composer__plan-toggle ${planMode ? 'is-active' : ''}`}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="4" y="5" width="16" height="14" rx="2" />
                  <path d="M8 9h8" />
                  <path d="M8 13h5" />
                  <path d="M8 17h3" />
                </svg>
                <span>计划{planMode ? ' · 开' : ''}</span>
              </button>
            ) : null}

            {/* Single consolidated model pill: model · effort, with a
                side flyout for Effort / More models. */}
            <ComposerModelMenu
              modelOptions={modelSelectOptions}
              activeModelId={activeModelId || ''}
              modelPlaceholder={modelPlaceholder}
              onSelectModel={(next) => onSelectModel?.(next)}
              reasoningOptions={reasoningSelectOptions}
              activeReasoning={activeReasoning || ''}
              onSelectReasoning={(next) => onSelectReasoning?.(next)}
              disabled={modelStatus === 'loading' || modelSelectOptions.length === 0}
            />

            <button
              type="button"
              disabled={!!disabled || !!isUploading || voiceState === 'transcribing'}
              onClick={toggleRecording}
              className={`composer__icon-button composer__mic composer__mic--${voiceState}`}
              aria-label={
                voiceState === 'recording'
                  ? '停止录音并转写'
                  : voiceState === 'transcribing'
                    ? '正在转写语音'
                    : '语音输入'
              }
              aria-pressed={voiceState === 'recording'}
              title={
                voiceState === 'recording'
                  ? '点击停止并转写为文字'
                  : voiceState === 'transcribing'
                    ? '正在转写…'
                    : '语音输入 — 说话自动转成文字'
              }
            >
              {voiceState === 'transcribing' ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="composer__mic-spinner">
                  <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0" strokeLinecap="round" />
                  <path d="M12 18v3" strokeLinecap="round" />
                </svg>
              )}
            </button>

            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                disabled={!onStop}
                className="composer__submit composer__submit--stop is-ready"
                aria-label="停止生成"
                title="停止当前任务"
              >
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <rect x="7" y="7" width="10" height="10" rx="2.2" />
                </svg>
              </button>
            ) : null}
            <button
              type="submit"
              disabled={!canSubmit}
              className={`composer__submit ${canSubmit ? 'is-ready' : ''}`}
              aria-label={isStreaming ? '加入待发送队列' : '发送消息'}
              title={
                isStreaming
                  ? '任务进行中 — 发送后将排队，等当前任务结束后自动发出'
                  : '发送消息'
              }
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </form>
  );
};
