import React, { useState, useEffect, useRef, memo } from 'react';
import type { TimelineEvent, ToolCall } from '../../stores/chatStore';

interface ToolChainProps {
  toolCalls: ToolCall[];
  timelineEvents: TimelineEvent[];
  isActive?: boolean;
  isDone?: boolean;  // true when agent response has arrived
  activeToolName?: string;
  displayCount?: number;  // number to display in title (for consistency with filtered list)
}

function getEventLabel(event: TimelineEvent): string {
  if (event.content && event.content.trim()) {
    return event.content;
  }
  return event.toolName || 'Tool event';
}

export const ToolChain: React.FC<ToolChainProps> = memo(({ toolCalls, timelineEvents, isActive = false, isDone = false, activeToolName, displayCount }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasRunning = toolCalls.some(tc => tc.status === 'running');

  // Update current time every 100ms when tools are running
  useEffect(() => {
    if (hasRunning || isActive) {
      intervalRef.current = setInterval(() => {
        setNow(Date.now());
      }, 100);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [hasRunning, isActive]);

  // Total duration = sum of all completed tool durations
  const totalDuration = toolCalls.reduce((acc, tc) => {
    if (tc.duration !== undefined) {
      return acc + tc.duration;
    }
    return acc;
  }, 0);

  // Overall elapsed time (time since first tool started)
  const overallElapsed = (() => {
    if (toolCalls.length === 0) return 0;
    const firstTool = toolCalls[0];
    const startTime = new Date(firstTool.timestamp).getTime();
    return Math.round((now - startTime) / 1000);
  })();

  // Display duration: show elapsed if running, otherwise show total
  const displayDuration = hasRunning ? overallElapsed : totalDuration;

  const formatTime = (seconds: number) => {
    if (seconds < 1) return '<1s';
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  };

  const getTitle = () => {
    if (hasRunning && activeToolName) {
      return 'Execution Timeline';
    }
    const count = displayCount !== undefined ? displayCount : toolCalls.length;
    return count > 0 ? `Execution Timeline (${count})` : 'Execution Timeline';
  };

  const getStatusText = () => {
    if (hasRunning && activeToolName) {
      return `Running ${activeToolName}`;
    }
    if (!isDone) {
      return 'Waiting for final response';
    }
    const count = displayCount !== undefined ? displayCount : toolCalls.length;
    return count > 0 ? `${count} step${count > 1 ? 's' : ''} completed` : 'No tool activity';
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
        marginTop: '8px',
        marginBottom: '8px',
        marginLeft: '52px',
        maxWidth: 'calc(70% - 52px)',
        boxSizing: 'border-box',
      }}
    >
      {/* Main Container */}
      <div
        style={{
          backgroundColor: '#141414',
          border: '1px solid #2a2a2a',
          borderRadius: '10px',
          overflow: 'hidden',
        }}
      >
        {/* Header - clickable */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '10px 14px',
            backgroundColor: 'transparent',
            border: 'none',
            cursor: 'pointer',
            width: '100%',
            textAlign: 'left',
            transition: 'background-color 0.15s ease',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.backgroundColor = '#1a1a1a';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
        >
          {/* Expand/Collapse Icon */}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2"
            style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}>
            <polyline points="9 18 15 12 9 6" />
          </svg>

          {/* Chain Icon */}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="1.5">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg>

          {/* Title */}
          <span style={{
            fontSize: '13px',
            color: '#ccc',
            fontFamily: 'ui-monospace, monospace',
            flex: 1,
          }}>
            {getTitle()}
          </span>

          {/* Status Icon - show spinner when running or waiting for response, checkmark only when done */}
          {hasRunning || !isDone ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="2" style={{ animation: 'spin 1s linear infinite' }}>
              <circle cx="12" cy="12" r="10" strokeDasharray="31.4" strokeDashoffset="10" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#34c759" strokeWidth="2">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}

          {/* Total Duration */}
          <span style={{
            fontSize: '12px',
            color: '#555',
            fontFamily: 'ui-monospace, monospace',
          }}>
            {displayDuration > 0 ? formatTime(displayDuration) : ''}
          </span>
        </button>

        {/* Tool List */}
        <div
          style={{
            maxHeight: isExpanded ? '400px' : '0',
            overflowY: 'auto',
            transition: 'max-height 0.25s ease-out',
          }}
        >
          <div style={{ padding: '0 14px 12px 14px' }}>
            <div style={{ fontSize: '11px', color: '#676767', marginBottom: timelineEvents.length > 0 ? '10px' : 0 }}>
              {getStatusText()}
            </div>
            {timelineEvents.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {timelineEvents.map((event, index) => (
                  <div
                    key={event.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '22px 1fr auto',
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
                      {index < timelineEvents.length - 1 && (
                        <span
                          style={{
                            position: 'absolute',
                            top: '12px',
                            bottom: '-8px',
                            width: '1px',
                            backgroundColor: '#2a2a2a',
                          }}
                        />
                      )}
                      <span
                        style={{
                          position: 'relative',
                          zIndex: 1,
                          marginTop: '4px',
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor:
                            event.type === 'tool_end' ? '#34c759' :
                            event.type === 'tool_start' ? '#f59e0b' :
                            '#5a5a5a',
                        }}
                      />
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', color: '#ddd', lineHeight: 1.4 }}>
                        {getEventLabel(event)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#666', marginTop: '3px' }}>
                        {event.type === 'progress' ? 'Progress update' : event.type === 'tool_start' ? 'Tool started' : 'Tool completed'}
                      </div>
                    </div>
                    <div style={{ fontSize: '11px', color: '#555', whiteSpace: 'nowrap' }}>
                      {event.duration !== undefined ? `${Math.round(event.duration)}s` : formatEventTime(event.timestamp)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
});

export const ToolIndicator = ToolChain;
