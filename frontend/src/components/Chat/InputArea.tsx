import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { UploadProgress } from '../../types';
import { hasFileTransfer } from './inputAreaDrag';
import './inputArea.css';

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
  disabled?: boolean;
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
}

interface InlineSelectOption {
  value: string;
  label: string;
}

interface InlineSelectProps {
  value: string;
  placeholder: string;
  options: InlineSelectOption[];
  onSelect: (value: string) => void;
  disabled?: boolean;
  align?: 'left' | 'right';
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

const InlineSelect: React.FC<InlineSelectProps> = ({
  value,
  placeholder,
  options,
  onSelect,
  disabled = false,
  align = 'right',
}) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const currentLabel = options.find((option) => option.value === value)?.label || placeholder;

  useEffect(() => {
    if (!open) {
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
    <div className="composer__inline-select" ref={rootRef}>
      <button
        type="button"
        className="composer__inline-trigger"
        disabled={disabled}
        onClick={() => setOpen((state) => !state)}
        aria-expanded={open}
      >
        <span>{currentLabel}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open ? (
        <div className={`composer__inline-menu composer__inline-menu--${align}`}>
          {options.map((option) => {
            const selected = option.value === value;
            return (
              <button
                key={option.value || 'empty'}
                type="button"
                className={`composer__inline-option ${selected ? 'is-selected' : ''}`}
                onClick={() => {
                  onSelect(option.value);
                  setOpen(false);
                }}
              >
                <span>{option.label}</span>
                {selected ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

export const InputArea: React.FC<InputAreaProps> = ({
  onSend,
  onStop,
  disabled,
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
  externalDragActive = false,
  pendingMessages = [],
  onCancelPendingMessage,
  onSendGuidance,
}) => {
  // Pending list collapses by default once it would dominate the screen.
  const [pendingExpanded, setPendingExpanded] = useState(false);
  useEffect(() => {
    // When the queue empties, reset to collapsed so it expands fresh next time.
    if (pendingMessages.length === 0) setPendingExpanded(false);
  }, [pendingMessages.length]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const knowledgeRef = useRef<HTMLDivElement>(null);
  const dragDepthRef = useRef(0);
  const canSubmit = (!!value.trim() || attachments.length > 0) && !disabled && !isUploading;
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
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

  const reasoningPlaceholder =
    reasoningSelectOptions.find((option) => option.value === activeReasoning)?.label || '关闭';

  const linkedKnowledgeBases = useMemo(
    () => knowledgeOptions.filter((option) => linkedKnowledgeBaseIds.includes(option.id)),
    [knowledgeOptions, linkedKnowledgeBaseIds]
  );

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (canSubmit) {
      void onSend(value.trim());
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
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

  useEffect(() => {
    if (!knowledgeOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!knowledgeRef.current?.contains(event.target as Node)) {
        setKnowledgeOpen(false);
      }
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [knowledgeOpen]);

  const toggleKnowledgeBase = (knowledgeBaseId: string) => {
    const nextIds = linkedKnowledgeBaseIds.includes(knowledgeBaseId)
      ? linkedKnowledgeBaseIds.filter((id) => id !== knowledgeBaseId)
      : [...linkedKnowledgeBaseIds, knowledgeBaseId];
    onUpdateLinkedKnowledgeBases?.(nextIds);
  };

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

            <div className="composer__knowledge" ref={knowledgeRef}>
              <button
                type="button"
                className={`composer__knowledge-trigger ${knowledgeOpen ? 'is-open' : ''}`}
                onClick={() => setKnowledgeOpen((state) => !state)}
              >
                {linkedKnowledgeBases.length > 0 ? '已链接知识库' : '链接知识库'}
              </button>

              {knowledgeOpen ? (
                <div className="composer__knowledge-menu">
                  <div className="composer__knowledge-menu-head">
                    <strong>选择当前会话要参考的知识库</strong>
                    <span>可多选</span>
                  </div>
                  {knowledgeOptions.length === 0 ? (
                    <div className="composer__knowledge-empty">
                      还没有知识库。先去左侧知识库页面创建一个。
                    </div>
                  ) : (
                    <div className="composer__knowledge-options">
                      {knowledgeOptions.map((item) => {
                        const selected = linkedKnowledgeBaseIds.includes(item.id);
                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={`composer__knowledge-option ${selected ? 'is-selected' : ''}`}
                            onClick={() => toggleKnowledgeBase(item.id)}
                          >
                            <div>
                              <strong>{item.name}</strong>
                              <p>{item.description || '未填写简介'}</p>
                            </div>
                            <span>{selected ? '已链接' : '链接'}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>

          <div className="composer__footer-right">
            {composerMode === 'active' ? (
              <div className="composer__controls">
                <InlineSelect
                  value={activeModelId || ''}
                  placeholder={modelPlaceholder}
                  options={modelSelectOptions}
                  onSelect={(next) => onSelectModel?.(next)}
                  disabled={modelStatus === 'loading' || modelSelectOptions.length === 0}
                />
                <span className="composer__controls-divider" />
                <InlineSelect
                  value={activeReasoning || ''}
                  placeholder={reasoningPlaceholder}
                  options={reasoningSelectOptions}
                  onSelect={(next) => onSelectReasoning?.(next)}
                />
              </div>
            ) : null}

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
