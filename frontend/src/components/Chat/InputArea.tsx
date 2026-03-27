import React, { useEffect, useRef } from 'react';
import type { UploadProgress } from '../../types';

export interface DraftAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
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
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canSubmit = (value.trim() || attachments.length > 0) && !disabled && !isUploading;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (canSubmit) {
      void onSend(value.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [value]);

  useEffect(() => {
    if (!textareaRef.current || focusSignal === undefined) {
      return;
    }
    textareaRef.current.focus();
    const length = textareaRef.current.value.length;
    textareaRef.current.setSelectionRange(length, length);
  }, [focusSignal]);

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: '12px',
        padding: '16px 24px',
        backgroundColor: '#0a0a0a',
        borderTop: '1px solid #1a1a1a',
        flexWrap: 'wrap',
      }}
    >
      {attachments.length > 0 && (
        <div
          style={{
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            marginBottom: '4px',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '8px',
            }}
          >
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: '999px',
                  backgroundColor: '#151515',
                  border: '1px solid #2a2a2a',
                  color: '#d8d8d8',
                  fontSize: '12px',
                }}
              >
                <span>{attachment.name}</span>
                <span style={{ color: '#7c7c7c' }}>{formatFileSize(attachment.size)}</span>
                <button
                  type="button"
                  disabled={!!isUploading}
                  onClick={() => onRemoveAttachment?.(attachment.id)}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    color: isUploading ? '#5c5c5c' : '#9a9a9a',
                    cursor: isUploading ? 'not-allowed' : 'pointer',
                    padding: 0,
                    lineHeight: 1,
                    fontSize: '14px',
                  }}
                  aria-label={`移除 ${attachment.name}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          {isUploading && uploadProgress && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: '0 2px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                  color: '#8f8f94',
                  fontSize: '12px',
                }}
              >
                <span>
                  正在上传 {attachments.length} 个文件 · {formatFileSize(uploadProgress.loaded)} /{' '}
                  {formatFileSize(uploadProgress.total)}
                </span>
                <span
                  style={{
                    color: '#f5f5f5',
                    fontSize: '13px',
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                  }}
                >
                  {uploadProgress.percent}%
                </span>
              </div>

              <div
                style={{
                  position: 'relative',
                  width: '100%',
                  height: '6px',
                  borderRadius: '999px',
                  backgroundColor: '#171717',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${uploadProgress.percent}%`,
                    height: '100%',
                    borderRadius: 'inherit',
                    background:
                      'linear-gradient(90deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 1))',
                    boxShadow: '0 0 16px rgba(255, 255, 255, 0.18)',
                    transition: 'width 0.14s ease',
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.ppt,.pptx,.xls,.xlsx,.csv,.md,.markdown,.txt,.json,.yaml,.yml,.xml,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            onSelectFiles?.(e.target.files);
            e.target.value = '';
          }
        }}
      />

      <button
        type="button"
        disabled={!!disabled || !!isUploading}
        onClick={() => fileInputRef.current?.click()}
        style={{
          width: '38px',
          height: '38px',
          borderRadius: '12px',
          border: '1px solid #2a2a2a',
          backgroundColor: '#141414',
          color: '#d8d8d8',
          cursor: disabled || isUploading ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
        aria-label="上传文件"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21.44 11.05l-8.49 8.49a5.5 5.5 0 0 1-7.78-7.78l8.49-8.49a3.5 3.5 0 0 1 4.95 4.95l-8.5 8.49a1.5 1.5 0 0 1-2.12-2.12l7.79-7.78" />
        </svg>
      </button>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isUploading ? '正在上传文件...' : '给 SUN-AGENT 发送消息，或附带文件一起提问'}
        disabled={!!disabled || !!isUploading}
        rows={1}
        style={{
          flex: 1,
          padding: '10px 16px',
          borderRadius: '12px',
          border: '1px solid #2a2a2a',
          backgroundColor: '#141414',
          color: '#e5e5e5',
          resize: 'none',
          outline: 'none',
          fontSize: '14px',
          fontFamily: 'inherit',
          maxHeight: '150px',
          transition: 'border-color 0.2s ease',
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = '#444';
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = '#2a2a2a';
        }}
      />

      <button
        type="submit"
        disabled={!canSubmit}
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          border: 'none',
          backgroundColor: canSubmit ? '#fff' : '#2a2a2a',
          color: canSubmit ? '#000' : '#666',
          fontSize: '18px',
          cursor: canSubmit ? 'pointer' : 'not-allowed',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s ease',
          transform: canSubmit ? 'scale(1)' : 'scale(0.95)',
        }}
        onMouseOver={(e) => {
          if (canSubmit) {
            e.currentTarget.style.backgroundColor = '#e5e5e5';
          }
        }}
        onMouseOut={(e) => {
          if (canSubmit) {
            e.currentTarget.style.backgroundColor = '#fff';
          }
        }}
        aria-label="发送消息"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
      </button>

      {isStreaming && (
        <button
          type="button"
          onClick={onStop}
          style={{
            padding: '0 14px',
            height: '36px',
            borderRadius: '999px',
            border: '1px solid #3a3a3a',
            backgroundColor: '#171717',
            color: '#f2f2f2',
            fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          停止
        </button>
      )}
    </form>
  );
};
