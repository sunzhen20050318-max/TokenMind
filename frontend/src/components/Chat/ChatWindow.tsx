import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BrandMark } from '../BrandMark';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputArea, type DraftAttachment, type ComposerReasoningOption } from './InputArea';
import { hasFileTransfer } from './inputAreaDrag';
import { ToolChain } from './ToolIndicator';
import { ToolApprovalModal } from './ToolApprovalModal';
import { useChatStore, type TimelineEvent, type ToolCall } from '../../stores/chatStore';
import {
  isSessionConnected,
  isSessionExecTrusted,
  respondToToolApproval,
  sendMessage as sendChatMessage,
  setSessionExecTrust,
  stopSessionTask,
} from '../../hooks/useSessionOrchestrator';
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
  title: string;
  prompt: string;
}

const STARTER_CARDS: StarterCard[] = [
  {
    id: 'search',
    title: '搜索信息',
    prompt: '请帮我搜索一个主题，并把结果整理成清晰的要点总结。',
  },
  {
    id: 'files',
    title: '读取文件',
    prompt: '请帮我读取一个文件或图片，并提取其中的关键信息给我。',
  },
  {
    id: 'mcp',
    title: '使用 MCP',
    prompt: '请检查当前可用的 MCP 服务和工具，并告诉我它们可以帮我完成什么任务。',
  },
  {
    id: 'task',
    title: '定时任务',
    prompt: '请帮我设计一个适合当前项目的自动化或定时任务方案。',
  },
  {
    id: 'assistant',
    title: '个人助理',
    prompt: '我想把 TokenMind 当成个人 AI 助手使用，请先告诉我它最适合帮我做哪些事情。',
  },
];

const REASONING_OPTIONS: ComposerReasoningOption[] = [
  { value: '', label: '关闭' },
  { value: 'low', label: '轻度' },
  { value: 'medium', label: '标准' },
  { value: 'high', label: '深度' },
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

function mergeTimelineEvents(primary: TimelineEvent[], fallback: TimelineEvent[]): TimelineEvent[] {
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
  const clippedArgs = compactArgs.length > 140 ? `${compactArgs.slice(0, 137)}...` : compactArgs;
  return `${toolName}(${clippedArgs})`;
}

function deriveTurnArtifacts(messages: Message[]): Map<string, TurnArtifacts> {
  const artifacts = new Map<string, TurnArtifacts>();
  const toolMeta = new Map<
    string,
    { turnKey: string; toolName: string; displayName: string; startedAt?: string }
  >();
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
      const duration =
        meta?.startedAt && message.timestamp
          ? Math.max(
              0,
              Math.round(
                (new Date(message.timestamp).getTime() - new Date(meta.startedAt).getTime()) / 1000
              )
            )
          : undefined;
      const timestamp = message.timestamp || new Date().toISOString();
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
      toolCall.status === 'running' ? { ...toolCall, status: 'completed' } : toolCall
    );
  }

  return artifacts;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return '夜深了，现在想继续完成什么？';
  if (hour < 12) return '早上好，今天想先推进什么？';
  if (hour < 18) return '下午好，今天想一起完成什么？';
  return '晚上好，现在想处理什么？';
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
    modelProviders,
    activeModelId,
    modelProvidersStatus,
    setActiveModel,
    availableKnowledgeBases,
    linkedKnowledgeBaseIds,
    loadKnowledgeBases,
    loadLinkedKnowledgeBases,
    setLinkedKnowledgeBases,
    pendingSessionStarter,
    clearPendingSessionStarter,
    pendingApproval,
    sessionExecTrusted,
    setSessionPendingApproval,
    setSessionExecTrusted,
  } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // The orchestrator owns the WebSocket lifecycle; ChatWindow only ever
  // dispatches actions for its current session, never opens/closes sockets.
  const sendMessage = useCallback(
    (content: string, attachments: Parameters<typeof sendChatMessage>[2] = []) => {
      sendChatMessage(sessionId, content, attachments);
    },
    [sessionId],
  );
  const stopMessage = useCallback(() => {
    stopSessionTask(sessionId);
  }, [sessionId]);
  const isConnected = isSessionConnected(sessionId);
  const enableExecForSession = useCallback(() => {
    setSessionExecTrust(sessionId, true);
  }, [sessionId]);
  const disableExecForSession = useCallback(() => {
    setSessionExecTrust(sessionId, false);
  }, [sessionId]);
  const approvePendingTool = useCallback(() => {
    if (!pendingApproval) return;
    respondToToolApproval(sessionId, pendingApproval.approval_id, true);
    setSessionPendingApproval(sessionId, null);
  }, [pendingApproval, sessionId, setSessionPendingApproval]);
  const rejectPendingTool = useCallback(() => {
    if (!pendingApproval) return;
    respondToToolApproval(sessionId, pendingApproval.approval_id, false);
    setSessionPendingApproval(sessionId, null);
  }, [pendingApproval, sessionId, setSessionPendingApproval]);
  const trustAndApprovePendingTool = useCallback(() => {
    if (!pendingApproval) return;
    setSessionExecTrust(sessionId, true);
    respondToToolApproval(sessionId, pendingApproval.approval_id, true);
    setSessionPendingApproval(sessionId, null);
  }, [pendingApproval, sessionId, setSessionPendingApproval]);

  // On mount/session change, hydrate the per-session exec-trust flag from
  // localStorage so the toggle reflects the persisted preference.
  useEffect(() => {
    setSessionExecTrusted(sessionId, isSessionExecTrusted(sessionId));
  }, [sessionId, setSessionExecTrusted]);
  const prevMessagesLenRef = useRef<number>(0);
  const dragDepthRef = useRef(0);
  const [draftMessage, setDraftMessage] = useState('');
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [pendingFiles, setPendingFiles] = useState<Array<{ id: string; file: File }>>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>('');
  const [isSurfaceDragActive, setIsSurfaceDragActive] = useState(false);

  useEffect(() => {
    setDraftMessage('');
    setPendingFiles([]);
    setUploadProgress(null);
  }, [sessionId]);

  useEffect(() => {
    void loadKnowledgeBases();
    void loadLinkedKnowledgeBases(sessionId);
  }, [loadKnowledgeBases, loadLinkedKnowledgeBases, sessionId]);

  useEffect(() => {
    let active = true;
    const loadComposerConfig = async () => {
      try {
        const config = await api.getConfig();
        if (!active) {
          return;
        }
        setReasoningEffort(config.agent.reasoning_effort || '');
      } catch {
        if (active) {
          setReasoningEffort('');
        }
      }
    };

    void loadComposerConfig();
    return () => {
      active = false;
    };
  }, []);

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
            !message.content.trim() &&
            !(message.attachments && message.attachments.length > 0)
          ) {
            return false;
          }
          return true;
        }),
    [messages]
  );

  const hasConversation = visibleMessages.length > 0;
  const persistedArtifactsByTurn = useMemo(() => deriveTurnArtifacts(messages), [messages]);
  const liveToolCallsByTurn = useMemo(() => groupByTurnId(toolCalls), [toolCalls]);
  const liveTimelineEventsByTurn = useMemo(() => groupByTurnId(timelineEvents), [timelineEvents]);

  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) {
      return;
    }

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const newMessagesCount = visibleMessages.length - prevMessagesLenRef.current;
    prevMessagesLenRef.current = visibleMessages.length;

    if (newMessagesCount > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else if ((toolCalls.length > 0 || timelineEvents.length > 0) && distanceFromBottom < 120) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [visibleMessages, toolCalls, timelineEvents]);

  const handleSend = useCallback(async (content: string) => {
    if (!isConnected || (!content.trim() && pendingFiles.length === 0)) {
      return;
    }

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
  }, [
    addMessage,
    isConnected,
    pendingFiles,
    sendMessage,
    setActiveTool,
    setCurrentTurnId,
    setError,
    setLoading,
  ]);

  useEffect(() => {
    if (!isConnected || !pendingSessionStarter || pendingSessionStarter.sessionId !== sessionId) {
      return;
    }

    const starterMessage = pendingSessionStarter.message;
    clearPendingSessionStarter(sessionId);
    void handleSend(starterMessage);
  }, [clearPendingSessionStarter, handleSend, isConnected, pendingSessionStarter, sessionId]);

  const handleStarterCardSelect = (prompt: string) => {
    setDraftMessage(prompt);
    setInputFocusSignal((signal) => signal + 1);
  };

  const appendPendingFiles = useCallback((files: File[]) => {
    const nextFiles = files.map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
    }));
    setPendingFiles((existing) => [...existing, ...nextFiles]);
  }, []);

  const handleSelectFiles = (files: FileList) => {
    appendPendingFiles(Array.from(files));
  };

  const handleRemoveAttachment = (id: string) => {
    setPendingFiles((existing) => existing.filter((item) => item.id !== id));
  };

  const handleReasoningChange = async (value: string) => {
    setReasoningEffort(value);
    try {
      await api.updateAgentConfig({ reasoning_effort: value || null });
    } catch (error) {
      setError(error instanceof Error ? error.message : '更新思考等级失败');
    }
  };

  const draftAttachments: DraftAttachment[] = pendingFiles.map(({ id, file }) => ({
    id,
    name: file.name,
    size: file.size,
    type: file.type,
  }));

  const resetSurfaceDragState = useCallback(() => {
    dragDepthRef.current = 0;
    setIsSurfaceDragActive(false);
  }, []);

  const handleSurfaceDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current += 1;
    setIsSurfaceDragActive(true);
  }, [isUploading]);

  const handleSurfaceDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
    if (!isSurfaceDragActive) {
      setIsSurfaceDragActive(true);
    }
  }, [isSurfaceDragActive, isUploading]);

  const handleSurfaceDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsSurfaceDragActive(false);
    }
  }, []);

  const handleSurfaceDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (isUploading || !hasFileTransfer(event.dataTransfer?.types)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const files = Array.from(event.dataTransfer?.files || []);
    resetSurfaceDragState();
    if (files.length > 0) {
      appendPendingFiles(files);
    }
  }, [appendPendingFiles, isUploading, resetSurfaceDragState]);

  const composerModelOptions = modelProviders.map((provider) => ({
    id: provider.id,
    label: provider.name,
    configured: provider.configured,
  }));

  const renderedThread = useMemo(() => {
    const nodes: React.ReactNode[] = [];
    let pendingTurnKey: string | null = null;
    let pendingArtifacts: TurnArtifacts | null = null;
    let pendingIsCurrentTurn = false;

    const buildToolChain = (keySeed: string) => {
      if (!pendingArtifacts) return null;

      const hasToolArtifacts =
        pendingArtifacts.toolCalls.length > 0 ||
        pendingArtifacts.timelineEvents.length > 0 ||
        (pendingIsCurrentTurn && isLoading && !!activeTool);

      if (!hasToolArtifacts) return null;

      return (
        <ToolChain
          key={`chain-${keySeed}`}
          toolCalls={pendingArtifacts.toolCalls}
          isActive={pendingIsCurrentTurn && isLoading && !!activeTool}
          isDone={
            !pendingIsCurrentTurn ||
            !isLoading ||
            !pendingArtifacts.toolCalls.some((toolCall) => toolCall.status === 'running')
          }
          displayCount={pendingArtifacts.toolCalls.length}
          activeToolName={pendingIsCurrentTurn ? activeTool || undefined : undefined}
          timelineEvents={pendingArtifacts.timelineEvents}
          variant="embedded"
        />
      );
    };

    const buildStandaloneChain = (keySeed: string) => {
      if (!pendingTurnKey || !pendingArtifacts) {
        return null;
      }

      const chain = buildToolChain(keySeed);
      if (!chain) return null;

      return (
        <MessageBubble
          key={`toolchain-standalone-${keySeed}`}
          message={{ role: 'assistant', content: '' }}
          embeddedToolChain={chain}
        />
      );
    };

    const flushPendingStandalone = (keySeed: string) => {
      const standalone = buildStandaloneChain(keySeed);
      if (standalone) {
        nodes.push(standalone);
      }
      pendingTurnKey = null;
      pendingArtifacts = null;
      pendingIsCurrentTurn = false;
    };

    visibleMessages.forEach(({ message, rawIndex }, idx) => {
      const keyBase = message.timestamp ? `${message.timestamp}-${idx}` : `msg-${idx}`;

      if (message.role === 'user') {
        if (pendingTurnKey) {
          flushPendingStandalone(`${keyBase}-before-user`);
        }

        const turnKey = getTurnKey(message, rawIndex);
        const persistedArtifacts = persistedArtifactsByTurn.get(turnKey);
        pendingTurnKey = turnKey;
        pendingArtifacts = {
          toolCalls: liveToolCallsByTurn.get(turnKey) || persistedArtifacts?.toolCalls || [],
          timelineEvents: mergeTimelineEvents(
            liveTimelineEventsByTurn.get(turnKey) || [],
            persistedArtifacts?.timelineEvents || []
          ),
        };
        pendingIsCurrentTurn = turnKey === currentTurnId;
        nodes.push(<MessageBubble key={keyBase} message={message} />);
        return;
      }

      if (message.role === 'assistant' && pendingTurnKey && pendingArtifacts) {
        const chain = buildToolChain(keyBase);

        nodes.push(
          <MessageBubble
            key={keyBase}
            message={message}
            embeddedToolChain={chain ?? undefined}
          />
        );
        pendingTurnKey = null;
        pendingArtifacts = null;
        pendingIsCurrentTurn = false;
        return;
      }

      nodes.push(<MessageBubble key={keyBase} message={message} />);
    });

    if (pendingTurnKey) {
      flushPendingStandalone('tail');
    }

    return nodes;
  }, [
    activeTool,
    currentTurnId,
    isLoading,
    liveTimelineEventsByTurn,
    liveToolCallsByTurn,
    persistedArtifactsByTurn,
    visibleMessages,
  ]);

  return (
    <div className={`chat-shell ${hasConversation ? 'chat-shell--active' : 'chat-shell--launch'}`}>
      <div className="chat-shell__topbar">
        <button
          type="button"
          className={`chat-shell__trust ${sessionExecTrusted ? 'is-trusted' : ''}`}
          onClick={sessionExecTrusted ? disableExecForSession : enableExecForSession}
          title={
            sessionExecTrusted
              ? '当前会话中的 exec 会自动允许，点击后恢复逐次确认。'
              : '开启后，当前会话中的 exec 不再每次弹出确认。'
          }
        >
          {sessionExecTrusted ? '当前会话 Exec 已允许' : '允许当前会话执行 Exec'}
        </button>
      </div>

      <div
        className={`chat-shell__surface ${isSurfaceDragActive ? 'is-drop-active' : ''}`}
        onDragEnter={handleSurfaceDragEnter}
        onDragOver={handleSurfaceDragOver}
        onDragLeave={handleSurfaceDragLeave}
        onDrop={handleSurfaceDrop}
      >
        {isSurfaceDragActive ? (
          <div className="chat-shell__drop-overlay" aria-hidden="true">
            <div className="chat-shell__drop-hero">
              <div className="chat-shell__drop-icon">
                <svg viewBox="0 0 64 64" fill="none">
                  <rect x="6" y="12" width="22" height="28" rx="6" fill="#7f8cff" opacity="0.92" transform="rotate(-12 6 12)" />
                  <rect x="36" y="10" width="22" height="30" rx="6" fill="#b5befd" opacity="0.92" transform="rotate(10 36 10)" />
                  <rect x="20" y="28" width="24" height="24" rx="7" fill="#5662ff" />
                  <path d="M27 44l4-5 4 3 4-5 5 7H27z" fill="#dfe3ff" />
                  <circle cx="35.5" cy="35.5" r="2.5" fill="#dfe3ff" />
                </svg>
              </div>
              <h2 className="chat-shell__drop-title">添加任意内容</h2>
              <p className="chat-shell__drop-copy">将任意文件拖放到此处，以将其添加到对话中</p>
            </div>
          </div>
        ) : null}

        <div className={`chat-shell__scroll ${hasConversation ? 'is-active' : 'is-launch'}`}>
          {hasConversation ? (
            <div className="chat-thread">
              {renderedThread}
              {isLoading && !activeTool && visibleMessages.length > 0 ? <TypingIndicator /> : null}
            </div>
          ) : isLoading ? (
            // History is still loading — keep the area blank to avoid flashing the greeting.
            <div className="chat-launch chat-launch--loading" />
          ) : (
            <section className="chat-launch">
              <div className="chat-launch__headline">
                <span className="chat-launch__mark">
                  <BrandMark alt="" style={{ height: '0.9em', width: 'auto' }} />
                </span>
                <h1 className="chat-launch__title">{getGreeting()}</h1>
              </div>
            </section>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className={`chat-composer-dock ${hasConversation ? 'is-active' : 'is-launch'}`}>
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
            externalDragActive={isSurfaceDragActive}
            composerMode={hasConversation ? 'active' : 'launch'}
            modelOptions={composerModelOptions}
            activeModelId={activeModelId}
            modelStatus={modelProvidersStatus}
            onSelectModel={(providerId) => {
              void setActiveModel(providerId);
            }}
            reasoningOptions={REASONING_OPTIONS}
            activeReasoning={reasoningEffort}
            onSelectReasoning={(value) => {
              void handleReasoningChange(value);
            }}
            knowledgeOptions={availableKnowledgeBases
              .filter((item) => item.enabled)
              .map((item) => ({
              id: item.id,
              name: item.name,
              description: item.description,
            }))}
            linkedKnowledgeBaseIds={linkedKnowledgeBaseIds}
            onUpdateLinkedKnowledgeBases={(knowledgeBaseIds) => {
              void setLinkedKnowledgeBases(knowledgeBaseIds);
            }}
          />

          <div className={`chat-launch__chips ${hasConversation ? 'is-hidden' : ''}`}>
            {STARTER_CARDS.map((card) => (
              <button
                key={card.id}
                type="button"
                className="chat-launch__chip"
                onClick={() => handleStarterCardSelect(card.prompt)}
                title={card.prompt}
              >
                {card.title}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ToolApprovalModal
        approval={pendingApproval}
        onApprove={approvePendingTool}
        onReject={rejectPendingTool}
        onTrustAndApprove={trustAndApprovePendingTool}
      />
    </div>
  );
};
