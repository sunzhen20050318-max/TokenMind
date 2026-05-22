import React, { memo, useEffect, useRef, useState } from 'react';
import type { TimelineEvent, ToolCall } from '../../stores/chatStore';

interface ToolChainProps {
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  isActive?: boolean;
  isDone?: boolean;
  activeToolName?: string;
  displayCount?: number;
  variant?: 'standalone' | 'embedded';
}

function getEventLabel(event: TimelineEvent): string {
  if (event.type === 'reasoning') {
    const len = (event.content || '').length;
    return len > 0 ? `💭 思考过程 · ${len} 字` : '💭 思考过程';
  }
  if (event.type === 'file_edit_progress' && event.fileEdit) {
    const icon = event.fileEdit.tool === 'write_file' ? '📝' : '✏️';
    return `${icon} ${event.fileEdit.path || event.content || '...'}`;
  }
  if (event.content && event.content.trim()) {
    return event.content;
  }
  return event.toolName || '工具事件';
}

function getEventDetail(event: TimelineEvent): string {
  if (event.type === 'file_edit_progress' && event.fileEdit) {
    const { phase, status, added, deleted, approximate, error } = event.fileEdit;
    if (phase === 'error') {
      return error ? `失败：${error.slice(0, 120)}` : '失败';
    }
    if (status === 'done') {
      return `完成 · +${added} −${deleted} 行`;
    }
    const prefix = approximate ? '正在写入 (估算)' : '正在写入';
    return `${prefix} · +${added} −${deleted} 行`;
  }
  if (event.detail) {
    return event.detail;
  }
  if (event.type === 'reasoning') {
    return '模型思考';
  }
  if (event.type === 'progress') {
    return '进度更新';
  }
  if (event.type === 'tool_start') {
    return '工具启动';
  }
  if (event.type === 'tool_error') {
    return '执行被阻止或失败';
  }
  return '工具完成';
}

function fileEditDotColor(event: TimelineEvent): string | null {
  if (event.type !== 'file_edit_progress' || !event.fileEdit) return null;
  if (event.fileEdit.phase === 'error') return '#ef4444';
  if (event.fileEdit.status === 'done') return '#34c759';
  return '#0a84ff';  // editing in progress
}

export const ToolChain: React.FC<ToolChainProps> = memo(
  ({
    toolCalls,
    timelineEvents,
    isActive = false,
    isDone = false,
    activeToolName,
    displayCount,
    variant = 'standalone',
  }) => {
    // Default expanded only for tool chains that are still running. Historical
    // chains (loaded from session history) start collapsed so the chat does
    // not overflow with old Exec details.
    const [isExpanded, setIsExpanded] = useState(isActive);
    const [now, setNow] = useState(() => Date.now());
    // Per-row "show full reasoning" toggle so a long DeepSeek-R1 monologue
    // doesn't bloat the chain by default — user clicks to peek.
    const [openReasonings, setOpenReasonings] = useState<Set<string>>(() => new Set());
    const toggleReasoning = (eventId: string) => {
      setOpenReasonings((prev) => {
        const next = new Set(prev);
        if (next.has(eventId)) next.delete(eventId);
        else next.add(eventId);
        return next;
      });
    };

    // When a tool chain transitions from idle → active (a fresh answer kicks off
    // Exec after the component is already mounted), auto-expand so the user can
    // follow the live execution without needing to click.
    const wasActiveRef = useRef<boolean>(isActive);
    useEffect(() => {
      if (isActive && !wasActiveRef.current) {
        setIsExpanded(true);
      }
      wasActiveRef.current = isActive;
    }, [isActive]);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const hasRunning = toolCalls.some((toolCall) => toolCall.status === 'running');
    const hasErrors =
      toolCalls.some((toolCall) => toolCall.status === 'error') ||
      timelineEvents.some((event) => event.type === 'tool_error');

    useEffect(() => {
      if (hasRunning || isActive) {
        intervalRef.current = setInterval(() => {
          setNow(Date.now());
        }, 100);
      } else if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
        }
      };
    }, [hasRunning, isActive]);

    const totalDuration = toolCalls.reduce((acc, toolCall) => {
      if (toolCall.duration !== undefined) {
        return acc + toolCall.duration;
      }
      return acc;
    }, 0);

    const overallElapsed = (() => {
      if (toolCalls.length === 0) return 0;
      const firstTool = toolCalls[0];
      const startTime = new Date(firstTool.timestamp).getTime();
      return Math.round((now - startTime) / 1000);
    })();

    const displayDuration = hasRunning ? overallElapsed : totalDuration;

    const formatTime = (seconds: number) => {
      if (seconds < 1) return '<1s';
      if (seconds < 60) return `${seconds}s`;
      return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    };

    const getTitle = () => {
      const count = displayCount !== undefined ? displayCount : toolCalls.length;
      return count > 0 ? `Exec (${count})` : 'Exec';
    };

    const getStatusText = () => {
      if (hasRunning && activeToolName) {
        return `正在运行 ${activeToolName}`;
      }
      if (hasErrors) {
        return '有步骤被阻止或执行失败';
      }
      if (!isDone) {
        return '等待最终回复';
      }
      const count = displayCount !== undefined ? displayCount : toolCalls.length;
      return count > 0 ? `共完成 ${count} 个步骤` : '暂无工具活动';
    };

    const formatEventTime = (value: string) =>
      new Date(value).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });

    return (
      <div
        style={{
          width: variant === 'embedded' ? '100%' : 'min(calc(100% - 30px), 856px)',
          margin: variant === 'embedded' ? '0' : '2px 0 8px',
          marginLeft: variant === 'embedded' ? '0' : '30px',
          padding: 0,
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            backgroundColor: variant === 'embedded' ? '#17181b' : '#141416',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '14px',
            overflow: 'hidden',
          }}
        >
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '9px',
              padding: '8px 14px',
              backgroundColor: 'transparent',
              border: 'none',
              cursor: 'pointer',
              width: '100%',
              textAlign: 'left',
              transition: 'background-color 0.15s ease',
            }}
            onMouseOver={(event) => {
              event.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)';
            }}
            onMouseOut={(event) => {
              event.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#666"
              strokeWidth="2"
              style={{
                transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s ease',
              }}
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>

            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="1.5">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>

            <span
              style={{
                fontSize: '12px',
                color: '#ddd',
                fontFamily: 'ui-monospace, monospace',
                flex: 1,
              }}
            >
              {getTitle()}
            </span>

            {hasRunning || !isDone ? (
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#888"
                strokeWidth="2"
                style={{ animation: 'tool-chain-spin 1s linear infinite' }}
              >
                <circle cx="12" cy="12" r="10" strokeDasharray="31.4" strokeDashoffset="10" />
              </svg>
            ) : hasErrors ? (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v5" />
                <circle cx="12" cy="16.5" r="0.75" fill="#ef4444" stroke="none" />
              </svg>
            ) : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34c759" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}

            <span
              style={{
                fontSize: '11px',
                color: '#666',
                fontFamily: 'ui-monospace, monospace',
              }}
            >
              {displayDuration > 0 ? formatTime(displayDuration) : ''}
            </span>
          </button>

          <div
            style={{
              maxHeight: isExpanded ? '420px' : '0',
              overflowY: 'auto',
              transition: 'max-height 0.25s ease-out',
            }}
          >
            <div style={{ padding: '0 14px 12px' }}>
              <div style={{ fontSize: '11px', color: '#6f6f74', marginBottom: timelineEvents.length > 0 ? '10px' : 0 }}>
                {getStatusText()}
              </div>

              {timelineEvents.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '9px' }}>
                  {timelineEvents.map((event, index) => {
                    const isReasoning = event.type === 'reasoning';
                    const expanded = isReasoning && openReasonings.has(event.id);
                    return (
                    <div
                      key={event.id}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '20px 1fr auto',
                        gap: '10px',
                        alignItems: 'start',
                      }}
                    >
                      <div
                        style={{
                          position: 'relative',
                          display: 'flex',
                          justifyContent: 'center',
                          alignSelf: 'stretch',
                        }}
                      >
                        {index < timelineEvents.length - 1 ? (
                          <span
                            style={{
                              position: 'absolute',
                              top: '10px',
                              bottom: '-9px',
                              width: '1px',
                              backgroundColor: '#2a2a2d',
                            }}
                          />
                        ) : null}

                        <span
                          style={{
                            position: 'relative',
                            zIndex: 1,
                            marginTop: '3px',
                            width: '7px',
                            height: '7px',
                            borderRadius: '50%',
                            backgroundColor:
                              fileEditDotColor(event) ||
                              (event.type === 'tool_end'
                                ? '#34c759'
                                : event.type === 'tool_error'
                                  ? '#ef4444'
                                  : event.type === 'tool_start'
                                    ? '#f59e0b'
                                    : event.type === 'reasoning'
                                      ? '#8b85d6'
                                      : '#5f5f65'),
                          }}
                        />
                      </div>

                      <div>
                        <div
                          style={{
                            fontSize: '13px',
                            color: '#e8e8eb',
                            lineHeight: 1.42,
                            cursor: isReasoning ? 'pointer' : 'default',
                          }}
                          onClick={isReasoning ? () => toggleReasoning(event.id) : undefined}
                          title={isReasoning ? '点击查看 / 收起完整思考' : undefined}
                        >
                          {getEventLabel(event)}
                          {isReasoning ? (
                            <span style={{ marginLeft: '6px', color: '#77777e', fontSize: '11px' }}>
                              {expanded ? '收起 ▴' : '展开 ▾'}
                            </span>
                          ) : null}
                        </div>
                        <div style={{ fontSize: '11px', color: '#77777e', marginTop: '2px' }}>
                          {getEventDetail(event)}
                        </div>
                        {isReasoning && expanded ? (
                          <div
                            style={{
                              marginTop: '8px',
                              padding: '10px 12px',
                              background: 'rgba(139, 133, 214, 0.06)',
                              border: '1px solid rgba(139, 133, 214, 0.18)',
                              borderRadius: '8px',
                              fontSize: '12.5px',
                              lineHeight: 1.65,
                              color: '#b8b8c4',
                              fontStyle: 'italic',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              maxHeight: '320px',
                              overflowY: 'auto',
                            }}
                          >
                            {event.content}
                          </div>
                        ) : null}
                      </div>

                      <div style={{ fontSize: '11px', color: '#666', whiteSpace: 'nowrap' }}>
                        {event.duration !== undefined ? `${Math.round(event.duration)}s` : formatEventTime(event.timestamp)}
                      </div>
                    </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <style>{`
          @keyframes tool-chain-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }
);

export const ToolIndicator = ToolChain;

