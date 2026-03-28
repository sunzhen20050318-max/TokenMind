import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputArea, type DraftAttachment } from './InputArea';
import { ToolChain } from './ToolIndicator';
import { ToolApprovalModal } from './ToolApprovalModal';
import { useChatStore, type TimelineEvent, type ToolCall } from '../../stores/chatStore';
import { useWebSocket } from '../../hooks/useWebSocket';
import { api } from '../../services/api';
import type { Attachment, Message, UploadProgress } from '../../types';
import './chatWindow.css';

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

interface StarterCard {
  id: string;
  tag: string;
  title: string;
  description: string;
  prompt: string;
}

const STARTER_CARDS: StarterCard[] = [
  {
    id: 'channel-setup',
    tag: '渠道接入',
    title: '配置聊天渠道',
    description: '帮我配置 Telegram、飞书、Slack、WhatsApp 或其他聊天渠道的接入方式。',
    prompt: '请帮我检查当前项目支持哪些聊天渠道，并告诉我如何配置其中一个渠道接入。',
  },
  {
    id: 'search-summary',
    tag: '搜索总结',
    title: '搜索并整理信息',
    description: '搜索网页、提炼重点、输出结构化结论，适合做信息收集和快速总结。',
    prompt: '请帮我搜索一个主题，并把结果整理成清晰的要点总结。',
  },
  {
    id: 'file-image',
    tag: '文件理解',
    title: '读取文件或图片',
    description: '帮我处理文档、图片、截图或本地文件，提取内容并解释重点。',
    prompt: '请帮我读取一个文件或图片，并提取其中的关键信息给我。',
  },
  {
    id: 'mcp-workflow',
    tag: 'MCP',
    title: '使用 MCP 工具',
    description: '检查当前已连接的 MCP 服务和工具，让它们直接参与具体任务执行。',
    prompt: '请检查当前可用的 MCP 服务和工具，并告诉我它们可以帮我完成什么任务。',
  },
  {
    id: 'automation',
    tag: '自动化',
    title: '创建定时任务',
    description: '把常见动作做成定时执行的任务，例如日报、提醒、巡检或信息汇总。',
    prompt: '请帮我设计一个适合当前项目的自动化或定时任务方案。',
  },
  {
    id: 'assistant-task',
    tag: '个人助理',
    title: '处理日常任务',
    description: '把 SUN-AGENT 当成你的个人 AI 助手，让它帮你安排、分析、整理或执行任务。',
    prompt: '我想把 SUN-AGENT 当成个人 AI 助手使用，请先告诉我它最适合帮我做哪些事情。',
  },
];

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
    setError,
    toolCalls,
    timelineEvents,
    currentTurnId,
    setActiveTool,
    setCurrentTurnId,
  } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const {
    sendMessage,
    stopMessage,
    isConnected,
    pendingApproval,
    sessionExecTrusted,
    enableExecForSession,
    disableExecForSession,
    approvePendingTool,
    rejectPendingTool,
    trustAndApprovePendingTool,
  } = useWebSocket(sessionId);
  const prevMessagesLenRef = useRef<number>(0);
  const [draftMessage, setDraftMessage] = useState('');
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [pendingFiles, setPendingFiles] = useState<Array<{ id: string; file: File }>>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);

  useEffect(() => {
    setDraftMessage('');
    setPendingFiles([]);
    setUploadProgress(null);
  }, [sessionId]);

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

  const handleSend = async (content: string) => {
    if (!isConnected || (!content.trim() && pendingFiles.length === 0)) return;
    let attachments: Attachment[] = [];
    setError(null);

    if (pendingFiles.length > 0) {
      const fallbackTotal = pendingFiles.reduce((sum, item) => sum + item.file.size, 0);
      try {
        setIsUploading(true);
        setUploadProgress({
          loaded: 0,
          total: fallbackTotal,
          percent: 0,
        });
        const uploadResult = await api.uploadFiles(
          sessionId,
          pendingFiles.map((item) => item.file),
          (progress) => {
            setUploadProgress(progress);
          }
        );
        attachments = uploadResult.attachments;
      } catch (error) {
        setError(error instanceof Error ? error.message : '文件上传失败');
        setLoading(false);
        setIsUploading(false);
        setUploadProgress(null);
        return;
      } finally {
        setIsUploading(false);
      }
    }

    const turnId = new Date().toISOString();
    setCurrentTurnId(turnId);
    setActiveTool(null);
    addMessage({
      role: 'user',
      content,
      timestamp: turnId,
      attachments,
    });
    setLoading(true);
    sendMessage(content, attachments);
    setDraftMessage('');
    setPendingFiles([]);
    setUploadProgress(null);
  };

  const handleStarterCardSelect = (prompt: string) => {
    setDraftMessage(prompt);
    setInputFocusSignal((signal) => signal + 1);
  };

  const handleSelectFiles = (files: FileList) => {
    const nextFiles = Array.from(files).map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
    }));
    setPendingFiles((existing) => [...existing, ...nextFiles]);
  };

  const handleRemoveAttachment = (id: string) => {
    setPendingFiles((existing) => existing.filter((item) => item.id !== id));
  };

  const draftAttachments: DraftAttachment[] = pendingFiles.map(({ id, file }) => ({
    id,
    name: file.name,
    size: file.size,
    type: file.type,
  }));

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
          display: 'flex',
          justifyContent: 'flex-end',
          padding: '12px 16px 0',
        }}
      >
        <button
          type="button"
          onClick={sessionExecTrusted ? disableExecForSession : enableExecForSession}
          style={{
            borderRadius: '999px',
            border: sessionExecTrusted ? '1px solid rgba(255,255,255,0.08)' : '1px solid rgba(255,255,255,0.14)',
            background: sessionExecTrusted ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
            color: sessionExecTrusted ? '#f4f4f4' : '#c6c6c6',
            padding: '8px 12px',
            fontSize: '12px',
            cursor: 'pointer',
            transition: 'all 0.18s ease',
          }}
          title={
            sessionExecTrusted
              ? '当前会话中的 exec 将自动允许，点击可恢复逐次确认。'
              : '点击后，当前会话中的 exec 将不再每次弹确认。'
          }
        >
          {sessionExecTrusted ? '当前会话 Exec 已允许' : '允许当前会话执行 Exec'}
        </button>
      </div>
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
          <div className="chat-empty-state">
            <div className="chat-empty-shell">
              <div className="chat-empty-badge">SUN-AGENT workspace</div>
              <h2 className="chat-empty-title">把 SUN-AGENT 变成你的个人 AI 助手</h2>
              <p className="chat-empty-copy">
                这里更像一个可连接渠道、调用工具、处理文件、执行 MCP 和承接自动化任务的助手入口。选择一个场景后，提示词会自动填入下方输入框。
              </p>

              <div className="chat-starter-grid">
                {STARTER_CARDS.map((card) => (
                  <button
                    key={card.id}
                    type="button"
                    className="chat-starter-card"
                    onClick={() => handleStarterCardSelect(card.prompt)}
                  >
                    <div className="chat-starter-top">
                      <span className="chat-starter-tag">{card.tag}</span>
                      <span className="chat-starter-action">点击填入</span>
                    </div>
                    <div className="chat-starter-title">{card.title}</div>
                    <div className="chat-starter-description">{card.description}</div>
                    <div className="chat-starter-prompt">{card.prompt}</div>
                  </button>
                ))}
              </div>

              <div className="chat-empty-note">
                这些只是常见起点，你也可以直接描述自己的真实任务。
              </div>
            </div>
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
        isUploading={isUploading}
        uploadProgress={uploadProgress}
        value={draftMessage}
        onChange={setDraftMessage}
        focusSignal={inputFocusSignal}
        attachments={draftAttachments}
        onSelectFiles={handleSelectFiles}
        onRemoveAttachment={handleRemoveAttachment}
      />
      <ToolApprovalModal
        approval={pendingApproval}
        onApprove={approvePendingTool}
        onReject={rejectPendingTool}
        onTrustAndApprove={trustAndApprovePendingTool}
      />
    </div>
  );
};
