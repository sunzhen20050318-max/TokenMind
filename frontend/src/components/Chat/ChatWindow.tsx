import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BrandMark } from '../BrandMark';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputArea, type DraftAttachment, type ComposerReasoningOption } from './InputArea';
import { hasFileTransfer } from './inputAreaDrag';
import { ToolChain } from './ToolIndicator';
import { BrowserHandoffModal } from './BrowserHandoffModal';
import { ToolApprovalModal } from './ToolApprovalModal';
import { UserQuestionModal } from './UserQuestionModal';
import { TaskListBubble } from './TaskListBubble';
import { CommandCardModal, type CommandCardOption } from './CommandCardModal';
import { StatusCard } from './StatusCard';
import type { SlashCommandOption } from './SlashCommandMenu';
import type { SlashSkillSummary } from '../../types';
import { useChatStore, type TimelineEvent, type ToolCall } from '../../stores/chatStore';
import {
  useSessionConnected,
  isSessionExecTrusted,
  respondToBrowserHandoff,
  respondToToolApproval,
  respondToUserQuestion,
  sendMessage as sendChatMessage,
  sendSessionGuidance,
  setSessionExecTrust,
  stopSessionTask,
} from '../../hooks/useSessionOrchestrator';
import { api } from '../../services/api';
import type { Attachment, Message, UploadProgress } from '../../types';
import './chatWindow.css';

interface ChatWindowProps {
  sessionId: string;
  onNavigateToSettings?: () => void;
  onNavigateToBrowser?: () => void;
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

export const ChatWindow: React.FC<ChatWindowProps> = ({ sessionId, onNavigateToSettings, onNavigateToBrowser }) => {
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
    activeWikiKbId,
    setActiveWikiKb,
    pendingSessionStarter,
    clearPendingSessionStarter,
    pendingApproval,
    pendingBrowserHandoff,
    setPendingBrowserHandoff,
    pendingUserQuestion,
    taskList,
    pendingMessages,
    consolidatedOffset,
    compactSession,
    personality,
    planMode,
    compactionThresholdTokens,
    lastPromptTokens,
    lastPromptAt,
    lastPromptModel,
    setSessionPersonality,
    setSessionPlanMode,
    setSessionPendingApproval,
    setSessionPendingUserQuestion,
    dismissSessionTaskList,
    enqueuePendingMessage,
    removePendingMessage,
    shiftPendingMessage,
    setSessionExecTrusted,
  } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Track the composer dock's current height so we can grow the scroll
  // area's bottom padding to match. Without this the approval / question
  // modal (which is rendered inside the dock and grows the dock upward)
  // would overlap the messages content. The base value covers the input
  // area alone; ResizeObserver updates it when a modal appears.
  const dockRef = useRef<HTMLDivElement>(null);
  const [dockHeight, setDockHeight] = useState<number>(0);
  const prevDockHeightRef = useRef<number>(0);
  useEffect(() => {
    const el = dockRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const h = entry.contentRect.height;
        setDockHeight(h);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // When the dock grows (modal appears), auto-scroll the messages
  // container all the way to the bottom so the last message sits just
  // above the (now-taller) dock. Using scrollIntoView with default
  // block='start' would scroll the ref to the top of the viewport
  // instead — wrong direction. We also wait one frame so the updated
  // padding-bottom has been applied and scrollHeight reflects it.
  useEffect(() => {
    if (dockHeight > prevDockHeightRef.current + 20) {
      const container = messagesEndRef.current?.parentElement;
      if (container) {
        requestAnimationFrame(() => {
          container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        });
      }
    }
    prevDockHeightRef.current = dockHeight;
  }, [dockHeight]);
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
  const isConnected = useSessionConnected(sessionId);
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
  const redirectPendingTool = useCallback(
    (instruction: string) => {
      if (!pendingApproval) return;
      const text = instruction.trim();
      if (!text) return;
      respondToToolApproval(sessionId, pendingApproval.approval_id, false);
      sendSessionGuidance(sessionId, text);
      setSessionPendingApproval(sessionId, null);
    },
    [pendingApproval, sessionId, setSessionPendingApproval],
  );
  const handleBrowserHandoffComplete = useCallback(() => {
    if (!pendingBrowserHandoff) return;
    respondToBrowserHandoff(pendingBrowserHandoff.session_id, pendingBrowserHandoff.handoff_id, true);
    setPendingBrowserHandoff(null);
  }, [pendingBrowserHandoff, setPendingBrowserHandoff]);
  const handleBrowserHandoffCancel = useCallback(() => {
    if (!pendingBrowserHandoff) return;
    respondToBrowserHandoff(pendingBrowserHandoff.session_id, pendingBrowserHandoff.handoff_id, false);
    setPendingBrowserHandoff(null);
  }, [pendingBrowserHandoff, setPendingBrowserHandoff]);
  const submitPendingUserQuestion = useCallback(
    (answers: Record<string, { selected: string | string[]; notes?: string }>) => {
      if (!pendingUserQuestion) return;
      respondToUserQuestion(sessionId, pendingUserQuestion.question_id, answers);
      setSessionPendingUserQuestion(sessionId, null);
    },
    [pendingUserQuestion, sessionId, setSessionPendingUserQuestion],
  );
  const cancelPendingUserQuestion = useCallback(() => {
    if (!pendingUserQuestion) return;
    // Sending an empty-answers response tells the backend the user
    // dismissed the question; the tool result is "user did not respond".
    respondToUserQuestion(sessionId, pendingUserQuestion.question_id, {});
    setSessionPendingUserQuestion(sessionId, null);
  }, [pendingUserQuestion, sessionId, setSessionPendingUserQuestion]);

  // Stable callback so the TaskListBubble's auto-dismiss timer effect
  // doesn't get its cleanup torn down on every parent re-render — a
  // fresh inline arrow caused the timer to be cancelled before it
  // could fire, defeating the 5-second auto-close behavior.
  const dismissTaskListForSession = useCallback(() => {
    dismissSessionTaskList(sessionId);
  }, [sessionId, dismissSessionTaskList]);

  // ── Slash command card options ─────────────────────────────────────
  const personalityCardOptions = useMemo<CommandCardOption[]>(
    () => [
      {
        value: '__default__',
        label: '系统默认',
        hint: '让模型用它自己的语气回答。',
      },
      {
        value: 'pragmatic',
        label: '务实 · pragmatic',
        hint: '直接给结论或操作，不寒暄、不重复问题、不展开思路（默认推荐，省 token）',
      },
      {
        value: 'warm',
        label: '亲和 · warm',
        hint: '语气温和、共情、可以解释你的思考。会比务实风格多花一些 token。',
      },
    ],
    [],
  );
  // ── Slash commands ────────────────────────────────────────────────
  // Built-in commands + workspace skills fetched on session change.
  const [slashSkills, setSlashSkills] = useState<SlashSkillSummary[]>([]);
  useEffect(() => {
    let alive = true;
    api
      .listSlashSkills()
      .then((res) => {
        if (alive) setSlashSkills(res.items || []);
      })
      .catch(() => {
        // Skills are optional; ignore failures so the menu still shows
        // built-in commands.
      });
    return () => {
      alive = false;
    };
  }, [sessionId]);
  const slashCommandList = useMemo<SlashCommandOption[]>(
    () => [
      { name: 'compact', description: '压缩较早的对话到 HISTORY.md / MEMORY.md' },
      { name: 'status', description: '查看当前会话设置和上下文用量' },
      { name: 'model', description: '切换当前会话使用的模型' },
      { name: 'reasoning', description: '切换思考深度（低 / 中 / 高）' },
      { name: 'personality', description: '切换回答风格（亲和 / 务实）' },
      { name: 'browser', description: '打开浏览器自动化页面（OpenCLI）' },
      ...slashSkills.map((s) => ({
        name: s.name,
        description: `技能 · ${s.description}`,
      })),
    ],
    [slashSkills],
  );
  type OpenCardKind = 'personality' | 'model' | 'reasoning' | 'status' | null;
  const [openCard, setOpenCard] = useState<OpenCardKind>(null);
  const closeOpenCard = useCallback(() => setOpenCard(null), []);
  // Slash-command status banner shown just above the input.
  //   pending: long-running op in flight (shows spinner, no auto-dismiss)
  //   done:    successful finish (auto-dismiss after 3.5s)
  //   error:   failed (auto-dismiss after 5s, slightly tinted)
  type SlashToast = { kind: 'pending' | 'done' | 'error'; text: string };
  const [slashToast, setSlashToast] = useState<SlashToast | null>(null);
  const slashToastTimerRef = useRef<number | null>(null);
  const setPendingSlashToast = useCallback((text: string) => {
    setSlashToast({ kind: 'pending', text });
    if (slashToastTimerRef.current !== null) {
      window.clearTimeout(slashToastTimerRef.current);
      slashToastTimerRef.current = null;
    }
  }, []);
  const finishSlashToast = useCallback((kind: 'done' | 'error', text: string) => {
    setSlashToast({ kind, text });
    if (slashToastTimerRef.current !== null) {
      window.clearTimeout(slashToastTimerRef.current);
    }
    slashToastTimerRef.current = window.setTimeout(() => {
      setSlashToast(null);
      slashToastTimerRef.current = null;
    }, kind === 'error' ? 5000 : 3500);
  }, []);
  useEffect(() => {
    return () => {
      if (slashToastTimerRef.current !== null) {
        window.clearTimeout(slashToastTimerRef.current);
      }
    };
  }, []);
  // Block double-fire of /compact while a previous one is still talking
  // to the LLM — otherwise the second click stacks another expensive
  // request behind the lock and the user sees ghost progress.
  const compactBusyRef = useRef(false);
  // Reactive mirror of compactBusyRef so the context ring can grey out
  // while a compaction is in flight (the ref alone won't re-render).
  const [compactBusy, setCompactBusy] = useState(false);
  const dispatchSkill = useCallback(
    async (name: string, args: string) => {
      try {
        const { body } = await api.getSkillBody(name);
        const rendered = body.includes('$ARGS')
          ? body.split('$ARGS').join(args)
          : args.trim()
            ? `${body.trimEnd()}\n\n${args}`
            : body;
        await handleSend(rendered);
      } catch (e) {
        finishSlashToast(
          'error',
          `加载技能失败：${e instanceof Error ? e.message : '未知错误'}`,
        );
      }
    },
    // handleSend is defined below — we declare its identity stable for
    // this callback via the deps list. eslint may complain, but the ref
    // is fine because handleSend itself reads other state through closures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [finishSlashToast],
  );
  const handleSlashCommand = useCallback(
    async (name: string, args: string = '') => {
      // 1) Skill dispatch — wins over built-ins so a workspace skill
      // never gets shadowed by a typo collision (we surface a warning
      // instead by checking the builtin set first).
      const isBuiltin =
        name === 'compact' ||
        name === 'status' ||
        name === 'model' ||
        name === 'reasoning' ||
        name === 'personality' ||
        name === 'browser';
      const isSkill = slashSkills.some((s) => s.name === name);
      if (!isBuiltin && isSkill) {
        await dispatchSkill(name, args);
        return;
      }
      if (name === 'status') {
        setOpenCard('status');
        return;
      }
      if (name === 'model') {
        setOpenCard('model');
        return;
      }
      if (name === 'reasoning') {
        setOpenCard('reasoning');
        return;
      }
      if (name === 'personality') {
        setOpenCard('personality');
        return;
      }
      if (name === 'browser') {
        if (onNavigateToBrowser) {
          onNavigateToBrowser();
        } else {
          finishSlashToast('error', '当前界面不支持跳转到浏览器页面');
        }
        return;
      }
      if (name === 'compact') {
        if (compactBusyRef.current) {
          finishSlashToast('error', '上一次 /compact 还在进行中…');
          return;
        }
        compactBusyRef.current = true;
        setCompactBusy(true);
        setPendingSlashToast('正在压缩对话历史，请稍候…（LLM 摘要中）');
        // Snapshot the offset + messages BEFORE the call so we can
        // translate the backend's raw-message count into a
        // user-visible count (raw includes tool_call / tool_result
        // messages that never show up as chat bubbles).
        const prevOffset = useChatStore.getState().consolidatedOffset;
        const prevMessages = useChatStore.getState().messages;
        try {
          const compactedRaw = await compactSession(sessionId);
          if (compactedRaw > 0) {
            const visibleCount = prevMessages
              .slice(prevOffset, prevOffset + compactedRaw)
              .filter(
                (m) =>
                  (m.role === 'user' ||
                    (m.role === 'assistant' && !m.tool_calls?.length)) &&
                  (typeof m.content !== 'string' || m.content.trim().length > 0),
              ).length;
            finishSlashToast(
              'done',
              `已固化 ${visibleCount} 条对话到 HISTORY.md / MEMORY.md`,
            );
          } else {
            finishSlashToast('done', '当前没有可固化的较早对话');
          }
        } catch (e) {
          finishSlashToast(
            'error',
            `压缩失败：${e instanceof Error ? e.message : '未知错误'}`,
          );
        } finally {
          compactBusyRef.current = false;
          setCompactBusy(false);
        }
        return;
      }
      finishSlashToast('error', `未识别的命令：/${name}`);
    },
    [
      compactSession,
      sessionId,
      setPendingSlashToast,
      finishSlashToast,
      slashSkills,
      dispatchSkill,
    ],
  );

  // On mount/session change, hydrate the per-session exec-trust flag from
  // localStorage so the toggle reflects the persisted preference.
  useEffect(() => {
    setSessionExecTrusted(sessionId, isSessionExecTrusted(sessionId));
  }, [sessionId, setSessionExecTrusted]);
  const prevMessagesLenRef = useRef<number>(0);
  const dragDepthRef = useRef(0);
  const draftStorageKey = (sid: string) => `tokenmind:draft:${sid}`;
  const [draftMessage, setDraftMessage] = useState<string>(() => {
    if (typeof window === 'undefined') return '';
    return window.localStorage.getItem(draftStorageKey(sessionId)) || '';
  });
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [pendingFiles, setPendingFiles] = useState<Array<{ id: string; file: File }>>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>('');
  const [isSurfaceDragActive, setIsSurfaceDragActive] = useState(false);

  // Switching sessions: restore that session's draft (or empty), and reset
  // attachment / upload state so per-session UI starts clean.
  useEffect(() => {
    const stored =
      typeof window !== 'undefined'
        ? window.localStorage.getItem(draftStorageKey(sessionId)) || ''
        : '';
    setDraftMessage(stored);
    setPendingFiles([]);
    setUploadProgress(null);
    setInputFocusSignal((signal) => signal + 1);
  }, [sessionId]);

  // Persist draft (debounced) — survives refresh, navigation, and tab close.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const key = draftStorageKey(sessionId);
    const tid = window.setTimeout(() => {
      if (draftMessage) {
        window.localStorage.setItem(key, draftMessage);
      } else {
        window.localStorage.removeItem(key);
      }
    }, 250);
    return () => window.clearTimeout(tid);
  }, [sessionId, draftMessage]);

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

    // Agent is busy → defer this message instead of dropping it. Pending
    // entries flush automatically the next time isLoading flips to false
    // (see the drain effect below). Attachments aren't queued in this mode
    // — keep the user's pending files staged so they ship with the next
    // *foreground* send.
    if (isLoading && pendingFiles.length === 0 && content.trim()) {
      enqueuePendingMessage(sessionId, content);
      setDraftMessage('');
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
    enqueuePendingMessage,
    isConnected,
    isLoading,
    pendingFiles,
    sendMessage,
    sessionId,
    setActiveTool,
    setCurrentTurnId,
    setError,
    setLoading,
  ]);

  // Drain the deferred-message queue once the agent goes idle. We only
  // kick off one at a time — sending it flips ``isLoading`` back to true,
  // and the next entry waits for the *next* idle transition. Bail out
  // when there are no pending files so a queued plain-text message
  // doesn't accidentally piggyback uploads the user staged afterwards.
  useEffect(() => {
    if (isLoading) return;
    if (pendingMessages.length === 0) return;
    if (pendingFiles.length > 0) return;
    if (!isConnected) return;
    const head = shiftPendingMessage(sessionId);
    if (head) {
      void handleSend(head.content);
    }
  }, [
    handleSend,
    isConnected,
    isLoading,
    pendingFiles.length,
    pendingMessages.length,
    sessionId,
    shiftPendingMessage,
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

  const modelCardOptions = useMemo<CommandCardOption[]>(
    () =>
      modelProviders
        .filter((p) => p.configured)
        .map((p) => ({
          value: p.id,
          label: p.name,
          hint: p.id,
        })),
    [modelProviders],
  );
  const reasoningCardOptions = useMemo<CommandCardOption[]>(
    () =>
      REASONING_OPTIONS.map((option) => ({
        value: option.value,
        label: option.label,
        hint:
          option.value === ''
            ? '不携带 reasoning_effort 参数 — 推理模型按默认行为'
            : `reasoning_effort = ${option.value}`,
      })),
    [],
  );
  const statusModelLabel = useMemo<string | null>(() => {
    if (!activeModelId) return null;
    const match = modelProviders.find((p) => p.id === activeModelId);
    return match ? match.name : activeModelId;
  }, [activeModelId, modelProviders]);

  const needsProviderSetup =
    modelProvidersStatus === 'ready' && !modelProviders.some((p) => p.configured);

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

        <div
          className={`chat-shell__scroll ${hasConversation ? 'is-active' : 'is-launch'}`}
          style={
            hasConversation && dockHeight > 0
              ? { paddingBottom: `${dockHeight + 36}px` }
              : undefined
          }
        >
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

        <div
          ref={dockRef}
          className={`chat-composer-dock ${hasConversation ? 'is-active' : 'is-launch'}`}
        >
          {!isConnected ? (
            <div className="chat-composer-dock__reconnecting" role="status">
              <span className="chat-composer-dock__reconnecting-dot" aria-hidden />
              连接中…消息会在连接恢复后发送
            </div>
          ) : null}
          {needsProviderSetup ? (
            <div className="chat-composer-dock__setup" role="status">
              <span className="chat-composer-dock__setup-icon" aria-hidden>⚙</span>
              <span className="chat-composer-dock__setup-text">
                还没有配置任何模型,发送消息会失败。
              </span>
              {onNavigateToSettings ? (
                <button
                  type="button"
                  className="chat-composer-dock__setup-cta"
                  onClick={onNavigateToSettings}
                >
                  去设置中心 →
                </button>
              ) : null}
            </div>
          ) : null}
          <ToolApprovalModal
            approval={pendingApproval}
            onApprove={approvePendingTool}
            onReject={rejectPendingTool}
            onTrustAndApprove={trustAndApprovePendingTool}
            onRedirect={redirectPendingTool}
          />
          <BrowserHandoffModal
            handoff={pendingBrowserHandoff && pendingBrowserHandoff.session_id === sessionId ? pendingBrowserHandoff : null}
            onComplete={handleBrowserHandoffComplete}
            onCancel={handleBrowserHandoffCancel}
          />
          <UserQuestionModal
            question={pendingUserQuestion}
            onSubmit={submitPendingUserQuestion}
            onCancel={cancelPendingUserQuestion}
          />
          <TaskListBubble snapshot={taskList} onDismiss={dismissTaskListForSession} />
          {openCard === 'personality' ? (
            <CommandCardModal
              title="PERSONALITY"
              subtitle="选择回答风格"
              icon="◇"
              options={personalityCardOptions}
              selectedValue={personality ?? '__default__'}
              onSubmit={async (value) => {
                const next = value === '__default__' ? null : (value as 'warm' | 'pragmatic');
                closeOpenCard();
                await setSessionPersonality(sessionId, next);
                finishSlashToast(
                  'done',
                  `回答风格：${
                    next === 'warm' ? '亲和' : next === 'pragmatic' ? '务实' : '系统默认'
                  }`,
                );
              }}
              onCancel={closeOpenCard}
            />
          ) : null}
          {openCard === 'model' ? (
            <CommandCardModal
              title="MODEL"
              subtitle="切换当前会话使用的模型"
              icon="⌬"
              options={modelCardOptions}
              selectedValue={activeModelId}
              onSubmit={async (value) => {
                closeOpenCard();
                try {
                  await setActiveModel(value);
                  const label = modelCardOptions.find((o) => o.value === value)?.label || value;
                  finishSlashToast('done', `模型已切换：${label}`);
                } catch (e) {
                  finishSlashToast(
                    'error',
                    `切换失败：${e instanceof Error ? e.message : '未知错误'}`,
                  );
                }
              }}
              onCancel={closeOpenCard}
              footerHint={
                modelCardOptions.length === 0
                  ? '尚未配置任何模型 — 去设置中心补全 API Key'
                  : undefined
              }
            />
          ) : null}
          {openCard === 'reasoning' ? (
            <CommandCardModal
              title="REASONING"
              subtitle="切换思考深度（仅对支持的模型生效）"
              icon="◈"
              options={reasoningCardOptions}
              selectedValue={reasoningEffort || ''}
              onSubmit={async (value) => {
                closeOpenCard();
                try {
                  await handleReasoningChange(value);
                  const label =
                    reasoningCardOptions.find((o) => o.value === value)?.label || value || '关闭';
                  finishSlashToast('done', `思考深度：${label}`);
                } catch (e) {
                  finishSlashToast(
                    'error',
                    `切换失败：${e instanceof Error ? e.message : '未知错误'}`,
                  );
                }
              }}
              onCancel={closeOpenCard}
            />
          ) : null}
          {openCard === 'status' ? (
            <StatusCard
              model={statusModelLabel}
              reasoning={reasoningEffort || null}
              personality={personality}
              planMode={planMode}
              messageCount={messages.length}
              consolidatedOffset={consolidatedOffset}
              compactionThreshold={compactionThresholdTokens}
              lastPromptTokens={lastPromptTokens}
              lastPromptAt={lastPromptAt}
              lastPromptModel={lastPromptModel}
              onClose={closeOpenCard}
            />
          ) : null}
          {slashToast ? (
            <div
              role="status"
              aria-live={slashToast.kind === 'pending' ? 'polite' : 'assertive'}
              style={{
                marginBottom: '8px',
                padding: '8px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                background: '#161616',
                border: `1px solid ${
                  slashToast.kind === 'error'
                    ? 'rgba(217,108,108,0.45)'
                    : 'rgba(255,255,255,0.18)'
                }`,
                borderRadius: '10px',
                color: slashToast.kind === 'error' ? '#e8a8a8' : '#cfcfcf',
                fontFamily:
                  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                fontSize: '11.5px',
              }}
            >
              <style>
                {`
                  @keyframes tk-slash-toast-spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                  }
                `}
              </style>
              {slashToast.kind === 'pending' ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
                  <circle cx="7" cy="7" r="5.5" stroke="rgba(232,232,232,0.25)" strokeWidth="1.5" fill="none" />
                  <circle
                    cx="7"
                    cy="7"
                    r="5.5"
                    stroke="#e8e8e8"
                    strokeWidth="1.5"
                    fill="none"
                    strokeDasharray="9 28"
                    strokeLinecap="round"
                    style={{
                      transformOrigin: 'center',
                      animation: 'tk-slash-toast-spin 1.2s linear infinite',
                    }}
                  />
                </svg>
              ) : slashToast.kind === 'done' ? (
                <span style={{ color: '#e8e8e8', fontSize: '12px' }}>✓</span>
              ) : (
                <span style={{ color: '#d96c6c', fontSize: '12px' }}>!</span>
              )}
              <span style={{ flex: 1, minWidth: 0 }}>{slashToast.text}</span>
            </div>
          ) : null}
          <InputArea
            onSend={handleSend}
            onStop={stopMessage}
            connectionDown={!isConnected}
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
            pendingMessages={pendingMessages}
            onCancelPendingMessage={(id) => removePendingMessage(sessionId, id)}
            onSendGuidance={(id, content) => {
              sendSessionGuidance(sessionId, content);
              removePendingMessage(sessionId, id);
            }}
            slashCommands={slashCommandList}
            onSlashCommandSelect={(name, args) => {
              void handleSlashCommand(name, args || '');
            }}
            planMode={planMode}
            lastPromptTokens={lastPromptTokens}
            contextThreshold={compactionThresholdTokens}
            onCompactContext={() => {
              void handleSlashCommand('compact', '');
            }}
            compacting={compactBusy}
            onTogglePlanMode={() => {
              const next = !planMode;
              void setSessionPlanMode(sessionId, next).then(() => {
                finishSlashToast(
                  'done',
                  next ? '计划模式已开启' : '计划模式已关闭',
                );
              });
            }}
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
              .filter((item) => item.enabled && item.type === 'rag')
              .map((item) => ({
              id: item.id,
              name: item.name,
              description: item.description,
            }))}
            linkedKnowledgeBaseIds={linkedKnowledgeBaseIds}
            onUpdateLinkedKnowledgeBases={(knowledgeBaseIds) => {
              void setLinkedKnowledgeBases(knowledgeBaseIds);
            }}
            availableWikiKbs={availableKnowledgeBases.filter(
              (kb) => kb.enabled && kb.type === 'wiki',
            )}
            activeWikiKbId={activeWikiKbId}
            onSetActiveWikiKb={(kbId) => {
              void setActiveWikiKb(sessionId, kbId);
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

    </div>
  );
};
