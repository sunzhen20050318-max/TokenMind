import React, { useEffect, useMemo, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputArea } from './InputArea';
import { ToolChain } from './ToolIndicator';
import { useChatStore, type TimelineEvent, type ToolCall } from '../../stores/chatStore';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { Message } from '../../types';

interface ChatWindowProps {
  sessionId: string;
}

interface VisibleMessageEntry {
  message: Message;
  rawIndex: number;
}

interface TurnArtifacts {
  timelineEvents: TimelineEvent[];
  toolCalls: ToolCall[];
}

function getTurnKey(message: Message, rawIndex: number): string {
  return message.timestamp || `turn-${rawIndex}`;
}

function groupByTurnId<T extends { turnId: string }>(items: T[]): Map<string, T[]> {
  const grouped = new Map<string, T[]>();
  items.forEach((item) => {
    if (!item.turnId) {
      return;
    }
    const existing = grouped.get(item.turnId) || [];
    existing.push(item);
    grouped.set(item.turnId, existing);
  });
  return grouped;
}

function mergeTimelineEvents(
  primary: TimelineEvent[],
  fallback: TimelineEvent[]
): TimelineEvent[] {
  const merged = new Map<string, TimelineEvent>();
  for (const event of fallback) {
    merged.set(event.id, event);
  }
  for (const event of primary) {
    merged.set(event.id, event);
  }
  return Array.from(merged.values()).sort((a, b) => {
    const tsA = new Date(a.timestamp).getTime();
    const tsB = new Date(b.timestamp).getTime();
    if (tsA !== tsB) {
      return tsA - tsB;
    }
    return a.id.localeCompare(b.id);
  });
}

function formatToolDisplayName(toolName: string, rawArguments?: string): string {
  if (!rawArguments || !rawArguments.trim()) {
    return toolName;
  }
  const compactArgs = rawArguments.replace(/\s+/g, ' ').trim();
  const clippedArgs = compactArgs.length > 140
    ? `${compactArgs.slice(0, 137)}...`
    : compactArgs;
  return `${toolName}(${clippedArgs})`;
}

function deriveTurnArtifacts(messages: Message[]): Map<string, TurnArtifacts> {
  const artifacts = new Map<string, TurnArtifacts>();
  const toolMeta = new Map<string, { turnKey: string; toolName: string; displayName: string; startedAt?: string }>();
  let currentTurnKey: string | null = null;

  const ensureTurn = (turnKey: string): TurnArtifacts => {
    const existing = artifacts.get(turnKey);
    if (existing) {
      return existing;
    }
    const created: TurnArtifacts = { timelineEvents: [], toolCalls: [] };
    artifacts.set(turnKey, created);
    return created;
  };

  messages.forEach((message, rawIndex) => {
    if (message.role === 'user') {
      currentTurnKey = getTurnKey(message, rawIndex);
      ensureTurn(currentTurnKey);
      return;
    }

    if (!currentTurnKey) {
      return;
    }

    if (message.role === 'assistant' && message.tool_calls?.length) {
      const turn = ensureTurn(currentTurnKey);
      message.tool_calls.forEach((toolCall, toolIndex) => {
        const toolId = toolCall.id || `${currentTurnKey}-tool-${toolIndex}`;
        const toolName = toolCall.function?.name || toolCall.name || 'tool';
        const displayName = formatToolDisplayName(toolName, toolCall.function?.arguments);
        const timestamp = message.timestamp || new Date().toISOString();

        turn.timelineEvents.push({
          id: `${toolId}-start`,
          type: 'tool_start',
          content: displayName,
          timestamp,
          turnId: currentTurnKey!,
          toolId,
          toolName,
        });
        turn.toolCalls.push({
          id: toolId,
          tool: displayName,
          status: 'running',
          timestamp,
          turnId: currentTurnKey!,
        });
        toolMeta.set(toolId, {
          turnKey: currentTurnKey!,
          toolName,
          displayName,
          startedAt: message.timestamp,
        });
      });
      return;
    }

    if (message.role === 'tool') {
      const toolId = message.tool_call_id || `${currentTurnKey}-tool-${rawIndex}`;
      const meta = toolMeta.get(toolId);
      const turnKey = meta?.turnKey || currentTurnKey;
      const toolName = meta?.toolName || message.name || 'tool';
      const displayName = meta?.displayName || toolName;
      const timestamp = message.timestamp || new Date().toISOString();
      const duration =
        meta?.startedAt && message.timestamp
          ? Math.max(
              0,
              Math.round(
                (new Date(message.timestamp).getTime() - new Date(meta.startedAt).getTime()) / 1000
              )
            )
          : undefined;
      const turn = ensureTurn(turnKey);

      turn.timelineEvents.push({
        id: `${toolId}-end`,
        type: 'tool_end',
        content: displayName,
        timestamp,
        turnId: turnKey,
        toolId,
        toolName,
        duration,
      });

      const existingTool = turn.toolCalls.find((toolCall) => toolCall.id === toolId);
      if (existingTool) {
        existingTool.status = 'completed';
        existingTool.duration = duration;
      } else {
        turn.toolCalls.push({
          id: toolId,
          tool: displayName,
          status: 'completed',
          timestamp,
          turnId: turnKey,
          duration,
        });
      }
    }
  });

  for (const [, turn] of artifacts) {
    turn.toolCalls = turn.toolCalls.map((toolCall) =>
      toolCall.status === 'running'
        ? { ...toolCall, status: 'completed' }
        : toolCall
    );
  }

  return artifacts;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ sessionId }) => {
  const {
    messages,
    isLoading,
    activeTool,
    addMessage,
    setLoading,
    toolCalls,
    timelineEvents,
    currentTurnId,
    setActiveTool,
    setCurrentTurnId,
  } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, stopMessage, isConnected } = useWebSocket(sessionId);
  const prevMessagesLenRef = useRef<number>(0);

  const visibleMessages = useMemo<VisibleMessageEntry[]>(
    () =>
      messages
        .map((message, rawIndex) => ({ message, rawIndex }))
        .filter(({ message }) => {
          if (message.role === 'tool') {
            return false;
          }
          if (message.role === 'assistant' && message.tool_calls?.length) {
            return false;
          }
          if (
            message.role === 'assistant' &&
            typeof message.content === 'string' &&
            !message.content.trim()
          ) {
            return false;
          }
          return true;
        }),
    [messages]
  );

  const persistedArtifactsByTurn = useMemo(() => deriveTurnArtifacts(messages), [messages]);
  const liveToolCallsByTurn = useMemo(() => groupByTurnId(toolCalls), [toolCalls]);
  const liveTimelineEventsByTurn = useMemo(() => groupByTurnId(timelineEvents), [timelineEvents]);

  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const newMessagesCount = visibleMessages.length - prevMessagesLenRef.current;
    prevMessagesLenRef.current = visibleMessages.length;

    if (newMessagesCount > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else if ((toolCalls.length > 0 || timelineEvents.length > 0) && distanceFromBottom < 100) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [visibleMessages, toolCalls, timelineEvents]);

  const handleSend = (content: string) => {
    if (!isConnected) return;
    const turnId = new Date().toISOString();
    setCurrentTurnId(turnId);
    setActiveTool(null);
    addMessage({
      role: 'user',
      content,
      timestamp: turnId,
    });
    setLoading(true);
    sendMessage(content);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#0a0a0a',
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          paddingTop: '24px',
          paddingBottom: '12px',
          contentVisibility: 'auto',
        }}
      >
        {visibleMessages.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#6e6e73',
            }}
          >
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="1" style={{ marginBottom: '16px' }}>
              <circle cx="12" cy="12" r="4" fill="#666" stroke="#666" />
              <line x1="12" y1="2" x2="12" y2="5" />
              <line x1="12" y1="19" x2="12" y2="22" />
              <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
              <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
              <line x1="2" y1="12" x2="5" y2="12" />
              <line x1="19" y1="12" x2="22" y2="12" />
              <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
              <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
            </svg>
            <p style={{ fontSize: '16px', marginBottom: '8px', color: '#8e8e93' }}>
              Start a conversation with sun-agent
            </p>
            <p style={{ fontSize: '13px' }}>
              Ask questions, get help with tasks, and more
            </p>
          </div>
        ) : (
          <>
            {visibleMessages.map(({ message, rawIndex }, idx) => {
              const turnKey = message.role === 'user' ? getTurnKey(message, rawIndex) : null;
              const persistedArtifacts = turnKey ? persistedArtifactsByTurn.get(turnKey) : undefined;
              const turnToolCalls = turnKey
                ? liveToolCallsByTurn.get(turnKey) || persistedArtifacts?.toolCalls || []
                : [];
              const turnTimeline = turnKey
                ? mergeTimelineEvents(
                    liveTimelineEventsByTurn.get(turnKey) || [],
                    persistedArtifacts?.timelineEvents || []
                  )
                : [];
              const isCurrentTurn = turnKey !== null && turnKey === currentTurnId;
              const showToolChain =
                message.role === 'user' &&
                (turnToolCalls.length > 0 || turnTimeline.length > 0 || (isCurrentTurn && !!activeTool));

              return (
                <React.Fragment key={message.timestamp ? `${message.timestamp}-${idx}` : `msg-${idx}`}>
                  <MessageBubble message={message} />
                  {showToolChain && (
                    <ToolChain
                      toolCalls={turnToolCalls}
                      isActive={isCurrentTurn && isLoading && !!activeTool}
                      isDone={!isCurrentTurn || !isLoading || !turnToolCalls.some((toolCall) => toolCall.status === 'running')}
                      displayCount={turnToolCalls.length}
                      activeToolName={isCurrentTurn ? activeTool || undefined : undefined}
                      timelineEvents={turnTimeline}
                    />
                  )}
                </React.Fragment>
              );
            })}
            {isLoading && !activeTool && visibleMessages.length > 0 && <TypingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      <InputArea
        onSend={handleSend}
        onStop={stopMessage}
        disabled={!isConnected}
        isStreaming={isLoading}
      />
    </div>
  );
};
