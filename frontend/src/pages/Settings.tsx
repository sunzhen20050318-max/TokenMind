import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CloseIcon } from '../components/CloseIcon';
import { api } from '../services/api';
import { useChatStore } from '../stores/chatStore';
import {
  createEmptyCreativeCapabilitySettings,
  isCreativeCapabilityConfigured,
} from '../types/config';
import type {
  AgentSettings,
  CreativeCapabilityKey,
  CreativeCapabilitySettings,
  CreativeSettings,
  ChannelCatalogEntry,
  ChannelName,
  McpServerSettings,
  McpServerSettingsUpdate,
  McpServerToolsState,
  ProviderSettings,
  RuntimeSettings,
  ToolsSettings,
} from '../types/config';
import type { CronJob, CronStatus, CreateCronJobPayload } from '../types/cron';
import type { MemoryOverviewResponse } from '../types/memory';
import type { StorageFileItem, StorageOverviewResponse } from '../types/storage';
import type { SkillSuggestion, SkillSummary } from '../types';
import './settings.css';

const PROVIDER_META: Record<
  string,
  {
    label: string;
    defaultModel: string;
    /**
     * Pre-fills the API Base input when the user opens this provider for
     * the first time. Mirrors ``ProviderSpec.default_api_base`` in
     * ``tokenmind/providers/registry.py`` — keep both in sync.
     */
    defaultApiBase: string;
    mode: 'api' | 'local' | 'oauth';
  }
> = {
  openai: {
    label: 'OpenAI',
    defaultModel: 'gpt-4o',
    defaultApiBase: 'https://api.openai.com/v1',
    mode: 'api',
  },
  anthropic: {
    label: 'Anthropic',
    defaultModel: 'claude-sonnet-4-5',
    defaultApiBase: 'https://api.anthropic.com/v1/',
    mode: 'api',
  },
  gemini: {
    label: 'Gemini',
    defaultModel: 'gemini-2.0-flash',
    defaultApiBase: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    mode: 'api',
  },
  deepseek: {
    label: 'DeepSeek',
    defaultModel: 'deepseek-chat',
    defaultApiBase: 'https://api.deepseek.com',
    mode: 'api',
  },
  moonshot: {
    label: 'Moonshot',
    defaultModel: 'kimi-k2.5',
    defaultApiBase: 'https://api.moonshot.ai/v1',
    mode: 'api',
  },
  minimax: {
    label: 'MiniMax',
    defaultModel: 'MiniMax-M2.7',
    defaultApiBase: 'https://api.minimax.io/v1',
    mode: 'api',
  },
  mimo: {
    label: 'MiMo',
    defaultModel: '',
    defaultApiBase: 'https://token-plan-sgp.xiaomimimo.com/v1',
    mode: 'api',
  },
  zhipu: {
    label: 'GLM',
    defaultModel: 'glm-4',
    defaultApiBase: 'https://open.bigmodel.cn/api/paas/v4/',
    mode: 'api',
  },
  dashscope: {
    label: 'Qwen',
    defaultModel: 'qwen-max',
    defaultApiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    mode: 'api',
  },
  openrouter: {
    label: 'OpenRouter',
    defaultModel: 'anthropic/claude-sonnet-4-5',
    defaultApiBase: 'https://openrouter.ai/api/v1',
    mode: 'api',
  },
  siliconflow: {
    label: 'SiliconFlow',
    defaultModel: 'Qwen/Qwen2.5-7B-Instruct',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    mode: 'api',
  },
  ollama: {
    label: 'Ollama',
    defaultModel: 'llama3.2',
    defaultApiBase: 'http://localhost:11434/v1',
    mode: 'local',
  },
  custom: {
    label: '自定义',
    defaultModel: 'default',
    defaultApiBase: '',
    mode: 'api',
  },
};

const CREATIVE_CAPABILITY_META: Record<
  CreativeCapabilityKey,
  {
    label: string;
    description: string;
    defaultProvider: string;
    defaultModel: string;
    usage: string;
  }
> = {
  image: {
    label: '生图',
    description: '在普通对话中按需调用，为当前会话返回图片附件。',
    defaultProvider: 'minimax',
    defaultModel: 'image-01',
    usage: '聊天内可用',
  },
  music: {
    label: '音乐',
    description: '用于独立音乐生成页的模型配置，当前版本先提供入口和状态。',
    defaultProvider: 'minimax',
    defaultModel: 'music-2.6',
    usage: '独立页面',
  },
  music_cover: {
    label: '翻唱模型',
    description: '上传参考音乐时使用的翻唱/参考音频模型，未启用时音乐页不能使用参考音乐。',
    defaultProvider: 'minimax',
    defaultModel: 'music-cover',
    usage: '音乐页参考音乐',
  },
  voice_clone: {
    label: '声音克隆',
    description: '从音频样本克隆出专属音色，可用于后续的语音合成。',
    defaultProvider: 'minimax',
    defaultModel: 'speech-2.8-hd',
    usage: '声音工程 · 声音克隆',
  },
  tts: {
    label: '语音合成',
    description: '文字转语音（TTS），支持使用系统、克隆或设计出来的音色。',
    defaultProvider: 'minimax',
    defaultModel: 'speech-2.8-hd',
    usage: '声音工程 · 语音合成',
  },
  voice_design: {
    label: '音色设计',
    description: '用文字描述生成全新音色，无需上传参考音频。',
    defaultProvider: 'minimax',
    defaultModel: 'speech-2.8-hd',
    usage: '声音工程 · 音色设计',
  },
  video: {
    label: '视频',
    description: '用于独立视频生成页的模型配置，当前版本先提供入口和状态。',
    defaultProvider: 'minimax',
    defaultModel: 'video-01',
    usage: '独立页面',
  },
};

const LEGACY_SECTION_META = [
  { id: 'models', title: '模型', copy: '管理提供商、API Key 和默认模型。' },
  { id: 'tools', title: '工具', copy: '管理搜索、代理、命令执行和安全边界。' },
  { id: 'mcp', title: 'MCP', copy: '管理 MCP 服务列表和工具可见范围。' },
  { id: 'runtime', title: '运行时', copy: '管理渠道进度、网关和心跳设置。' },
] as const;

const LEGACY_SEARCH_PROVIDER_OPTIONS = ['brave', 'tavily', 'duckduckgo', 'searxng', 'jina'];
const LEGACY_REASONING_OPTIONS = [
  { value: '', label: '关闭' },
  { value: 'low', label: '快速' },
  { value: 'medium', label: '平衡' },
  { value: 'high', label: '深度' },
];

void LEGACY_SECTION_META;
void LEGACY_SEARCH_PROVIDER_OPTIONS;
void LEGACY_REASONING_OPTIONS;

const SECTION_META = [
  { id: 'models', title: '模型', copy: '管理提供商、API Key 和默认模型。', group: 'core' },
  { id: 'tools', title: '工具', copy: '管理搜索、命令执行、上传和安全边界。', group: 'core' },
  { id: 'mcp', title: 'MCP', copy: '管理 MCP 服务列表和工具可见范围。', group: 'core' },
  { id: 'channels', title: '外部渠道', copy: '接入飞书、钉钉、企业微信等中国主流应用。', group: 'core' },
  { id: 'skills', title: '技能', copy: '启用或停用已安装的智能体技能。', group: 'core' },
  { id: 'runtime', title: '运行时', copy: '管理进度推送、网关和心跳设置。', group: 'core' },
  { id: 'memory', title: '记忆中心', copy: '查看长期记忆、当前上下文和近期归档。', group: 'workspace' },
  // 'automation' 仍然保留在 SECTION_META 里，让 SettingsModal initialSection
  // 能定位到 renderAutomationCenter；但下方左侧 nav 渲染时会过滤掉它，因为
  // 入口已经搬到主页侧边栏的「更多」菜单（mainView='tasks'）。
  { id: 'automation', title: '定时任务', copy: '统一管理自动化任务、结果投递和失败状态。', group: 'workspace' },
  { id: 'storage', title: '文件中心', copy: '管理上传文件、存储配额和清理策略。', group: 'workspace' },
] as const;

const HIDDEN_NAV_SECTIONS: ReadonlySet<string> = new Set(['automation']);

/** Capabilities that are MiniMax-only (audio / music pipelines). They get
 * grouped under a collapsible "MiniMax 音乐工程" header so the top-level
 * creative list shows only the multi-vendor capabilities (image / video). */
const MINIMAX_STUDIO_IDS: ReadonlySet<CreativeCapabilityKey> = new Set([
  'music',
  'music_cover',
  'voice_clone',
  'tts',
  'voice_design',
]);

const NAV_GROUPS: Array<{ id: 'core' | 'workspace'; label: string }> = [
  { id: 'core', label: '核心设置' },
  { id: 'workspace', label: '工作区管理' },
];

void NAV_GROUPS;

const SEARCH_PROVIDER_OPTIONS = ['brave', 'tavily', 'duckduckgo', 'searxng', 'jina'];
const REASONING_OPTIONS = [
  { value: '', label: '关闭' },
  { value: 'low', label: '快速' },
  { value: 'medium', label: '平衡' },
  { value: 'high', label: '深度' },
];

export type SectionId = (typeof SECTION_META)[number]['id'];
type TasksScheduleKind = 'every' | 'cron' | 'at';
type FixedCronPreset = 'daily' | 'weekdays' | 'weekly' | 'custom';
type StorageFilterMode = 'all' | 'referenced' | 'orphan';

const TASK_RESULTS_SESSION_ID = 'web:task-results';
const WEEKDAY_OPTIONS = [
  { value: '1', label: '周一' },
  { value: '2', label: '周二' },
  { value: '3', label: '周三' },
  { value: '4', label: '周四' },
  { value: '5', label: '周五' },
  { value: '6', label: '周六' },
  { value: '0', label: '周日' },
];

interface ProviderFormState {
  apiBase: string;
  apiKey: string;
  defaultModel: string;
  extraHeadersText: string;
}

interface CreativeCapabilityFormState {
  enabled: boolean;
  provider: string;
  apiBase: string;
  apiKey: string;
  model: string;
  extraHeadersText: string;
}

interface McpHeaderRow {
  id: string;
  key: string;
  value: string;
}

interface McpFormState {
  name: string;
  enabled: boolean;
  notes: string;
  icon: string;
  type: '' | 'stdio' | 'sse' | 'streamableHttp';
  command: string;
  argsText: string;
  envText: string;
  url: string;
  headerRows: McpHeaderRow[];
  toolTimeout: number;
  enabledToolsText: string;
}

interface NoticeState {
  tone: 'success' | 'error';
  text: string;
}

function formatTimestamp(value?: string | number | null): string {
  if (!value) {
    return '--';
  }
  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function countWords(content: string): number {
  return content
    .trim()
    .split(/\s+/)
    .filter(Boolean).length;
}

function memoryRoleLabel(role: string): string {
  if (role === 'user') return '用户';
  if (role === 'assistant') return 'TokenMind';
  if (role === 'tool') return '工具';
  return role;
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / 1024 ** exponent;
  return `${value >= 100 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`;
}

function truncateMiddle(value: string, maxLength: number): string {
  if (!value || value.length <= maxLength) {
    return value;
  }
  const keep = Math.max(6, maxLength - 3);
  const left = Math.ceil(keep / 2);
  const right = Math.floor(keep / 2);
  return `${value.slice(0, left)}...${value.slice(-right)}`;
}

function badgeLabel(file: StorageFileItem): string {
  if (file.category === 'markdown') return 'Markdown';
  if (file.category === 'spreadsheet') return '表格';
  if (file.category === 'presentation') return '演示';
  if (file.category === 'pdf') return 'PDF';
  if (file.category === 'image') return '图片';
  if (file.category === 'text') return '文本';
  return '文件';
}

function buildCronExpression(
  preset: FixedCronPreset,
  timeValue: string,
  customExpr: string,
  weekday: string
): string {
  if (preset === 'custom') {
    return customExpr.trim();
  }

  const [hourText = '9', minuteText = '0'] = timeValue.split(':');
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const safeHour = Number.isFinite(hour) ? hour : 9;
  const safeMinute = Number.isFinite(minute) ? minute : 0;

  if (preset === 'daily') {
    return `${safeMinute} ${safeHour} * * *`;
  }
  if (preset === 'weekdays') {
    return `${safeMinute} ${safeHour} * * 1-5`;
  }
  return `${safeMinute} ${safeHour} * * ${weekday}`;
}

function buildCronPreview(
  preset: FixedCronPreset,
  timeValue: string,
  timezone: string,
  weekday: string
): string {
  const zone = timezone.trim() || '本地时区';
  if (preset === 'daily') {
    return `每天 ${timeValue} (${zone})`;
  }
  if (preset === 'weekdays') {
    return `工作日 ${timeValue} (${zone})`;
  }
  if (preset === 'weekly') {
    const weekdayLabel =
      WEEKDAY_OPTIONS.find((option) => option.value === weekday)?.label || '周一';
    return `${weekdayLabel} ${timeValue} (${zone})`;
  }
  return `自定义 Cron (${zone})`;
}

function defaultAtValue(): string {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

function SettingsMarkdown({
  content,
  className = '',
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={`settings-markdown ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

interface SettingsModalProps {
  onClose?: () => void;
  onNavigateToSession?: (sessionId: string) => void;
  onNavigateBack?: () => void;
  /**
   * Pre-selected section. When this is one of the SECTION_META ids the
   * settings center opens directly on that page; combine with ``hideNav``
   * to embed a single section as a standalone page (e.g. 定时任务 lives
   * in the sidebar's "更多" menu but reuses this exact UI).
   */
  initialSection?: SectionId;
  /**
   * Hide the left-side section nav. The main panel still renders, so a
   * single section can be exposed as its own top-level page.
   */
  hideNav?: boolean;
}

function prettyJson(value?: Record<string, string> | null): string {
  if (!value || Object.keys(value).length === 0) {
    return '';
  }
  return JSON.stringify(value, null, 2);
}

function parseJsonObject(text: string, label: string): Record<string, string> {
  if (!text.trim()) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} 需要是合法的 JSON 对象`);
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} 需要是键值对对象`);
  }

  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [key, String(value)])
  );
}

function listToText(items: string[] = []): string {
  return items.join('\n');
}

function textToList(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildProviderForm(providerId: string, provider?: ProviderSettings): ProviderFormState {
  return {
    apiBase: provider?.api_base || PROVIDER_META[providerId]?.defaultApiBase || '',
    apiKey: '',
    defaultModel: provider?.default_model || PROVIDER_META[providerId]?.defaultModel || '',
    extraHeadersText: prettyJson(provider?.extra_headers),
  };
}

function buildCreativeCapabilityForm(
  capabilityId: CreativeCapabilityKey,
  capability?: CreativeCapabilitySettings | null
): CreativeCapabilityFormState {
  const fallback = createEmptyCreativeCapabilitySettings();
  const resolved = capability || fallback;
  return {
    enabled: resolved.enabled,
    provider: resolved.provider || CREATIVE_CAPABILITY_META[capabilityId].defaultProvider,
    apiBase: resolved.api_base || '',
    apiKey: '',
    model: resolved.model || CREATIVE_CAPABILITY_META[capabilityId].defaultModel,
    extraHeadersText: prettyJson(resolved.extra_headers),
  };
}

function nextHeaderRowId(): string {
  return `mcp-h-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function headersToRows(headers: Record<string, string> | null | undefined): McpHeaderRow[] {
  if (!headers || Object.keys(headers).length === 0) {
    return [];
  }
  return Object.entries(headers).map(([key, value]) => ({
    id: nextHeaderRowId(),
    key,
    value,
  }));
}

function rowsToHeaders(rows: McpHeaderRow[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const row of rows) {
    const trimmedKey = row.key.trim();
    if (!trimmedKey) {
      continue;
    }
    result[trimmedKey] = row.value;
  }
  return result;
}

function emptyMcpForm(): McpFormState {
  return {
    name: '',
    enabled: true,
    notes: '',
    icon: '',
    type: '',
    command: '',
    argsText: '',
    envText: '',
    url: '',
    headerRows: [],
    toolTimeout: 30,
    enabledToolsText: '*',
  };
}

function buildMcpForm(name: string, server?: McpServerSettings): McpFormState {
  if (!server) {
    return { ...emptyMcpForm(), name };
  }

  return {
    name,
    enabled: server.enabled ?? true,
    notes: server.notes || '',
    icon: server.icon || '',
    type: server.type || '',
    command: server.command,
    argsText: listToText(server.args),
    envText: prettyJson(server.env),
    url: server.url,
    headerRows: headersToRows(server.headers),
    toolTimeout: server.tool_timeout,
    enabledToolsText: listToText(server.enabled_tools),
  };
}

function getMcpConnectionTone(probe?: McpServerToolsState | null): 'connected' | 'error' | 'idle' {
  if (!probe) {
    return 'idle';
  }
  return probe.status === 'connected' ? 'connected' : 'error';
}

function getMcpConnectionLabel(probe?: McpServerToolsState | null): string {
  if (!probe) {
    return '未探测';
  }
  return probe.status === 'connected' ? '已连通' : '连接失败';
}

function isProviderConfigured(providerId: string, provider?: ProviderSettings): boolean {
  if (PROVIDER_META[providerId]?.mode === 'local') {
    return true;
  }
  if (providerId === 'custom') {
    return Boolean((provider?.api_key || '').trim() || (provider?.api_base || '').trim());
  }
  return Boolean((provider?.api_key || '').trim());
}

function Field({
  label,
  copy,
  children,
}: {
  label: string;
  copy?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="settings-field">
      <div>
        <div className="settings-field-title">{label}</div>
        {copy ? <div className="settings-field-copy">{copy}</div> : null}
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="settings-metric">
      <div className="settings-metric-label">{label}</div>
      <div className="settings-metric-value">{value}</div>
    </div>
  );
}

function ToggleRow({
  title,
  copy,
  value,
  onToggle,
}: {
  title: string;
  copy: string;
  value: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="settings-toggle-row">
      <div className="settings-toggle-text">
        <strong>{title}</strong>
        <span>{copy}</span>
      </div>
      <button
        className={`settings-toggle ${value ? 'on' : ''}`}
        onClick={onToggle}
        type="button"
      >
        {value ? '已开启' : '已关闭'}
      </button>
    </div>
  );
}

function SettingsNavIcon({ section }: { section: SectionId }) {
  if (section === 'models') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 7h16" />
        <path d="M4 12h10" />
        <path d="M4 17h13" />
        <circle cx="18" cy="12" r="2.5" />
      </svg>
    );
  }
  if (section === 'tools') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M14.7 6.3a4 4 0 1 0 3 3L22 13.6 19.6 16l-1.7-1.7-1.4 1.4-2.4-2.4a4 4 0 0 0-4.8-6Z" />
      </svg>
    );
  }
  if (section === 'mcp') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3.5" y="6" width="7" height="12" rx="2" />
        <rect x="13.5" y="4" width="7" height="16" rx="2" />
      </svg>
    );
  }
  if (section === 'channels') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    );
  }
  if (section === 'skills') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 2l2.5 5 5.5.8-4 3.9 1 5.5L12 14.8 7 17.2l1-5.5-4-3.9 5.5-.8z" />
      </svg>
    );
  }
  if (section === 'memory') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M5 6.5a2.5 2.5 0 0 1 2.5-2.5H19v16H7.5A2.5 2.5 0 0 0 5 22V6.5Z" />
        <path d="M5 17.5A2.5 2.5 0 0 1 7.5 15H19" />
      </svg>
    );
  }
  if (section === 'automation') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="4" y="5" width="16" height="15" rx="3" />
        <path d="M8 3v4" />
        <path d="M16 3v4" />
        <path d="M8 11h8" />
        <path d="M12 11v5" />
      </svg>
    );
  }
  if (section === 'storage') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 7.5C4 5.57 7.58 4 12 4s8 1.57 8 3.5S16.42 11 12 11 4 9.43 4 7.5Z" />
        <path d="M20 12.5c0 1.93-3.58 3.5-8 3.5s-8-1.57-8-3.5" />
        <path d="M20 7.5v9c0 1.93-3.58 3.5-8 3.5s-8-1.57-8-3.5v-9" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 3v5" />
      <path d="M12 16v5" />
      <path d="M4.93 4.93l3.54 3.54" />
      <path d="M15.53 15.53l3.54 3.54" />
      <path d="M3 12h5" />
      <path d="M16 12h5" />
      <path d="M4.93 19.07l3.54-3.54" />
      <path d="M15.53 8.47l3.54-3.54" />
    </svg>
  );
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  onClose,
  onNavigateToSession,
  onNavigateBack,
  initialSection,
  hideNav,
}) => {
  const {
    currentSession,
    sessions,
    fetchModelProviders,
    loadSessions,
    setCreativeCapabilities,
    setCurrentSession,
  } = useChatStore();
  const navigateToSession = (sessionId: string) => {
    if (onNavigateToSession) {
      onNavigateToSession(sessionId);
    } else {
      setCurrentSession(sessionId);
      onClose?.();
    }
  };
  const [selectedSection, setSelectedSection] = useState<SectionId>(initialSection || 'models');
  const [providers, setProviders] = useState<Record<string, ProviderSettings>>({});
  const [agentDraft, setAgentDraft] = useState<AgentSettings | null>(null);
  const [toolsDraft, setToolsDraft] = useState<ToolsSettings | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeSettings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState('openai');
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [providerForm, setProviderForm] = useState<ProviderFormState>(buildProviderForm('openai'));
  const [selectedMcpName, setSelectedMcpName] = useState<string | null>(null);
  const [mcpForm, setMcpForm] = useState<McpFormState>(emptyMcpForm());
  const [mcpEditorOpen, setMcpEditorOpen] = useState(false);
  const [mcpJsonImportOpen, setMcpJsonImportOpen] = useState(false);
  const [mcpJsonImportText, setMcpJsonImportText] = useState('');
  const [mcpJsonImportError, setMcpJsonImportError] = useState<string | null>(null);
  const [mcpAdvancedOpen, setMcpAdvancedOpen] = useState(false);
  const [searchApiKeyMasked, setSearchApiKeyMasked] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingSection, setSavingSection] = useState<string | null>(null);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [creativeDraft, setCreativeDraft] = useState<CreativeSettings | null>(null);
  const [selectedCreativeId, setSelectedCreativeId] = useState<CreativeCapabilityKey>('image');
  const [minimaxStudioExpanded, setMinimaxStudioExpanded] = useState(false);
  const [editingCreativeId, setEditingCreativeId] = useState<CreativeCapabilityKey | null>(null);
  const [creativeForm, setCreativeForm] = useState<CreativeCapabilityFormState>(
    buildCreativeCapabilityForm('image')
  );
  const [mcpCatalog, setMcpCatalog] = useState<Record<string, McpServerToolsState>>({});
  const [loadingMcpCatalog, setLoadingMcpCatalog] = useState(false);
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [skillSuggestions, setSkillSuggestions] = useState<SkillSuggestion[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [togglingSkill, setTogglingSkill] = useState<string | null>(null);
  const [skillSuggestionBusy, setSkillSuggestionBusy] = useState<string | null>(null);
  const [selectedSkillSuggestion, setSelectedSkillSuggestion] = useState<SkillSuggestion | null>(null);
  const [memoryOverview, setMemoryOverview] = useState<MemoryOverviewResponse | null>(null);
  const [memoryDraft, setMemoryDraft] = useState('');
  const [memoryArchiveQuery, setMemoryArchiveQuery] = useState('');
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memorySaving, setMemorySaving] = useState(false);
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [cronStatus, setCronStatus] = useState<CronStatus | null>(null);
  const [cronLoading, setCronLoading] = useState(false);
  const [cronActioningId, setCronActioningId] = useState<string | null>(null);
  const [storageOverview, setStorageOverview] = useState<StorageOverviewResponse | null>(null);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageQuery, setStorageQuery] = useState('');
  const [storageFilterMode, setStorageFilterMode] = useState<StorageFilterMode>('all');
  const [storageActionPath, setStorageActionPath] = useState<string | null>(null);
  const [taskName, setTaskName] = useState('');
  const [taskMessage, setTaskMessage] = useState('');
  const [taskEnabled, setTaskEnabled] = useState(true);
  const [scheduleKind, setScheduleKind] = useState<TasksScheduleKind>('cron');
  const [fixedCronPreset, setFixedCronPreset] = useState<FixedCronPreset>('daily');
  const [everySeconds, setEverySeconds] = useState(3600);
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [fixedTime, setFixedTime] = useState('09:00');
  const [weeklyDay, setWeeklyDay] = useState('1');
  const [taskTimezone, setTaskTimezone] = useState('Asia/Shanghai');
  const [taskAtValue, setTaskAtValue] = useState(defaultAtValue());
  const [taskTargetSessionId, setTaskTargetSessionId] = useState(TASK_RESULTS_SESSION_ID);
  const [cronTab, setCronTab] = useState<'scheduled' | 'completed'>('scheduled');
  const [cronEditorOpen, setCronEditorOpen] = useState(false);
  const [editingCronJobId, setEditingCronJobId] = useState<string | null>(null);
  const [cronAdvancedOpen, setCronAdvancedOpen] = useState(false);
  const [cronMenuOpenId, setCronMenuOpenId] = useState<string | null>(null);
  const [toolsCategory, setToolsCategory] = useState<
    'search' | 'exec' | 'audit' | 'uploads' | 'knowledge' | null
  >(null);
  const [editingKnowledgeModelKind, setEditingKnowledgeModelKind] = useState<
    'embedding' | 'rerank' | 'vlm' | null
  >(null);
  const [channelCatalog, setChannelCatalog] = useState<ChannelCatalogEntry[] | null>(null);
  const [channelLoading, setChannelLoading] = useState(false);
  const [channelEditorName, setChannelEditorName] = useState<ChannelName | null>(null);
  const [channelDraft, setChannelDraft] = useState<Record<string, unknown>>({});
  const [channelSavingName, setChannelSavingName] = useState<ChannelName | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        await loadSessions();
        const data = await api.getConfig();
        setProviders(data.providers);
        setCreativeDraft(data.creative);
        setCreativeCapabilities(data.creative);
        setAgentDraft(data.agent);
        setRuntimeDraft(data.runtime);
        setSearchApiKeyMasked(data.tools.web.search.api_key || '');
        setToolsDraft({
          ...data.tools,
          web: {
            ...data.tools.web,
            search: {
              ...data.tools.web.search,
              api_key: '',
            },
          },
          // Fill in defaults for any knowledge field the backend hasn't sent
          // yet — guards against the user upgrading the frontend before
          // restarting an older backend. The cast lets TS accept the spread
          // even though KnowledgeSettings declares vlm_* as required (we're
          // explicitly defending against a server that hasn't been told yet).
          knowledge: Object.assign(
            {
              vlm_model: '',
              vlm_api_key: '',
              vlm_api_base: null as string | null,
              vlm_timeout: 30,
              vlm_max_dim: 1280,
              vlm_max_workers: 8,
            },
            data.tools.knowledge,
          ),
        });

        const providerKeys = Object.keys(PROVIDER_META);
        const nextProvider =
          (data.agent.provider && data.providers[data.agent.provider] ? data.agent.provider : '') ||
          providerKeys.find((id) => data.providers[id]) ||
          providerKeys[0];
        setSelectedProviderId(nextProvider);
        setProviderForm(buildProviderForm(nextProvider, data.providers[nextProvider]));
        setCreativeForm(buildCreativeCapabilityForm('image', data.creative.image));

        // Card-based MCP UI: no server is auto-edited on load.
        setSelectedMcpName(null);
        setMcpForm(emptyMcpForm());
      } catch (error) {
        setNotice({
          tone: 'error',
          text: error instanceof Error ? error.message : '加载配置失败',
        });
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [loadSessions]);

  useEffect(() => {
    if (!notice) {
      return;
    }

    const timer = window.setTimeout(() => {
      setNotice(null);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    setNotice(null);
  }, [selectedSection]);

  useEffect(() => {
    setProviderForm(buildProviderForm(selectedProviderId, providers[selectedProviderId]));
  }, [providers, selectedProviderId]);

  useEffect(() => {
    if (!toolsDraft) {
      return;
    }

    if (!selectedMcpName) {
      setMcpForm(emptyMcpForm());
      return;
    }

    setMcpForm(buildMcpForm(selectedMcpName, toolsDraft.mcp_servers[selectedMcpName]));
  }, [selectedMcpName, toolsDraft]);

  const providerCards = useMemo(() => {
    return Object.keys(PROVIDER_META)
      .map((id) => {
        const provider = providers[id];
        return {
          id,
          label: PROVIDER_META[id].label,
          active: agentDraft?.provider === id,
          configured: isProviderConfigured(id, provider),
          model: provider?.default_model || PROVIDER_META[id].defaultModel,
          endpoint: provider?.api_base || provider?.api_key || '未填写',
        };
      })
      .sort((left, right) => {
        if (left.active !== right.active) {
          return left.active ? -1 : 1;
        }
        if (left.configured !== right.configured) {
          return left.configured ? -1 : 1;
        }
        return left.label.localeCompare(right.label);
      });
  }, [agentDraft?.provider, providers]);

  const creativeCards = useMemo(() => {
    return (Object.keys(CREATIVE_CAPABILITY_META) as CreativeCapabilityKey[]).map((id) => {
      const capability = creativeDraft?.[id] || createEmptyCreativeCapabilitySettings();
      return {
        id,
        label: CREATIVE_CAPABILITY_META[id].label,
        description: CREATIVE_CAPABILITY_META[id].description,
        usage: CREATIVE_CAPABILITY_META[id].usage,
        enabled: capability.enabled,
        configured: isCreativeCapabilityConfigured(capability),
        provider: capability.provider || '未配置',
        model: capability.model || '未配置',
      };
    });
  }, [creativeDraft]);

  const minimaxStudioCards = useMemo(
    () => creativeCards.filter((capability) => MINIMAX_STUDIO_IDS.has(capability.id)),
    [creativeCards],
  );

  type CapabilityCard = (typeof creativeCards)[number];
  const renderCapabilityCard = (capability: CapabilityCard) => (
    <div
      className={`settings-provider-card ${capability.enabled ? 'active' : ''} ${
        selectedCreativeId === capability.id ? 'is-selected' : ''
      }`}
      key={capability.id}
    >
      <div className="settings-provider-head">
        <div>
          <div className="settings-provider-name">{capability.label}</div>
          <div className="settings-badges">
            <span className="settings-badge">
              {capability.configured ? '已配置' : '未配置'}
            </span>
            <span className={`settings-badge ${capability.enabled ? 'active' : ''}`}>
              {capability.enabled ? '已启用' : '未启用'}
            </span>
            <span className="settings-badge">{capability.usage}</span>
          </div>
        </div>
      </div>
      <div className="settings-provider-desc">
        <div>{capability.description}</div>
        <div>
          {capability.provider} / {capability.model}
        </div>
      </div>
      <div className="settings-provider-actions">
        <button
          className="settings-button-secondary"
          onClick={() => openCreativeEditor(capability.id)}
          type="button"
        >
          配置能力
        </button>
        <button
          className="settings-button"
          disabled={savingSection === `creative-${capability.id}` || !capability.configured}
          onClick={() => void handleToggleCreativeCapability(capability.id, !capability.enabled)}
          type="button"
        >
          {capability.enabled ? '停用' : '启用'}
        </button>
      </div>
    </div>
  );

  const mcpEntries = useMemo(
    () => Object.entries(toolsDraft?.mcp_servers || {}).sort(([a], [b]) => a.localeCompare(b)),
    [toolsDraft]
  );

  const currentProviderLabel =
    (agentDraft?.provider && PROVIDER_META[agentDraft.provider]?.label) ||
    agentDraft?.provider ||
    'auto';

  const currentSectionMeta =
    SECTION_META.find((section) => section.id === selectedSection) || SECTION_META[0];
  const memoryDraftDirty = memoryOverview ? memoryDraft !== memoryOverview.long_term.content : false;
  const longTermMeta = useMemo(
    () => ({
      characters: memoryDraft.length,
      words: countWords(memoryDraft),
    }),
    [memoryDraft]
  );
  const cronGeneratedExpr = useMemo(
    () => buildCronExpression(fixedCronPreset, fixedTime, cronExpr, weeklyDay),
    [fixedCronPreset, fixedTime, cronExpr, weeklyDay]
  );
  const cronPreview = useMemo(
    () => buildCronPreview(fixedCronPreset, fixedTime, taskTimezone, weeklyDay),
    [fixedCronPreset, fixedTime, taskTimezone, weeklyDay]
  );
  const cronJobsByTab = useMemo(() => {
    const now = Date.now();
    const scheduled: CronJob[] = [];
    const completed: CronJob[] = [];
    for (const job of cronJobs) {
      const isOneOffPast =
        job.schedule.kind === 'at' && (job.schedule.at_ms ?? 0) > 0 && (job.schedule.at_ms ?? 0) <= now;
      if (isOneOffPast) {
        completed.push(job);
      } else {
        scheduled.push(job);
      }
    }
    const sortByNextRun = (list: CronJob[]) =>
      [...list].sort(
        (a, b) =>
          (a.state.next_run_at_ms || a.schedule.at_ms || 0) -
          (b.state.next_run_at_ms || b.schedule.at_ms || 0),
      );
    return { scheduled: sortByNextRun(scheduled), completed: sortByNextRun(completed) };
  }, [cronJobs]);
  const visibleCronJobs = cronTab === 'scheduled' ? cronJobsByTab.scheduled : cronJobsByTab.completed;
  const availableTargetSessions = useMemo(
    () =>
      sessions.filter((session) => {
        if (session.session_id === TASK_RESULTS_SESSION_ID) return false;
        if (session.message_count > 0) return true;
        if (session.title?.trim() || session.first_message?.trim()) return true;
        return false;
      }),
    [sessions]
  );
  const sessionOptions = useMemo(
    () =>
      availableTargetSessions.map((session) => ({
        id: session.session_id,
        label: session.title || session.first_message || session.session_id,
      })),
    [availableTargetSessions]
  );
  const storageUsagePercent = useMemo(() => {
    if (!storageOverview || storageOverview.summary.quota_bytes <= 0) return 0;
    return Math.min(
      100,
      Math.round((storageOverview.summary.used_bytes / storageOverview.summary.quota_bytes) * 100)
    );
  }, [storageOverview]);
  const filteredStorageFiles = useMemo(() => {
    if (!storageOverview) return [];
    const normalizedQuery = storageQuery.trim().toLowerCase();
    return storageOverview.files.filter((file) => {
      if (storageFilterMode === 'referenced' && !file.referenced) return false;
      if (storageFilterMode === 'orphan' && file.referenced) return false;
      if (!normalizedQuery) return true;
      const haystack = `${file.name} ${file.path} ${file.category} ${file.referenced_by
        .map((item) => item.title)
        .join(' ')}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [storageFilterMode, storageOverview, storageQuery]);

  const setSuccess = (text: string) => setNotice({ tone: 'success', text });
  const setFailure = (error: unknown, fallback: string) =>
    setNotice({
      tone: 'error',
      text: error instanceof Error ? error.message : fallback,
    });

  const loadSkills = async () => {
    setSkillsLoading(true);
    setSkillsError(null);
    try {
      const [items, suggestions] = await Promise.all([
        api.listSkills(),
        api.listSkillSuggestions(),
      ]);
      setSkills(items);
      setSkillSuggestions(suggestions);
    } catch (error) {
      setSkillsError(error instanceof Error ? error.message : '加载技能失败');
    } finally {
      setSkillsLoading(false);
    }
  };

  const toggleSkillEnabled = async (skill: SkillSummary, next: boolean) => {
    setTogglingSkill(skill.name);
    try {
      const updated = await api.setSkillEnabled(skill.name, next);
      setSkills((prev) =>
        prev ? prev.map((item) => (item.name === updated.name ? updated : item)) : prev,
      );
      setNotice({
        tone: 'success',
        text: next ? `已启用 ${skill.name}` : `已停用 ${skill.name}`,
      });
    } catch (error) {
      setFailure(error, '切换技能状态失败');
    } finally {
      setTogglingSkill(null);
    }
  };

  const approveSkillSuggestion = async (suggestion: SkillSuggestion) => {
    setSkillSuggestionBusy(suggestion.id);
    try {
      await api.approveSkillSuggestion(suggestion.id);
      setSelectedSkillSuggestion(null);
      setSuccess(`已确认技能建议：${suggestion.name}`);
    } catch (error) {
      setFailure(error, '确认技能建议失败');
      setSkillSuggestionBusy(null);
      return;
    }
    setSkillSuggestionBusy(null);
    void loadSkills();
  };

  const rejectSkillSuggestion = async (suggestion: SkillSuggestion) => {
    setSkillSuggestionBusy(suggestion.id);
    try {
      await api.rejectSkillSuggestion(suggestion.id);
      setSkillSuggestions((prev) => prev.filter((item) => item.id !== suggestion.id));
      setSelectedSkillSuggestion((current) => (current?.id === suggestion.id ? null : current));
      setSuccess(`已忽略技能建议：${suggestion.name}`);
    } catch (error) {
      setFailure(error, '忽略技能建议失败');
    } finally {
      setSkillSuggestionBusy(null);
    }
  };

  const loadMemoryOverview = async (query = memoryArchiveQuery, syncDraft = false) => {
    setMemoryLoading(true);
    try {
      const response = await api.getMemoryOverview(currentSession, query);
      setMemoryOverview(response);
      if (syncDraft || !memoryDraftDirty) {
        setMemoryDraft(response.long_term.content);
      }
    } catch (error) {
      setFailure(error, '加载记忆中心失败');
    } finally {
      setMemoryLoading(false);
    }
  };

  const loadAutomationData = async (silent = false) => {
    if (!silent) {
      setCronLoading(true);
    }
    try {
      const [jobsData, statusData] = await Promise.all([api.listCronJobs(true), api.getCronStatus()]);
      setCronJobs(jobsData);
      setCronStatus(statusData);
    } catch (error) {
      setFailure(error, '加载定时任务失败');
    } finally {
      setCronLoading(false);
    }
  };

  const loadStorageData = async (silent = false) => {
    if (!silent) {
      setStorageLoading(true);
    }
    try {
      const response = await api.getStorageOverview();
      setStorageOverview(response);
    } catch (error) {
      setFailure(error, '加载文件中心失败');
    } finally {
      setStorageLoading(false);
    }
  };

  const loadChannels = async () => {
    setChannelLoading(true);
    try {
      const data = await api.listChannels();
      setChannelCatalog(data.channels);
    } catch (error) {
      setFailure(error, '加载渠道列表失败');
    } finally {
      setChannelLoading(false);
    }
  };

  const loadMcpCatalog = async (silent = false) => {
    if (!toolsDraft || Object.keys(toolsDraft.mcp_servers).length === 0) {
      setMcpCatalog({});
      return;
    }

    setLoadingMcpCatalog(true);
    try {
      const response = await api.getMcpTools();
      setMcpCatalog(response.servers);
    } catch (error) {
      setMcpCatalog({});
      if (!silent) {
        setFailure(error, '加载 MCP 工具列表失败');
      }
    } finally {
      setLoadingMcpCatalog(false);
    }
  };

  useEffect(() => {
    if (selectedSection !== 'mcp' || loading || !toolsDraft) {
      return;
    }

    void loadMcpCatalog(true);
  }, [selectedSection, loading, toolsDraft]);

  useEffect(() => {
    if (loading) {
      return;
    }

    if (selectedSection === 'memory' && !memoryOverview && !memoryLoading) {
      void loadMemoryOverview(memoryArchiveQuery, true);
      return;
    }

    if (selectedSection === 'automation' && !cronStatus && !cronLoading) {
      void loadAutomationData();
      return;
    }

    if (selectedSection === 'storage' && !storageOverview && !storageLoading) {
      void loadStorageData();
    }

    if (selectedSection === 'skills' && !skills && !skillsLoading) {
      void loadSkills();
    }

    if (selectedSection === 'channels' && channelCatalog === null && !channelLoading) {
      void loadChannels();
    }
  }, [
    selectedSection,
    loading,
    memoryOverview,
    memoryLoading,
    memoryArchiveQuery,
    cronStatus,
    cronLoading,
    storageOverview,
    channelCatalog,
    channelLoading,
    storageLoading,
    skills,
    skillsLoading,
  ]);

  useEffect(() => {
    if (selectedSection !== 'memory' || !memoryOverview) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadMemoryOverview(memoryArchiveQuery, false);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [memoryArchiveQuery, currentSession, selectedSection]);

  useEffect(() => {
    if (loading || selectedSection !== 'automation') {
      return;
    }

    const timer = window.setInterval(() => {
      void loadAutomationData(true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loading, selectedSection]);

  const openProviderEditor = (providerId: string) => {
    setSelectedProviderId(providerId);
    setEditingProviderId(providerId);
  };

  const openCreativeEditor = (capabilityId: CreativeCapabilityKey) => {
    setSelectedCreativeId(capabilityId);
    setEditingCreativeId(capabilityId);
    setCreativeForm(buildCreativeCapabilityForm(capabilityId, creativeDraft?.[capabilityId]));
  };

  const closeProviderEditor = () => {
    setEditingProviderId(null);
  };

  const closeCreativeEditor = () => {
    setEditingCreativeId(null);
  };

  const handleActivateProvider = async (providerId: string) => {
    const provider = providers[providerId];
    const model =
      provider?.default_model || PROVIDER_META[providerId]?.defaultModel || agentDraft?.model || '';

    setSavingSection('models');
    setNotice(null);
    try {
      const response = await api.updateDefaults({ provider: providerId, model });
      setAgentDraft((current) =>
        current
          ? {
              ...current,
              provider: response.defaults.provider,
              model: response.defaults.model,
            }
          : current
      );
      await fetchModelProviders();
      setSuccess(`默认提供商已切换为 ${PROVIDER_META[providerId]?.label || providerId}`);
    } catch (error) {
      setFailure(error, '切换默认提供商失败');
    } finally {
      setSavingSection(null);
    }
  };

  const persistModelDefaults = async (draft: AgentSettings) => {
    const response = await api.updateAgentConfig({
      ...draft,
      reasoning_effort: draft.reasoning_effort || null,
    });
    setAgentDraft(response.agent);
    return response.agent;
  };

  const handleSaveProvider = async () => {
    setSavingSection('models');
    setNotice(null);
    try {
      const response = await api.updateProviderConfig(selectedProviderId, {
        api_base: providerForm.apiBase.trim() || null,
        default_model: providerForm.defaultModel.trim() || null,
        extra_headers: parseJsonObject(providerForm.extraHeadersText, 'Extra Headers'),
        ...(providerForm.apiKey.trim() ? { api_key: providerForm.apiKey.trim() } : {}),
      });

      setProviders((current) => ({
        ...current,
        [selectedProviderId]: response.config,
      }));
      setProviderForm((current) => ({
        ...current,
        apiKey: '',
        extraHeadersText: prettyJson(response.config.extra_headers),
      }));
      if (agentDraft) {
        await persistModelDefaults({
          ...agentDraft,
          provider: response.defaults.provider,
          model: response.defaults.model,
        });
      }
      setEditingProviderId(null);
      await fetchModelProviders();
      setSuccess(`${PROVIDER_META[selectedProviderId]?.label || selectedProviderId} 模型配置已保存`);
    } catch (error) {
      setFailure(error, '保存模型配置失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleSaveCreativeCapability = async () => {
    if (!editingCreativeId || !creativeDraft) {
      return;
    }

    setSavingSection('creative');
    setNotice(null);
    try {
      const response = await api.updateCreativeCapability(editingCreativeId, {
        enabled: creativeForm.enabled,
        provider: creativeForm.provider.trim(),
        api_base: creativeForm.apiBase.trim() || null,
        model: creativeForm.model.trim(),
        extra_headers: parseJsonObject(creativeForm.extraHeadersText, 'Creative Extra Headers'),
        ...(creativeForm.apiKey.trim() ? { api_key: creativeForm.apiKey.trim() } : {}),
      });

      setCreativeDraft((current) =>
        current
          ? {
              ...current,
              [editingCreativeId]: response.config,
            }
          : current
      );
      setCreativeCapabilities({
        ...(creativeDraft || ({} as CreativeSettings)),
        [editingCreativeId]: response.config,
      } as CreativeSettings);
      setCreativeForm((current) => ({
        ...current,
        apiKey: '',
        extraHeadersText: prettyJson(response.config.extra_headers),
      }));
      setEditingCreativeId(null);
      setSuccess(`${CREATIVE_CAPABILITY_META[editingCreativeId].label} 能力配置已保存`);
    } catch (error) {
      setFailure(error, '保存创作能力配置失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleToggleCreativeCapability = async (
    capabilityId: CreativeCapabilityKey,
    enabled: boolean
  ) => {
    if (!creativeDraft) {
      return;
    }

    setSavingSection(`creative-${capabilityId}`);
    setNotice(null);
    try {
      const response = await api.updateCreativeCapability(capabilityId, { enabled });
      setCreativeDraft((current) =>
        current
          ? {
              ...current,
              [capabilityId]: response.config,
            }
          : current
      );
      setCreativeCapabilities({
        ...(creativeDraft || ({} as CreativeSettings)),
        [capabilityId]: response.config,
      } as CreativeSettings);
      setSuccess(
        `${CREATIVE_CAPABILITY_META[capabilityId].label}${enabled ? ' 已启用' : ' 已停用'}`
      );
    } catch (error) {
      setFailure(error, '更新创作能力状态失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleSaveTools = async () => {
    if (!toolsDraft) {
      return;
    }

    setSavingSection('tools');
    setNotice(null);
    try {
      const response = await api.updateToolsConfig({
        audit_enabled: toolsDraft.audit_enabled,
        restrict_to_workspace: toolsDraft.restrict_to_workspace,
        web: {
          proxy: toolsDraft.web.proxy || '',
          search: {
            provider: toolsDraft.web.search.provider,
            ...(toolsDraft.web.search.api_key.trim()
              ? { api_key: toolsDraft.web.search.api_key.trim() }
              : {}),
            base_url: toolsDraft.web.search.base_url || '',
            max_results: toolsDraft.web.search.max_results,
          },
        },
        exec: {
          timeout: toolsDraft.exec.timeout,
          path_append: toolsDraft.exec.path_append,
          confirm_high_risk: toolsDraft.exec.confirm_high_risk,
          approval_timeout_s: toolsDraft.exec.approval_timeout_s,
        },
        uploads: {
          max_file_mb: toolsDraft.uploads.max_file_mb,
          max_total_mb: toolsDraft.uploads.max_total_mb,
          retention_days: toolsDraft.uploads.retention_days,
          cleanup_interval_hours: toolsDraft.uploads.cleanup_interval_hours,
        },
        knowledge: {
          vector_backend: toolsDraft.knowledge.vector_backend,
          chunk_size: toolsDraft.knowledge.chunk_size,
          chunk_overlap: toolsDraft.knowledge.chunk_overlap,
          top_k: toolsDraft.knowledge.top_k,
          embedding_model: toolsDraft.knowledge.embedding_model,
          ...(toolsDraft.knowledge.embedding_api_key.trim()
            ? { embedding_api_key: toolsDraft.knowledge.embedding_api_key.trim() }
            : {}),
          embedding_api_base: toolsDraft.knowledge.embedding_api_base || '',
          rerank_model: toolsDraft.knowledge.rerank_model,
          ...(toolsDraft.knowledge.rerank_api_key.trim()
            ? { rerank_api_key: toolsDraft.knowledge.rerank_api_key.trim() }
            : {}),
          rerank_api_base: toolsDraft.knowledge.rerank_api_base || '',
          rerank_top_n: toolsDraft.knowledge.rerank_top_n,
          vlm_model: toolsDraft.knowledge.vlm_model,
          ...(toolsDraft.knowledge.vlm_api_key.trim()
            ? { vlm_api_key: toolsDraft.knowledge.vlm_api_key.trim() }
            : {}),
          vlm_api_base: toolsDraft.knowledge.vlm_api_base || '',
          vlm_timeout: toolsDraft.knowledge.vlm_timeout,
          vlm_max_dim: toolsDraft.knowledge.vlm_max_dim,
          vlm_max_workers: toolsDraft.knowledge.vlm_max_workers,
        },
      });

      setSearchApiKeyMasked(response.tools.web.search.api_key || '');
      setToolsDraft((current) =>
        current
          ? {
              ...current,
              ...response.tools,
              mcp_servers: current.mcp_servers,
              web: {
                ...response.tools.web,
                search: {
                  ...response.tools.web.search,
                  api_key: '',
                },
              },
              knowledge: {
                // Keep prior values as a fallback so an older backend that
                // doesn't echo back the vlm_* fields can't strip the
                // defaults we initialised them with.
                ...current.knowledge,
                ...response.tools.knowledge,
                embedding_api_key: '',
                rerank_api_key: '',
                vlm_api_key: '',
              },
            }
          : current
      );
      setSuccess('工具配置已保存');
    } catch (error) {
      setFailure(error, '保存工具配置失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleSaveKnowledgeModels = async () => {
    if (!toolsDraft) return;
    setSavingSection('knowledge-models');
    setNotice(null);
    try {
      // Partial update: only the embedding/rerank/vlm model fields. The
      // backend looks at model_fields_set so chunking, vector_backend, top_k
      // stay untouched.
      const response = await api.updateToolsConfig({
        knowledge: {
          embedding_model: toolsDraft.knowledge.embedding_model,
          ...(toolsDraft.knowledge.embedding_api_key.trim()
            ? { embedding_api_key: toolsDraft.knowledge.embedding_api_key.trim() }
            : {}),
          embedding_api_base: toolsDraft.knowledge.embedding_api_base || '',
          rerank_model: toolsDraft.knowledge.rerank_model,
          ...(toolsDraft.knowledge.rerank_api_key.trim()
            ? { rerank_api_key: toolsDraft.knowledge.rerank_api_key.trim() }
            : {}),
          rerank_api_base: toolsDraft.knowledge.rerank_api_base || '',
          rerank_top_n: toolsDraft.knowledge.rerank_top_n,
          vlm_model: toolsDraft.knowledge.vlm_model,
          ...(toolsDraft.knowledge.vlm_api_key.trim()
            ? { vlm_api_key: toolsDraft.knowledge.vlm_api_key.trim() }
            : {}),
          vlm_api_base: toolsDraft.knowledge.vlm_api_base || '',
          vlm_timeout: toolsDraft.knowledge.vlm_timeout,
          vlm_max_dim: toolsDraft.knowledge.vlm_max_dim,
          vlm_max_workers: toolsDraft.knowledge.vlm_max_workers,
        },
      });
      setToolsDraft((current) =>
        current
          ? {
              ...current,
              knowledge: {
                ...current.knowledge,
                ...response.tools.knowledge,
                // Don't pull persisted secrets back into the draft — keep
                // the input field empty so the placeholder reads cleanly.
                embedding_api_key: '',
                rerank_api_key: '',
                vlm_api_key: '',
              },
            }
          : current,
      );
      setSuccess('知识库模型配置已保存');
    } catch (error) {
      setFailure(error, '保存知识库模型失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleSaveRuntime = async () => {
    if (!runtimeDraft) {
      return;
    }

    setSavingSection('runtime');
    setNotice(null);
    try {
      const response = await api.updateRuntimeConfig(runtimeDraft);
      setRuntimeDraft(response.runtime);
      setSuccess('运行时配置已保存，部分设置需要重启服务后生效');
    } catch (error) {
      setFailure(error, '保存运行时配置失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleSaveMcp = async () => {
    if (!toolsDraft) {
      return;
    }

    const nextName = mcpForm.name.trim();
    if (!nextName) {
      setNotice({ tone: 'error', text: 'MCP 服务名称不能为空' });
      return;
    }

    setSavingSection('mcp');
    setNotice(null);
    try {
      const response = await api.upsertMcpServer(nextName, {
        enabled: mcpForm.enabled,
        notes: mcpForm.notes,
        icon: mcpForm.icon.trim(),
        type: mcpForm.type || null,
        command: mcpForm.command.trim(),
        args: textToList(mcpForm.argsText),
        env: parseJsonObject(mcpForm.envText, 'Env'),
        url: mcpForm.url.trim(),
        headers: rowsToHeaders(mcpForm.headerRows),
        tool_timeout: mcpForm.toolTimeout,
        enabled_tools: textToList(mcpForm.enabledToolsText),
      });

      if (selectedMcpName && selectedMcpName !== nextName) {
        await api.deleteMcpServer(selectedMcpName);
      }

      setToolsDraft((current) => {
        if (!current) {
          return current;
        }
        const nextServers = { ...current.mcp_servers };
        if (selectedMcpName && selectedMcpName !== nextName) {
          delete nextServers[selectedMcpName];
        }
        nextServers[nextName] = response.server;
        return {
          ...current,
          mcp_servers: nextServers,
        };
      });
      setSelectedMcpName(nextName);
      setMcpEditorOpen(false);
      setSuccess(`MCP 服务 ${nextName} 已保存`);
    } catch (error) {
      setFailure(error, '保存 MCP 服务失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleDeleteMcp = async (targetName?: string) => {
    if (!toolsDraft) {
      return;
    }
    const nameToDelete = targetName ?? selectedMcpName;
    if (!nameToDelete) {
      return;
    }

    setSavingSection('mcp');
    setNotice(null);
    try {
      await api.deleteMcpServer(nameToDelete);
      const nextServers = { ...toolsDraft.mcp_servers };
      delete nextServers[nameToDelete];

      setToolsDraft({
        ...toolsDraft,
        mcp_servers: nextServers,
      });
      if (selectedMcpName === nameToDelete) {
        setSelectedMcpName(null);
        setMcpForm(emptyMcpForm());
        setMcpEditorOpen(false);
      }
      setSuccess(`MCP 服务 ${nameToDelete} 已删除`);
    } catch (error) {
      setFailure(error, '删除 MCP 服务失败');
    } finally {
      setSavingSection(null);
    }
  };

  const openMcpEditor = (name: string | null) => {
    if (!toolsDraft) {
      return;
    }
    if (name && toolsDraft.mcp_servers[name]) {
      setSelectedMcpName(name);
      setMcpForm(buildMcpForm(name, toolsDraft.mcp_servers[name]));
    } else {
      setSelectedMcpName(null);
      setMcpForm(emptyMcpForm());
    }
    setMcpAdvancedOpen(false);
    setMcpEditorOpen(true);
  };

  const closeMcpEditor = () => {
    setMcpEditorOpen(false);
    setSelectedMcpName(null);
    setMcpForm(emptyMcpForm());
  };

  const handleToggleMcpEnabled = async (name: string, enabled: boolean) => {
    if (!toolsDraft) {
      return;
    }
    setNotice(null);
    try {
      const response = await api.upsertMcpServer(name, { enabled });
      setToolsDraft((current) =>
        current
          ? {
              ...current,
              mcp_servers: { ...current.mcp_servers, [name]: response.server },
            }
          : current,
      );
      setSuccess(`MCP 服务 ${name} 已${enabled ? '启用' : '停用'}`);
    } catch (error) {
      setFailure(error, '切换 MCP 服务状态失败');
    }
  };

  const openChannelEditor = (entry: ChannelCatalogEntry) => {
    setChannelEditorName(entry.name);
    setChannelDraft({ ...entry.config });
  };

  const closeChannelEditor = () => {
    setChannelEditorName(null);
    setChannelDraft({});
  };

  const handleSaveChannel = async () => {
    if (!channelEditorName) {
      return;
    }
    setChannelSavingName(channelEditorName);
    setNotice(null);
    try {
      const response = await api.updateChannel(channelEditorName, channelDraft);
      setChannelCatalog((current) =>
        current
          ? current.map((entry) =>
              entry.name === channelEditorName
                ? { ...entry, config: response.config, enabled: !!response.config.enabled }
                : entry,
            )
          : current,
      );
      const label =
        channelCatalog?.find((entry) => entry.name === channelEditorName)?.label ||
        channelEditorName;
      setSuccess(`${label} 渠道已保存`);
      closeChannelEditor();
    } catch (error) {
      setFailure(error, '保存渠道失败');
    } finally {
      setChannelSavingName(null);
    }
  };

  const handleToggleChannel = async (entry: ChannelCatalogEntry, enabled: boolean) => {
    setChannelSavingName(entry.name);
    setNotice(null);
    try {
      const response = await api.updateChannel(entry.name, { enabled });
      setChannelCatalog((current) =>
        current
          ? current.map((item) =>
              item.name === entry.name
                ? { ...item, config: response.config, enabled: !!response.config.enabled }
                : item,
            )
          : current,
      );
      setSuccess(`${entry.label} 已${enabled ? '启用' : '停用'}`);
    } catch (error) {
      setFailure(error, '切换渠道状态失败');
    } finally {
      setChannelSavingName(null);
    }
  };

  const handleApplyMcpJsonImport = async () => {
    if (!toolsDraft) {
      return;
    }
    const trimmed = mcpJsonImportText.trim();
    if (!trimmed) {
      setMcpJsonImportError('请粘贴 JSON 内容');
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch (error) {
      setMcpJsonImportError(error instanceof Error ? `JSON 解析失败：${error.message}` : 'JSON 解析失败');
      return;
    }

    const root = parsed as { mcpServers?: Record<string, unknown> } | Record<string, unknown> | null;
    if (!root || typeof root !== 'object') {
      setMcpJsonImportError('JSON 根节点必须是对象');
      return;
    }

    const servers = (root as { mcpServers?: Record<string, unknown> }).mcpServers ?? root;
    if (!servers || typeof servers !== 'object' || Array.isArray(servers)) {
      setMcpJsonImportError('未找到 mcpServers 对象');
      return;
    }

    const entries = Object.entries(servers as Record<string, unknown>);
    if (entries.length === 0) {
      setMcpJsonImportError('JSON 中没有找到任何 MCP 服务');
      return;
    }

    setMcpJsonImportError(null);
    setSavingSection('mcp');
    const importedServers: Record<string, McpServerSettings> = {};
    const failures: string[] = [];

    for (const [name, raw] of entries) {
      const cfg = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
      const update: McpServerSettingsUpdate = {
        enabled: typeof cfg.enabled === 'boolean' ? cfg.enabled : true,
        notes: typeof cfg.notes === 'string' ? cfg.notes : '',
        icon: typeof cfg.icon === 'string' ? cfg.icon : '',
        type:
          cfg.type === 'stdio' || cfg.type === 'sse' || cfg.type === 'streamableHttp'
            ? cfg.type
            : null,
        command: typeof cfg.command === 'string' ? cfg.command : '',
        args: Array.isArray(cfg.args) ? cfg.args.map(String) : [],
        env:
          cfg.env && typeof cfg.env === 'object' && !Array.isArray(cfg.env)
            ? Object.fromEntries(Object.entries(cfg.env as Record<string, unknown>).map(([k, v]) => [k, String(v)]))
            : {},
        url: typeof cfg.url === 'string' ? cfg.url : '',
        headers:
          cfg.headers && typeof cfg.headers === 'object' && !Array.isArray(cfg.headers)
            ? Object.fromEntries(
                Object.entries(cfg.headers as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
              )
            : {},
        tool_timeout: typeof cfg.tool_timeout === 'number' ? cfg.tool_timeout : 30,
        enabled_tools: Array.isArray(cfg.enabled_tools) ? cfg.enabled_tools.map(String) : ['*'],
      };

      try {
        const response = await api.upsertMcpServer(name, update);
        importedServers[name] = response.server;
      } catch (error) {
        failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    setToolsDraft((current) =>
      current
        ? {
            ...current,
            mcp_servers: { ...current.mcp_servers, ...importedServers },
          }
        : current,
    );

    setSavingSection(null);
    if (failures.length > 0) {
      setFailure(new Error(failures.join('；')), `导入 ${entries.length - failures.length}/${entries.length} 个 MCP 服务，部分失败`);
    } else {
      setSuccess(`成功导入 ${entries.length} 个 MCP 服务`);
      setMcpJsonImportOpen(false);
      setMcpJsonImportText('');
    }
  };

  const handleSaveLongTermMemory = async () => {
    setMemorySaving(true);
    setNotice(null);
    try {
      const updated = await api.updateLongTermMemory(memoryDraft);
      setMemoryOverview((current) =>
        current
          ? {
              ...current,
              long_term: updated,
            }
          : current
      );
      setMemoryDraft(updated.content);
      setSuccess('长期记忆已保存');
    } catch (error) {
      setFailure(error, '保存长期记忆失败');
    } finally {
      setMemorySaving(false);
    }
  };

  const handleSaveCronJob = async () => {
    if (!taskName.trim()) {
      setNotice({ tone: 'error', text: '请填写任务标题' });
      return;
    }
    if (!taskMessage.trim()) {
      setNotice({ tone: 'error', text: '请填写提示词' });
      return;
    }

    setSavingSection('automation');
    setNotice(null);
    try {
      const payload: CreateCronJobPayload = {
        name: taskName.trim(),
        message: taskMessage.trim(),
        schedule_kind: scheduleKind,
        deliver: Boolean(taskTargetSessionId),
        session_id: taskTargetSessionId || null,
      };

      if (scheduleKind === 'every') {
        payload.every_seconds = everySeconds;
      } else if (scheduleKind === 'cron') {
        payload.cron_expr = cronGeneratedExpr;
        payload.tz = taskTimezone.trim();
      } else {
        payload.at = taskAtValue ? `${taskAtValue}:00` : '';
      }

      // Cron API has no PATCH — edit = delete old + create new.
      if (editingCronJobId) {
        await api.deleteCronJob(editingCronJobId);
      }
      const created = await api.createCronJob(payload);
      // Honor the master enable toggle if the user disabled it in the editor.
      if (!taskEnabled && created.enabled) {
        await api.toggleCronJob(created.id, false);
      }
      await loadSessions();
      await loadAutomationData(true);
      setSuccess(editingCronJobId ? '定时任务已更新' : '定时任务已创建');
      closeCronEditor();
    } catch (error) {
      setFailure(error, editingCronJobId ? '更新定时任务失败' : '创建定时任务失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleToggleCronJob = async (job: CronJob) => {
    setCronActioningId(job.id);
    setNotice(null);
    try {
      const updated = await api.toggleCronJob(job.id, !job.enabled);
      setCronJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
    } catch (error) {
      setFailure(error, '更新任务状态失败');
    } finally {
      setCronActioningId(null);
      await loadAutomationData(true);
    }
  };

  const handleRunCronJob = async (jobId: string) => {
    setCronActioningId(jobId);
    setNotice(null);
    try {
      await api.runCronJob(jobId);
      setSuccess('任务已立即触发');
      await loadAutomationData(true);
    } catch (error) {
      setFailure(error, '执行任务失败');
    } finally {
      setCronActioningId(null);
    }
  };

  const handleDeleteCronJob = async (jobId: string) => {
    setCronActioningId(jobId);
    setNotice(null);
    try {
      await api.deleteCronJob(jobId);
      setCronJobs((current) => current.filter((job) => job.id !== jobId));
      setSuccess('任务已删除');
      if (editingCronJobId === jobId) {
        setEditingCronJobId(null);
        setCronEditorOpen(false);
      }
      await loadAutomationData(true);
    } catch (error) {
      setFailure(error, '删除任务失败');
    } finally {
      setCronActioningId(null);
    }
  };

  const resetCronForm = () => {
    setTaskName('');
    setTaskMessage('');
    setTaskEnabled(true);
    setScheduleKind('cron');
    setFixedCronPreset('daily');
    setEverySeconds(3600);
    setCronExpr('0 9 * * *');
    setFixedTime('09:00');
    setWeeklyDay('1');
    setTaskTimezone('Asia/Shanghai');
    setTaskAtValue(defaultAtValue());
    setTaskTargetSessionId(TASK_RESULTS_SESSION_ID);
    setCronAdvancedOpen(false);
  };

  const populateCronFormFromJob = (job: CronJob) => {
    setTaskName(job.name);
    setTaskMessage(job.message);
    setTaskEnabled(job.enabled);
    setScheduleKind(job.schedule.kind);
    setTaskTimezone(job.schedule.tz || 'Asia/Shanghai');
    setTaskTargetSessionId(job.deliver ? job.to || '' : '');

    if (job.schedule.kind === 'every') {
      setEverySeconds(Math.max(1, Math.floor((job.schedule.every_ms || 3600000) / 1000)));
    } else if (job.schedule.kind === 'at') {
      if (job.schedule.at_ms) {
        const date = new Date(job.schedule.at_ms);
        const pad = (n: number) => String(n).padStart(2, '0');
        setTaskAtValue(
          `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`,
        );
      }
    } else if (job.schedule.kind === 'cron') {
      const expr = job.schedule.expr || '';
      setCronExpr(expr);
      const parts = expr.split(/\s+/);
      if (parts.length >= 5) {
        const [minute, hour, , , dow] = parts;
        const minuteNum = Number(minute);
        const hourNum = Number(hour);
        if (!Number.isNaN(minuteNum) && !Number.isNaN(hourNum)) {
          setFixedTime(`${String(hourNum).padStart(2, '0')}:${String(minuteNum).padStart(2, '0')}`);
        }
        if (dow === '*') {
          setFixedCronPreset('daily');
        } else if (dow === '1-5') {
          setFixedCronPreset('weekdays');
        } else if (/^\d$/.test(dow)) {
          setFixedCronPreset('weekly');
          setWeeklyDay(dow);
        } else {
          setFixedCronPreset('custom');
        }
      } else {
        setFixedCronPreset('custom');
      }
    }
    setCronAdvancedOpen(false);
  };

  const openCronEditor = (job?: CronJob) => {
    if (job) {
      setEditingCronJobId(job.id);
      populateCronFormFromJob(job);
    } else {
      setEditingCronJobId(null);
      resetCronForm();
    }
    setCronEditorOpen(true);
    setCronMenuOpenId(null);
  };

  const closeCronEditor = () => {
    setCronEditorOpen(false);
    setEditingCronJobId(null);
    resetCronForm();
  };

  const handleCleanupStorage = async () => {
    setStorageActionPath('__cleanup__');
    setNotice(null);
    try {
      const result = await api.cleanupStorage();
      await loadStorageData(true);
      setSuccess(`清理完成，删除了 ${result.deleted_files} 个文件和 ${result.deleted_dirs} 个空目录`);
    } catch (error) {
      setFailure(error, '清理文件失败');
    } finally {
      setStorageActionPath(null);
    }
  };

  const handleDeleteStoredFile = async (file: StorageFileItem) => {
    if (!file.can_delete) {
      const referencedBy = file.referenced_by.length;
      const reason =
        referencedBy > 0
          ? `仍被 ${referencedBy} 个会话引用，先删除对应会话或等待自动清理后再试。`
          : '当前还不能直接删除，请稍后再试。';
      setNotice({ tone: 'error', text: `${file.name} ${reason}` });
      return;
    }

    setStorageActionPath(file.path);
    setNotice(null);
    try {
      const result = await api.deleteStoredFile(file.path);
      await loadStorageData(true);
      setSuccess(`已删除 ${file.name}，释放 ${formatBytes(result.deleted_bytes)}`);
    } catch (error) {
      setFailure(error, '删除文件失败');
    } finally {
      setStorageActionPath(null);
    }
  };

  const renderModelsPanel = () => (
    <div className="settings-section">
      <div className="settings-metrics">
        <Metric label="默认提供商" value={currentProviderLabel} />
        <Metric label="默认模型" value={agentDraft?.model || '未设置'} />
        <Metric
          label="已存储密钥"
          value={`${providerCards.filter((provider) => provider.configured).length} 个`}
        />
      </div>

      <div className="settings-panel">
        <div className="settings-panel-header">
          <h3>提供商列表</h3>
          <p>只有已经保存 API Key 的提供商才能设为默认，点击编辑会打开单独的配置页。</p>
        </div>
        <div className="settings-provider-grid">
          {providerCards.map((provider) => (
            <div
              className={`settings-provider-card ${provider.active ? 'active' : ''} ${
                selectedProviderId === provider.id ? 'is-selected' : ''
              }`}
              key={provider.id}
            >
              <div className="settings-provider-head">
                <div>
                  <div className="settings-provider-name">{provider.label}</div>
                  <div className="settings-badges">
                    <span className="settings-badge">{provider.configured ? '已保存密钥' : '未保存密钥'}</span>
                    {provider.active ? <span className="settings-badge active">当前使用</span> : null}
                  </div>
                </div>
              </div>
              <div className="settings-provider-desc">
                <div>默认模型：{provider.model || '未设置'}</div>
                <div>{provider.endpoint || '未填写'}</div>
              </div>
              <div className="settings-provider-actions">
                <button
                  className="settings-button-secondary"
                  onClick={() => openProviderEditor(provider.id)}
                  type="button"
                >
                  编辑配置
                </button>
                <button
                  className="settings-button"
                  disabled={savingSection === 'models' || !provider.configured}
                  onClick={() => void handleActivateProvider(provider.id)}
                  type="button"
                >
                  {provider.active ? '正在使用' : '设为默认'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-panel">
        <div className="settings-panel-header">
          <h3>创作能力</h3>
          <p>这里的能力模型不会覆盖默认聊天模型，只决定对应创作入口是否可用。</p>
        </div>
        <div className="settings-provider-grid">
          {creativeCards
            .filter((capability) => !MINIMAX_STUDIO_IDS.has(capability.id))
            .map((capability) => renderCapabilityCard(capability))}

          <div className="settings-creative-group">
            <button
              type="button"
              className={`settings-creative-group__header ${
                minimaxStudioExpanded ? 'is-open' : ''
              }`}
              aria-expanded={minimaxStudioExpanded}
              onClick={() => setMinimaxStudioExpanded((value) => !value)}
            >
              <span className="settings-creative-group__title">MiniMax 音乐工程</span>
              <span className="settings-creative-group__count">
                {minimaxStudioCards.length} 项
              </span>
              <span
                className={`settings-creative-group__caret ${
                  minimaxStudioExpanded ? 'is-open' : ''
                }`}
                aria-hidden
              >
                ▾
              </span>
            </button>
            {minimaxStudioExpanded ? (
              <div className="settings-creative-group__body">
                {minimaxStudioCards.map((capability) => renderCapabilityCard(capability))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {toolsDraft ? (
        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>知识库模型</h3>
            <p>用于把上传的文档向量化(Embedding)、对召回结果重排(Rerank,可选)以及解析文档时调用视觉模型理解图表/扫描页(VLM,可选)。</p>
          </div>
          <div className="settings-provider-grid">
            {(['embedding', 'rerank', 'vlm'] as const).map((kind) => {
              const isEmbedding = kind === 'embedding';
              const isVlm = kind === 'vlm';
              const model = isEmbedding
                ? toolsDraft.knowledge.embedding_model
                : isVlm
                  ? toolsDraft.knowledge.vlm_model
                  : toolsDraft.knowledge.rerank_model;
              const endpoint = isEmbedding
                ? toolsDraft.knowledge.embedding_api_base
                : isVlm
                  ? toolsDraft.knowledge.vlm_api_base
                  : toolsDraft.knowledge.rerank_api_base;
              const configured = Boolean(model.trim());
              const editing = editingKnowledgeModelKind === kind;
              const label = isEmbedding ? 'Embedding' : isVlm ? 'VLM (视觉解析)' : 'Rerank';

              return (
                <div
                  key={kind}
                  className={`settings-provider-card ${configured ? 'active' : ''} ${
                    editing ? 'is-selected' : ''
                  }`}
                >
                  <div className="settings-provider-head">
                    <div>
                      <div className="settings-provider-name">{label}</div>
                      <div className="settings-badges">
                        <span className="settings-badge">
                          {configured ? '已配置' : '未配置'}
                        </span>
                        {!isEmbedding ? (
                          <span className="settings-badge">可选</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="settings-provider-desc">
                    <div>模型:{model || '未设置'}</div>
                    <div>{endpoint || '默认 endpoint'}</div>
                  </div>
                  <div className="settings-provider-actions">
                    <button
                      className="settings-button-secondary"
                      onClick={() => setEditingKnowledgeModelKind(kind)}
                      type="button"
                    >
                      编辑配置
                    </button>
                    <button
                      className="settings-button"
                      disabled
                      type="button"
                    >
                      {configured ? '已启用' : '启用'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

        </div>
      ) : null}
    </div>
  );

  const renderKnowledgeModelEditor = () => {
    if (!editingKnowledgeModelKind || !toolsDraft) return null;
    const kind = editingKnowledgeModelKind;
    const close = () => setEditingKnowledgeModelKind(null);

    const meta = {
      embedding: {
        title: 'Embedding 模型',
        intro: '把上传的文档切成片段后用这个模型转成向量,留空则只走关键词检索。',
        modelCopy: '推荐 text-embedding-3-small / bge-large-zh 等。',
        modelPlaceholder: 'text-embedding-3-small',
        modelField: 'embedding_model' as const,
        apiKeyField: 'embedding_api_key' as const,
        apiBaseField: 'embedding_api_base' as const,
      },
      rerank: {
        title: 'Rerank 模型',
        intro: '对召回的候选片段做二次排序,提升命中质量。留空则关闭 rerank。',
        modelCopy: '推荐 bge-reranker-v2-m3 / cohere rerank 等。',
        modelPlaceholder: 'bge-reranker-v2-m3',
        modelField: 'rerank_model' as const,
        apiKeyField: 'rerank_api_key' as const,
        apiBaseField: 'rerank_api_base' as const,
      },
      vlm: {
        title: 'VLM 视觉解析模型',
        intro: '配置后,解析 PDF 扫描页与 Office 文档内嵌图片时会调用该 VLM 生成图文描述;留空则跳过视觉解析,仅做文本提取。',
        modelCopy: '推荐 Qwen2.5-VL / GPT-4o-mini / Gemini 1.5 Flash 等多模态模型。',
        modelPlaceholder: 'Qwen/Qwen2.5-VL-7B-Instruct',
        modelField: 'vlm_model' as const,
        apiKeyField: 'vlm_api_key' as const,
        apiBaseField: 'vlm_api_base' as const,
      },
    }[kind];

    const setKnowledgeField = (updates: Partial<typeof toolsDraft.knowledge>) =>
      setToolsDraft((current) =>
        current
          ? { ...current, knowledge: { ...current.knowledge, ...updates } }
          : current,
      );

    return (
      <>
        <div className="settings-provider-editor-backdrop" onClick={close} />
        <aside className="settings-provider-editor">
          <div className="settings-provider-editor-head">
            <div>
              <h3>{meta.title}</h3>
              <p>{meta.intro}</p>
            </div>
            <button
              aria-label="关闭"
              className="settings-close"
              onClick={close}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
          <div className="settings-provider-editor-body">
            <div className="settings-panel">
              <div className="settings-grid one">
                <Field label="模型" copy={meta.modelCopy}>
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setKnowledgeField({ [meta.modelField]: event.target.value } as any)
                    }
                    placeholder={meta.modelPlaceholder}
                    type="text"
                    value={toolsDraft.knowledge[meta.modelField]}
                  />
                </Field>
                <Field label="API Key">
                  <input
                    autoComplete="off"
                    className="settings-input"
                    onChange={(event) =>
                      setKnowledgeField({ [meta.apiKeyField]: event.target.value } as any)
                    }
                    placeholder="sk-..."
                    type="password"
                    value={toolsDraft.knowledge[meta.apiKeyField]}
                  />
                </Field>
                <Field label="Base URL(可选)" copy="兼容 OpenAI 协议的网关地址。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setKnowledgeField({
                        [meta.apiBaseField]: event.target.value || null,
                      } as any)
                    }
                    placeholder="https://api.openai.com/v1"
                    type="text"
                    value={toolsDraft.knowledge[meta.apiBaseField] ?? ''}
                  />
                </Field>
                {kind === 'rerank' ? (
                  <Field label="重排条数" copy="对召回的前 N 个候选做 rerank。">
                    <input
                      className="settings-input"
                      min={1}
                      onChange={(event) =>
                        setKnowledgeField({
                          rerank_top_n: Number(event.target.value) || 1,
                        })
                      }
                      type="number"
                      value={toolsDraft.knowledge.rerank_top_n}
                    />
                  </Field>
                ) : null}
                {kind === 'vlm' ? (
                  <>
                    <Field label="请求超时 (秒)" copy="单次 VLM 调用的最长等待时间。">
                      <input
                        className="settings-input"
                        min={5}
                        onChange={(event) =>
                          setKnowledgeField({
                            vlm_timeout: Number(event.target.value) || 30,
                          })
                        }
                        type="number"
                        value={toolsDraft.knowledge.vlm_timeout}
                      />
                    </Field>
                    <Field
                      label="图片最大边长 (px)"
                      copy="上传给 VLM 前会等比缩放到这个尺寸,降低 token 消耗。"
                    >
                      <input
                        className="settings-input"
                        min={256}
                        onChange={(event) =>
                          setKnowledgeField({
                            vlm_max_dim: Number(event.target.value) || 1280,
                          })
                        }
                        type="number"
                        value={toolsDraft.knowledge.vlm_max_dim}
                      />
                    </Field>
                    <Field
                      label="并发线程数"
                      copy="解析一个文档时同时跑多少个 VLM 调用。值越大单个文档越快,但峰值 API 花费也更高。"
                    >
                      <input
                        className="settings-input"
                        min={1}
                        onChange={(event) =>
                          setKnowledgeField({
                            vlm_max_workers: Number(event.target.value) || 1,
                          })
                        }
                        type="number"
                        value={toolsDraft.knowledge.vlm_max_workers}
                      />
                    </Field>
                  </>
                ) : null}
              </div>
              <div className="settings-actions">
                <button
                  className="settings-button-secondary"
                  onClick={close}
                  type="button"
                >
                  取消
                </button>
                <button
                  className="settings-button"
                  disabled={savingSection === 'knowledge-models'}
                  onClick={async () => {
                    await handleSaveKnowledgeModels();
                    close();
                  }}
                  type="button"
                >
                  {savingSection === 'knowledge-models' ? '保存中…' : '保存'}
                </button>
              </div>
            </div>
          </div>
        </aside>
      </>
    );
  };

  const renderCreativeEditor = () => {
    if (!editingCreativeId) {
      return null;
    }

    const capabilityMeta = CREATIVE_CAPABILITY_META[editingCreativeId];
    const currentCapability = creativeDraft?.[editingCreativeId] || createEmptyCreativeCapabilitySettings();

    return (
      <>
        <div className="settings-provider-editor-backdrop" onClick={closeCreativeEditor} />
        <aside className="settings-provider-editor">
          <div className="settings-provider-editor-head">
            <div>
              <h3>{capabilityMeta.label}</h3>
              <p>{capabilityMeta.description}</p>
            </div>
            <button
              aria-label={`关闭 ${capabilityMeta.label} 配置面板`}
              className="settings-close"
              onClick={closeCreativeEditor}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
          <div className="settings-provider-editor-body">
            <div className="settings-panel">
              <div className="settings-grid one">
                <ToggleRow
                  title="启用能力"
                  copy={`当前入口：${capabilityMeta.usage}`}
                  value={creativeForm.enabled}
                  onToggle={() =>
                    setCreativeForm((current) => ({
                      ...current,
                      enabled: !current.enabled,
                    }))
                  }
                />
                <Field label="Provider" copy="填写该能力使用的提供商标识。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setCreativeForm((current) => ({ ...current, provider: event.target.value }))
                    }
                    placeholder={capabilityMeta.defaultProvider}
                    type="text"
                    value={creativeForm.provider}
                  />
                </Field>
                <Field label="Model" copy="填写该能力要调用的模型名。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setCreativeForm((current) => ({ ...current, model: event.target.value }))
                    }
                    placeholder={capabilityMeta.defaultModel}
                    type="text"
                    value={creativeForm.model}
                  />
                </Field>
                <Field label="API Base" copy="可选，留空时由服务端使用默认地址。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setCreativeForm((current) => ({ ...current, apiBase: event.target.value }))
                    }
                    placeholder="https://api.example.com"
                    type="text"
                    value={creativeForm.apiBase}
                  />
                </Field>
                <Field
                  label="API Key"
                  copy={`当前显示：${currentCapability.api_key || '未配置'}。仅在输入新值时更新。`}
                >
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setCreativeForm((current) => ({ ...current, apiKey: event.target.value }))
                    }
                    placeholder="输入新的 API Key"
                    type="password"
                    value={creativeForm.apiKey}
                  />
                </Field>
                <Field label="Extra Headers" copy='示例：{"X-App":"TokenMind"}'>
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setCreativeForm((current) => ({
                        ...current,
                        extraHeadersText: event.target.value,
                      }))
                    }
                    placeholder='{"X-App":"TokenMind"}'
                    value={creativeForm.extraHeadersText}
                  />
                </Field>
              </div>
              <div className="settings-actions">
                <button
                  className="settings-button"
                  disabled={savingSection === 'creative'}
                  onClick={() => void handleSaveCreativeCapability()}
                  type="button"
                >
                  保存创作能力配置
                </button>
              </div>
            </div>
          </div>
        </aside>
      </>
    );
  };

  const renderProviderEditor = () => {
    if (!editingProviderId) {
      return null;
    }

    return (
      <>
        <div className="settings-provider-editor-backdrop" onClick={closeProviderEditor} />
        <aside className="settings-provider-editor">
          <div className="settings-provider-editor-head">
            <div>
              <h3>{PROVIDER_META[editingProviderId]?.label || editingProviderId}</h3>
              <p>在这里单独配置当前提供商的连接地址、默认模型、密钥和额外请求头。</p>
            </div>
            <button
              aria-label={`关闭 ${PROVIDER_META[editingProviderId]?.label || editingProviderId} 配置面板`}
              className="settings-close"
              onClick={closeProviderEditor}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
          <div className="settings-provider-editor-body">
            <div className="settings-panel">
              <div className="settings-grid one">
                <Field label="API Base" copy="兼容 OpenAI 的网关地址或自定义服务地址。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setProviderForm((current) => ({ ...current, apiBase: event.target.value }))
                    }
                    placeholder="https://api.example.com"
                    type="text"
                    value={providerForm.apiBase}
                  />
                </Field>
                <Field label="默认模型" copy="设为默认时会优先使用这里的模型。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setProviderForm((current) => ({ ...current, defaultModel: event.target.value }))
                    }
                    placeholder={PROVIDER_META[editingProviderId]?.defaultModel || 'model-name'}
                    type="text"
                    value={providerForm.defaultModel}
                  />
                </Field>
                <Field
                  label="API Key"
                  copy={`当前显示：${providers[editingProviderId]?.api_key || '未配置'}。仅在输入新值时更新。`}
                >
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setProviderForm((current) => ({ ...current, apiKey: event.target.value }))
                    }
                    placeholder="输入新的 API Key"
                    type="password"
                    value={providerForm.apiKey}
                  />
                </Field>
                <Field label="额外请求头" copy='示例：{"APP-Code":"demo"}'>
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setProviderForm((current) => ({
                        ...current,
                        extraHeadersText: event.target.value,
                      }))
                    }
                    placeholder='{"X-App":"TokenMind"}'
                    value={providerForm.extraHeadersText}
                  />
                </Field>
              </div>
              <div className="settings-provider-advanced-fields">
                {renderModelAdvancedFields()}
              </div>
              <div className="settings-actions">
                <button
                  className="settings-button"
                  disabled={savingSection === 'models'}
                  onClick={() => void handleSaveProvider()}
                  type="button"
                >
                  保存模型配置
                </button>
              </div>
            </div>
          </div>
        </aside>
      </>
    );
  };

  const renderModelAdvancedFields = () => {
    if (!agentDraft) {
      return null;
    }

    return (
      <div className="settings-provider-advanced">
        <div className="settings-provider-advanced-head">
          <h4>模型高级参数</h4>
          <p>这些参数会随本次模型配置一起保存，用于后续对话和工具执行。</p>
        </div>
        <div className="settings-flat-panel">
          <div className="settings-grid">
            <Field label="工作目录" copy="模型调用和工具执行使用的 workspace。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current ? { ...current, workspace: event.target.value } : current
                  )
                }
                type="text"
                value={agentDraft.workspace}
              />
            </Field>
            <Field label="推理强度" copy="只在支持 reasoning 的模型上有意义。">
              <select
                className="settings-select"
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current
                      ? {
                          ...current,
                          reasoning_effort: event.target.value || null,
                        }
                      : current
                  )
                }
                value={agentDraft.reasoning_effort || ''}
              >
                {REASONING_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="settings-grid">
            <Field label="最大输出 Token" copy="单次回复允许的最大输出长度。">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current ? { ...current, max_tokens: Number(event.target.value) || 0 } : current
                  )
                }
                type="number"
                value={agentDraft.max_tokens}
              />
            </Field>
            <Field label="上下文窗口 Token" copy="构建上下文时的目标窗口大小。">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current
                      ? { ...current, context_window_tokens: Number(event.target.value) || 0 }
                      : current
                  )
                }
                type="number"
                value={agentDraft.context_window_tokens}
              />
            </Field>
          </div>
          <div className="settings-grid">
            <Field label="Temperature" copy="越高越发散，越低越稳定。">
              <input
                className="settings-input"
                max={2}
                min={0}
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current ? { ...current, temperature: Number(event.target.value) || 0 } : current
                  )
                }
                step="0.1"
                type="number"
                value={agentDraft.temperature}
              />
            </Field>
            <Field label="最大工具迭代" copy="单轮对话里允许的最多工具往返次数。">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current
                      ? { ...current, max_tool_iterations: Number(event.target.value) || 0 }
                      : current
                  )
                }
                type="number"
                value={agentDraft.max_tool_iterations}
              />
            </Field>
          </div>
        </div>
      </div>
    );
  };

  const renderToolsCategoryEditor = () => {
    if (!toolsDraft || !toolsCategory) {
      return null;
    }

    const titles: Record<NonNullable<typeof toolsCategory>, { title: string; copy: string }> = {
      search: { title: 'Web 搜索', copy: '配置默认搜索引擎、API Key 和返回数量。' },
      exec: { title: '命令执行', copy: '设置 exec 工具的超时和环境 PATH。' },
      audit: { title: '审批与审计', copy: '高风险命令是否需要确认，是否记录审计日志。' },
      uploads: { title: '上传与存储', copy: '单文件上限、总配额和过期清理策略。' },
      knowledge: { title: '知识库检索', copy: '向量后端、切块策略与召回数量。' },
    };
    const meta = titles[toolsCategory];

    const closeEditor = () => {
      setToolsCategory(null);
    };
    const saveAndClose = async () => {
      await handleSaveTools();
      closeEditor();
    };

    return (
      <div className="settings-mcp-editor">
        <div className="settings-mcp-editor__head">
          <div>
            <h3>{meta.title}</h3>
            <div className="settings-inline-note">{meta.copy}</div>
          </div>
          <button
            className="settings-mcp-editor__close"
            onClick={closeEditor}
            type="button"
            aria-label="关闭编辑器"
          >
            ×
          </button>
        </div>

        {toolsCategory === 'search' ? (
          <>
            <Field label="搜索提供商">
              <select
                className="settings-select"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          web: {
                            ...current.web,
                            search: { ...current.web.search, provider: event.target.value },
                          },
                        }
                      : current,
                  )
                }
                value={toolsDraft.web.search.provider}
              >
                {SEARCH_PROVIDER_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="搜索 API Key" copy={`当前显示：${searchApiKeyMasked || '未配置'}。仅在输入新值时更新。`}>
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          web: {
                            ...current.web,
                            search: { ...current.web.search, api_key: event.target.value },
                          },
                        }
                      : current,
                  )
                }
                placeholder="输入新的搜索 API Key"
                type="password"
                value={toolsDraft.web.search.api_key || ''}
              />
            </Field>
            <Field label="最大结果数" copy="单次搜索最多返回多少条结果。">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          web: {
                            ...current.web,
                            search: {
                              ...current.web.search,
                              max_results: Number(event.target.value) || 1,
                            },
                          },
                        }
                      : current,
                  )
                }
                type="number"
                value={toolsDraft.web.search.max_results}
              />
            </Field>
            <Field label="代理（可选）" copy="支持 HTTP 和 SOCKS5。留空表示不使用代理。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          web: { ...current.web, proxy: event.target.value },
                        }
                      : current,
                  )
                }
                placeholder="http://127.0.0.1:7890"
                type="text"
                value={toolsDraft.web.proxy || ''}
              />
            </Field>
            <Field label="自定义搜索地址（可选）" copy="SearXNG 或自托管搜索时使用。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          web: {
                            ...current.web,
                            search: { ...current.web.search, base_url: event.target.value },
                          },
                        }
                      : current,
                  )
                }
                placeholder="https://search.example.com"
                type="text"
                value={toolsDraft.web.search.base_url || ''}
              />
            </Field>
          </>
        ) : null}

        {toolsCategory === 'exec' ? (
          <>
            <Field label="超时时间（秒）" copy="单次 exec 调用超过这个时间会被取消。">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          exec: {
                            ...current.exec,
                            timeout: Number(event.target.value) || 1,
                          },
                        }
                      : current,
                  )
                }
                type="number"
                value={toolsDraft.exec.timeout}
              />
            </Field>
            <Field label="额外 PATH（可选）" copy="会追加到 exec 环境的 PATH 中。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          exec: { ...current.exec, path_append: event.target.value },
                        }
                      : current,
                  )
                }
                placeholder="C:\\tools;D:\\bin"
                type="text"
                value={toolsDraft.exec.path_append}
              />
            </Field>
          </>
        ) : null}

        {toolsCategory === 'audit' ? (
          <>
            <ToggleRow
              title="高风险命令需要确认"
              copy="Web 会话执行高风险命令前，先弹出确认层等待人工放行。"
              value={toolsDraft.exec.confirm_high_risk}
              onToggle={() =>
                setToolsDraft((current) =>
                  current
                    ? {
                        ...current,
                        exec: {
                          ...current.exec,
                          confirm_high_risk: !current.exec.confirm_high_risk,
                        },
                      }
                    : current,
                )
              }
            />
            <ToggleRow
              title="启用审计日志"
              copy="把 exec 审批、文件删除、会话删除和定时任务操作写入 workspace/logs/audit.jsonl。"
              value={toolsDraft.audit_enabled}
              onToggle={() =>
                setToolsDraft((current) =>
                  current
                    ? { ...current, audit_enabled: !current.audit_enabled }
                    : current,
                )
              }
            />
            <Field label="审批等待时间（秒）" copy="超过这个时间还没确认，高风险命令会自动取消。">
              <input
                className="settings-input"
                min={15}
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          exec: {
                            ...current.exec,
                            approval_timeout_s: Number(event.target.value) || 15,
                          },
                        }
                      : current,
                  )
                }
                type="number"
                value={toolsDraft.exec.approval_timeout_s}
              />
            </Field>
          </>
        ) : null}

        {toolsCategory === 'uploads' ? (
          <>
            <div className="settings-mcp-editor__grid">
              <Field label="单文件上限 (MB)">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            uploads: {
                              ...current.uploads,
                              max_file_mb: Number(event.target.value) || 1,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.uploads.max_file_mb}
                />
              </Field>
              <Field label="总配额 (MB)">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            uploads: {
                              ...current.uploads,
                              max_total_mb: Number(event.target.value) || 1,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.uploads.max_total_mb}
                />
              </Field>
              <Field label="保留天数" copy="超过这个天数仍未被引用的文件可被清理。">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            uploads: {
                              ...current.uploads,
                              retention_days: Number(event.target.value) || 1,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.uploads.retention_days}
                />
              </Field>
              <Field label="清理检查间隔（小时）">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            uploads: {
                              ...current.uploads,
                              cleanup_interval_hours: Number(event.target.value) || 1,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.uploads.cleanup_interval_hours}
                />
              </Field>
            </div>
          </>
        ) : null}

        {toolsCategory === 'knowledge' ? (
          <>
            <div className="settings-mcp-editor__grid">
              <Field label="向量后端" copy="默认 Qdrant，本地单机也能直接运行。">
                <select
                  className="settings-select"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            knowledge: { ...current.knowledge, vector_backend: event.target.value },
                          }
                        : current,
                    )
                  }
                  value={toolsDraft.knowledge.vector_backend}
                >
                  <option value="qdrant">Qdrant</option>
                  <option value="sqlite">SQLite（轻量兜底）</option>
                </select>
              </Field>
              <Field label="召回数量 Top-K">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            knowledge: {
                              ...current.knowledge,
                              top_k: Number(event.target.value) || 1,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.knowledge.top_k}
                />
              </Field>
              <Field label="分块长度" copy="单个 chunk 的目标长度。">
                <input
                  className="settings-input"
                  min={100}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            knowledge: {
                              ...current.knowledge,
                              chunk_size: Number(event.target.value) || 100,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.knowledge.chunk_size}
                />
              </Field>
              <Field label="分块重叠">
                <input
                  className="settings-input"
                  min={0}
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            knowledge: {
                              ...current.knowledge,
                              chunk_overlap: Number(event.target.value) || 0,
                            },
                          }
                        : current,
                    )
                  }
                  type="number"
                  value={toolsDraft.knowledge.chunk_overlap}
                />
              </Field>
            </div>

            <p className="settings-mcp-editor__hint">
              Embedding 与 Rerank 模型已搬到「设置 → 模型 → 知识库模型」统一管理。
            </p>
          </>
        ) : null}

        <div className="settings-actions settings-mcp-editor__actions">
          <button className="settings-button-secondary" onClick={closeEditor} type="button">
            取消
          </button>
          <button
            className="settings-button"
            disabled={savingSection === 'tools'}
            onClick={() => void saveAndClose()}
            type="button"
          >
            {savingSection === 'tools' ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    );
  };

  const renderTools = () => {
    if (!toolsDraft) {
      return null;
    }

    const cards: Array<{
      id: 'search' | 'exec' | 'audit' | 'uploads' | 'knowledge';
      icon: string;
      title: string;
      desc: string;
      summary: string;
    }> = [
      {
        id: 'search',
        icon: '🔍',
        title: 'Web 搜索',
        desc: '智能体搜索互联网时使用的提供商和参数。',
        summary: `${toolsDraft.web.search.provider} · 最多 ${toolsDraft.web.search.max_results} 条`,
      },
      {
        id: 'exec',
        icon: '⚡',
        title: '命令执行',
        desc: '智能体执行 shell 命令时的超时和环境。',
        summary: `超时 ${toolsDraft.exec.timeout} 秒`,
      },
      {
        id: 'audit',
        icon: '🛡️',
        title: '审批与审计',
        desc: '高风险动作是否需要人工确认，是否记录审计日志。',
        summary: `${toolsDraft.exec.confirm_high_risk ? '需确认' : '直接放行'} · ${
          toolsDraft.audit_enabled ? '已审计' : '未审计'
        }`,
      },
      {
        id: 'uploads',
        icon: '📤',
        title: '上传与存储',
        desc: '单文件大小、总配额和过期清理策略。',
        summary: `单文件 ${toolsDraft.uploads.max_file_mb}MB · 共 ${toolsDraft.uploads.max_total_mb}MB`,
      },
      {
        id: 'knowledge',
        icon: '📚',
        title: '知识库检索',
        desc: '向量后端、切块策略与召回数量。',
        summary: `${toolsDraft.knowledge.vector_backend} · Top-${toolsDraft.knowledge.top_k}${
          toolsDraft.knowledge.embedding_model ? ` · ${toolsDraft.knowledge.embedding_model}` : ''
        }`,
      },
    ];

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-mcp-toolbar__text">
            <h3>工具与运行边界</h3>
            <p>逐项管理工具能力、安全策略与上传配额。点击卡片打开对应配置。</p>
          </div>
        </div>

        <div className="settings-tools-safety">
          <div className="settings-toggle-text">
            <strong>限制工具访问工作目录</strong>
            <span>开启后，工具会尽量只访问当前 workspace 内的内容。</span>
          </div>
          <button
            className={`settings-toggle ${toolsDraft.restrict_to_workspace ? 'on' : ''}`}
            onClick={() => {
              setToolsDraft((current) =>
                current
                  ? { ...current, restrict_to_workspace: !current.restrict_to_workspace }
                  : current,
              );
              // Persist immediately so users don't need to remember to save.
              window.setTimeout(() => void handleSaveTools(), 0);
            }}
            type="button"
          >
            {toolsDraft.restrict_to_workspace ? '已开启' : '已关闭'}
          </button>
        </div>

        <div className="settings-mcp-grid">
          {cards.map((card) => (
            <button
              className={`settings-mcp-card settings-tools-card ${toolsCategory === card.id ? 'is-active' : ''}`}
              key={card.id}
              onClick={() => {
                setToolsCategory(card.id);
              }}
              type="button"
            >
              <div className="settings-mcp-card__head">
                <div className="settings-mcp-card__icon settings-tools-card__icon">{card.icon}</div>
                <div className="settings-mcp-card__title">
                  <div className="settings-mcp-card__name">{card.title}</div>
                  <div className="settings-mcp-card__transport">{card.summary}</div>
                </div>
              </div>
              <div className="settings-mcp-card__notes">{card.desc}</div>
            </button>
          ))}
        </div>

        {renderToolsCategoryEditor()}
      </div>
    );
  };


  const renderMcpEditor = () => {
    const isHttpMode = mcpForm.type === 'sse' || mcpForm.type === 'streamableHttp' || mcpForm.type === '';
    const showStdioFields = mcpForm.type === 'stdio' || mcpForm.type === '';
    const editingExistingName = selectedMcpName;

    return (
      <div className="settings-mcp-editor">
        <div className="settings-mcp-editor__head">
          <h3>{editingExistingName ? `编辑 ${editingExistingName}` : '新建 MCP 服务'}</h3>
          <button
            className="settings-mcp-editor__close"
            onClick={closeMcpEditor}
            type="button"
            aria-label="关闭编辑器"
          >
            ×
          </button>
        </div>

        <div className="settings-mcp-editor__grid">
          <Field label="服务器名称">
            <input
              className="settings-input"
              onChange={(event) => setMcpForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="例如：filesystem"
              type="text"
              value={mcpForm.name}
            />
          </Field>
          <Field label="传输类型">
            <select
              className="settings-select"
              onChange={(event) =>
                setMcpForm((current) => ({
                  ...current,
                  type: event.target.value as McpFormState['type'],
                }))
              }
              value={mcpForm.type}
            >
              <option value="">自动识别</option>
              <option value="streamableHttp">HTTP</option>
              <option value="sse">SSE</option>
              <option value="stdio">本地命令 (stdio)</option>
            </select>
          </Field>
        </div>

        <Field label="图标 URL（可选）">
          <input
            className="settings-input"
            onChange={(event) => setMcpForm((current) => ({ ...current, icon: event.target.value }))}
            placeholder="粘贴一个图标的 URL"
            type="text"
            value={mcpForm.icon}
          />
        </Field>

        <Field label="备注（可选）" copy="简短说明这个 MCP 服务做什么、何时启用。">
          <textarea
            className="settings-textarea settings-mcp-editor__notes"
            onChange={(event) => setMcpForm((current) => ({ ...current, notes: event.target.value }))}
            placeholder="例如：本地文件系统访问，仅在处理项目源码时启用"
            value={mcpForm.notes}
          />
        </Field>

        {isHttpMode ? (
          <>
            <Field label="服务器 URL">
              <input
                className="settings-input"
                onChange={(event) => setMcpForm((current) => ({ ...current, url: event.target.value }))}
                placeholder="https://mcp.yourserver.com/mcp"
                type="text"
                value={mcpForm.url}
              />
            </Field>

            <div className="settings-mcp-headers">
              <div className="settings-mcp-headers__head">
                <span className="settings-field-title">自定义 headers（可选）</span>
                <button
                  className="settings-button-secondary settings-mcp-headers__add"
                  onClick={() =>
                    setMcpForm((current) => ({
                      ...current,
                      headerRows: [...current.headerRows, { id: nextHeaderRowId(), key: '', value: '' }],
                    }))
                  }
                  type="button"
                >
                  + 添加自定义 header
                </button>
              </div>
              {mcpForm.headerRows.length > 0 ? (
                <div className="settings-mcp-headers__list">
                  {mcpForm.headerRows.map((row) => (
                    <div className="settings-mcp-headers__row" key={row.id}>
                      <input
                        className="settings-input"
                        onChange={(event) => {
                          const value = event.target.value;
                          setMcpForm((current) => ({
                            ...current,
                            headerRows: current.headerRows.map((entry) =>
                              entry.id === row.id ? { ...entry, key: value } : entry,
                            ),
                          }));
                        }}
                        placeholder="Header 名称"
                        type="text"
                        value={row.key}
                      />
                      <input
                        className="settings-input"
                        onChange={(event) => {
                          const value = event.target.value;
                          setMcpForm((current) => ({
                            ...current,
                            headerRows: current.headerRows.map((entry) =>
                              entry.id === row.id ? { ...entry, value: value } : entry,
                            ),
                          }));
                        }}
                        placeholder="Header 值"
                        type="text"
                        value={row.value}
                      />
                      <button
                        className="settings-mcp-headers__remove"
                        onClick={() =>
                          setMcpForm((current) => ({
                            ...current,
                            headerRows: current.headerRows.filter((entry) => entry.id !== row.id),
                          }))
                        }
                        type="button"
                        aria-label="删除 header"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </>
        ) : null}

        {showStdioFields && mcpForm.type === 'stdio' ? (
          <>
            <Field label="启动命令" copy="本地 stdio 模式下要执行的命令。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setMcpForm((current) => ({ ...current, command: event.target.value }))
                }
                placeholder="npx"
                type="text"
                value={mcpForm.command}
              />
            </Field>
            <Field label="参数列表（可选）" copy="每行一个参数。">
              <textarea
                className="settings-textarea"
                onChange={(event) =>
                  setMcpForm((current) => ({ ...current, argsText: event.target.value }))
                }
                placeholder="-y&#10;@modelcontextprotocol/server-filesystem"
                value={mcpForm.argsText}
              />
            </Field>
            <Field label="环境变量（可选）" copy="JSON 对象，例如 {&quot;ROOT&quot;:&quot;/data&quot;}。">
              <textarea
                className="settings-textarea"
                onChange={(event) =>
                  setMcpForm((current) => ({ ...current, envText: event.target.value }))
                }
                placeholder='{"ROOT":"/data"}'
                value={mcpForm.envText}
              />
            </Field>
          </>
        ) : null}

        <button
          className="settings-mcp-advanced-toggle"
          onClick={() => setMcpAdvancedOpen((value) => !value)}
          type="button"
        >
          {mcpAdvancedOpen ? '▾ 收起高级选项' : '▸ 高级选项'}
        </button>

        {mcpAdvancedOpen ? (
          <div className="settings-mcp-advanced">
            <Field label="允许的工具" copy="每行一个工具名，使用 * 表示全部。">
              <textarea
                className="settings-textarea"
                onChange={(event) =>
                  setMcpForm((current) => ({ ...current, enabledToolsText: event.target.value }))
                }
                placeholder="*"
                value={mcpForm.enabledToolsText}
              />
            </Field>
            <Field label="工具超时（秒）">
              <input
                className="settings-input"
                min={1}
                onChange={(event) =>
                  setMcpForm((current) => ({
                    ...current,
                    toolTimeout: Number(event.target.value) || 1,
                  }))
                }
                type="number"
                value={mcpForm.toolTimeout}
              />
            </Field>
          </div>
        ) : null}

        <div className="settings-actions settings-mcp-editor__actions">
          <button
            className="settings-button-secondary"
            onClick={closeMcpEditor}
            type="button"
          >
            取消
          </button>
          {editingExistingName ? (
            <button
              className="settings-button-danger"
              disabled={savingSection === 'mcp'}
              onClick={() => void handleDeleteMcp(editingExistingName)}
              type="button"
            >
              删除
            </button>
          ) : null}
          <button
            className="settings-button"
            disabled={savingSection === 'mcp'}
            onClick={() => void handleSaveMcp()}
            type="button"
          >
            {savingSection === 'mcp' ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    );
  };

  const renderMcpJsonImport = () => {
    if (!mcpJsonImportOpen) {
      return null;
    }
    return (
      <div
        className="settings-modal-overlay"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            setMcpJsonImportOpen(false);
          }
        }}
      >
        <div className="settings-mcp-json">
          <div className="settings-mcp-json__head">
            <h3>从 JSON 导入 MCP 服务</h3>
            <button
              className="settings-mcp-editor__close"
              onClick={() => setMcpJsonImportOpen(false)}
              type="button"
              aria-label="关闭"
            >
              ×
            </button>
          </div>
          <p className="settings-inline-note">
            支持 Claude Desktop / Cursor 等工具使用的 <code>{'{ "mcpServers": { ... } }'}</code> 格式，
            也接受直接传入服务字典。重名将覆盖现有配置。
          </p>
          <textarea
            className="settings-textarea settings-mcp-json__textarea"
            onChange={(event) => {
              setMcpJsonImportText(event.target.value);
              if (mcpJsonImportError) {
                setMcpJsonImportError(null);
              }
            }}
            placeholder={`{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    }
  }
}`}
            value={mcpJsonImportText}
          />
          {mcpJsonImportError ? (
            <div className="settings-notice error">{mcpJsonImportError}</div>
          ) : null}
          <div className="settings-actions">
            <button
              className="settings-button-secondary"
              onClick={() => setMcpJsonImportOpen(false)}
              type="button"
            >
              取消
            </button>
            <button
              className="settings-button"
              disabled={savingSection === 'mcp'}
              onClick={() => void handleApplyMcpJsonImport()}
              type="button"
            >
              {savingSection === 'mcp' ? '导入中…' : '导入'}
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderMemoryCenter = () => {
    if (memoryLoading && !memoryOverview) {
      return <div className="settings-loading">正在加载记忆中心...</div>;
    }

    if (!memoryOverview) {
      return <div className="settings-empty">当前还没有可展示的记忆数据。</div>;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="长期记忆字数" value={`${longTermMeta.words} 词`} />
          <Metric label="当前上下文条数" value={`${memoryOverview.current_context.items.length} 条`} />
          <Metric label="近期归档命中" value={`${memoryOverview.archive.total} 条`} />
        </div>

        <div className="settings-memory-layout">
          <section className="settings-panel settings-memory-editor-panel">
            <div className="settings-panel-header">
              <h3>长期记忆</h3>
              <p>这里保存的是跨会话保留的稳定事实、偏好和背景信息，可以直接编辑并保存。</p>
            </div>
            <textarea
              className="settings-textarea settings-memory-editor"
              onChange={(event) => setMemoryDraft(event.target.value)}
              placeholder="这里还没有长期记忆。你可以记录固定偏好、工作背景和重要事实。"
              spellCheck={false}
              value={memoryDraft}
            />
            <div className="settings-actions">
              <button className="settings-button-secondary" onClick={() => void loadMemoryOverview('', true)} type="button">
                刷新
              </button>
              <button
                className="settings-button"
                disabled={!memoryDraftDirty || memorySaving || !memoryOverview.long_term.editable}
                onClick={() => void handleSaveLongTermMemory()}
                type="button"
              >
                {memorySaving ? '保存中' : '保存长期记忆'}
              </button>
            </div>
          </section>

          <div className="settings-memory-side">
            <section className="settings-panel">
              <div className="settings-panel-header">
                <h3>编辑状态</h3>
                <p>随时确认当前草稿和已保存内容之间的差异。</p>
              </div>
              <div className="settings-facts-list">
                <div className="settings-fact-row">
                  <span>保存状态</span>
                  <strong>{memoryDraftDirty ? '有未保存修改' : '已同步'}</strong>
                </div>
                <div className="settings-fact-row">
                  <span>可编辑</span>
                  <strong>{memoryOverview.long_term.editable ? '是' : '否'}</strong>
                </div>
                <div className="settings-fact-row">
                  <span>字符数</span>
                  <strong>{memoryDraft.length}</strong>
                </div>
                <div className="settings-fact-row">
                  <span>最后更新</span>
                  <strong>{formatTimestamp(memoryOverview.long_term.updated_at)}</strong>
                </div>
              </div>
            </section>

            <section className="settings-panel">
              <div className="settings-panel-header">
                <h3>当前上下文</h3>
                <p>这里展示的是当前会话里仍在参与推理的近段内容。</p>
              </div>
              {memoryOverview.current_context.items.length === 0 ? (
                <div className="settings-empty">
                  还没有活动会话内容。开始一段对话后，这里会显示当前真正参与推理的内容。
                </div>
              ) : (
                <div className="settings-context-list">
                  {memoryOverview.current_context.items.slice(0, 4).map((item, index) => (
                    <article className="settings-context-item" key={`${item.timestamp || index}-${index}`}>
                      <div className="settings-context-item__head">
                        <span className="settings-badge active">{memoryRoleLabel(item.role)}</span>
                        <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                      </div>
                      <SettingsMarkdown content={item.content} />
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>

        <section className="settings-panel">
          <div className="settings-panel-header">
            <h3>近期归档</h3>
            <p>已经从主上下文移出的历史片段会显示在这里，方便你搜索和回看。</p>
          </div>
          <div className="settings-memory-toolbar">
            <input
              className="settings-input"
              onChange={(event) => setMemoryArchiveQuery(event.target.value)}
              placeholder="搜索归档内容"
              type="text"
              value={memoryArchiveQuery}
            />
            <span className="settings-badge">{memoryOverview.archive.total} 条</span>
          </div>
          {memoryOverview.archive.items.length === 0 ? (
            <div className="settings-empty">
              {memoryArchiveQuery.trim()
                ? '没有匹配当前关键词的归档内容。'
                : '还没有近期归档内容。对话足够长后，这里会出现整理过的历史片段。'}
            </div>
          ) : (
            <div className="settings-archive-list">
              {memoryOverview.archive.items.slice(0, 6).map((item) => (
                <article className="settings-archive-item" key={item.id}>
                  <div className="settings-context-item__head">
                    <span className="settings-badge active">归档片段</span>
                    <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <SettingsMarkdown content={item.content} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  };

  const renderCronEditor = () => {
    return (
      <div className="settings-mcp-editor">
        <div className="settings-mcp-editor__head">
          <h3>{editingCronJobId ? '编辑定时任务' : '新建定时任务'}</h3>
          <button
            className="settings-mcp-editor__close"
            onClick={closeCronEditor}
            type="button"
            aria-label="关闭编辑器"
          >
            ×
          </button>
        </div>

        <div className="settings-cron-toggle-row">
          <div className="settings-toggle-text">
            <strong>启用此任务</strong>
            <span>启用后，此任务将根据以下计划自动运行。</span>
          </div>
          <button
            className={`settings-toggle ${taskEnabled ? 'on' : ''}`}
            onClick={() => setTaskEnabled((value) => !value)}
            type="button"
            aria-label={taskEnabled ? '点击停用' : '点击启用'}
          >
            {taskEnabled ? '已启用' : '已停用'}
          </button>
        </div>

        <Field label="标题">
          <input
            className="settings-input"
            type="text"
            value={taskName}
            onChange={(event) => setTaskName(event.target.value)}
            placeholder="例如：每日新闻摘要"
          />
        </Field>

        <Field label="提示词">
          <textarea
            className="settings-textarea settings-cron-prompt"
            value={taskMessage}
            onChange={(event) => setTaskMessage(event.target.value)}
            placeholder="例如：搜索昨天最具影响力的 AI 新闻，并向我发送一份简要摘要。"
          />
        </Field>

        <div className="settings-cron-schedule">
          <div className="settings-field-title">计划</div>
          <div className="settings-cron-schedule__row">
            <select
              className="settings-select"
              value={
                scheduleKind === 'at'
                  ? 'at'
                  : scheduleKind === 'every'
                    ? 'every'
                    : fixedCronPreset
              }
              onChange={(event) => {
                const value = event.target.value;
                if (value === 'at') {
                  setScheduleKind('at');
                } else if (value === 'every') {
                  setScheduleKind('every');
                } else {
                  setScheduleKind('cron');
                  setFixedCronPreset(value as FixedCronPreset);
                }
              }}
            >
              <option value="at">不重复</option>
              <option value="daily">每天</option>
              <option value="weekdays">每个工作日</option>
              <option value="weekly">每周</option>
              <option value="every">每隔一段时间</option>
              <option value="custom">自定义 Cron</option>
            </select>

            {scheduleKind === 'at' ? (
              <input
                className="settings-input"
                type="datetime-local"
                value={taskAtValue}
                onChange={(event) => setTaskAtValue(event.target.value)}
              />
            ) : scheduleKind === 'every' ? (
              <div className="settings-cron-interval">
                <span className="settings-inline-note">每隔</span>
                <input
                  className="settings-input"
                  type="number"
                  min={1}
                  value={Math.max(1, Math.round(everySeconds / 60))}
                  onChange={(event) =>
                    setEverySeconds(Math.max(1, Number(event.target.value) || 1) * 60)
                  }
                />
                <span className="settings-inline-note">分钟</span>
              </div>
            ) : fixedCronPreset === 'custom' ? (
              <input
                className="settings-input"
                type="text"
                placeholder="0 9 * * 1-5"
                value={cronExpr}
                onChange={(event) => setCronExpr(event.target.value)}
              />
            ) : (
              <>
                {fixedCronPreset === 'weekly' ? (
                  <select
                    className="settings-select"
                    value={weeklyDay}
                    onChange={(event) => setWeeklyDay(event.target.value)}
                  >
                    {WEEKDAY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : null}
                <input
                  className="settings-input"
                  type="time"
                  value={fixedTime}
                  onChange={(event) => setFixedTime(event.target.value)}
                />
              </>
            )}
          </div>
          {scheduleKind === 'cron' ? (
            <div className="settings-cron-preview">
              <span>{cronPreview}</span>
              <code>{cronGeneratedExpr || '--'}</code>
            </div>
          ) : null}
        </div>

        <Field label="结果投递">
          <select
            className="settings-select"
            value={taskTargetSessionId}
            onChange={(event) => setTaskTargetSessionId(event.target.value)}
          >
            <option value={TASK_RESULTS_SESSION_ID}>任务结果会话（推荐）</option>
            {sessionOptions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.label}
              </option>
            ))}
            <option value="">仅执行，不发送到聊天窗口</option>
          </select>
        </Field>

        <button
          className="settings-mcp-advanced-toggle"
          onClick={() => setCronAdvancedOpen((value) => !value)}
          type="button"
        >
          {cronAdvancedOpen ? '▾ 收起高级设置' : '▸ 高级设置'}
        </button>

        {cronAdvancedOpen ? (
          <div className="settings-mcp-advanced">
            <Field label="时区" copy="使用 IANA 名称，例如 Asia/Shanghai、UTC。">
              <input
                className="settings-input"
                type="text"
                value={taskTimezone}
                onChange={(event) => setTaskTimezone(event.target.value)}
              />
            </Field>
          </div>
        ) : null}

        <div className="settings-actions settings-mcp-editor__actions">
          <button
            className="settings-button-secondary"
            onClick={closeCronEditor}
            type="button"
          >
            取消
          </button>
          <button
            className="settings-button"
            disabled={savingSection === 'automation'}
            onClick={() => void handleSaveCronJob()}
            type="button"
          >
            {savingSection === 'automation' ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    );
  };

  const renderAutomationCenter = () => {
    if (cronLoading && !cronStatus) {
      return <div className="settings-loading">正在加载定时任务...</div>;
    }

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-cron-tabs">
            <button
              className={`settings-cron-tab ${cronTab === 'scheduled' ? 'is-active' : ''}`}
              onClick={() => setCronTab('scheduled')}
              type="button"
            >
              已定时
            </button>
            <button
              className={`settings-cron-tab ${cronTab === 'completed' ? 'is-active' : ''}`}
              onClick={() => setCronTab('completed')}
              type="button"
            >
              已完成
            </button>
          </div>
          <div className="settings-mcp-toolbar__actions">
            <button
              className="settings-button"
              onClick={() => openCronEditor()}
              type="button"
            >
              + 新建定时计划
            </button>
          </div>
        </div>

        {visibleCronJobs.length === 0 ? (
          <div className="settings-mcp-empty">
            <div className="settings-mcp-empty__title">
              {cronTab === 'scheduled' ? '暂无定时任务' : '暂无已完成任务'}
            </div>
            <div className="settings-mcp-empty__hint">
              {cronTab === 'scheduled'
                ? '点击右上角 “+ 新建定时计划” 创建你的第一个自动化任务。'
                : '一次性任务执行完成后会出现在这里。'}
            </div>
          </div>
        ) : (
          <div className="settings-cron-table">
            <div className="settings-cron-row settings-cron-row--head">
              <span>标题</span>
              <span>计划于</span>
              <span>状态</span>
              <span></span>
            </div>
            {visibleCronJobs.map((job) => {
              const scheduleText =
                job.schedule.kind === 'at' && job.schedule.at_ms
                  ? formatTimestamp(job.schedule.at_ms)
                  : job.schedule.label || '--';
              const isCompleted = cronTab === 'completed';
              const statusTone = job.state.last_status === 'error' ? 'error' : 'ok';
              const statusText = statusTone === 'error' ? '执行失败' : '已完成';
              return (
                <div className="settings-cron-row" key={job.id}>
                  <button
                    className="settings-cron-row__title"
                    onClick={() => openCronEditor(job)}
                    type="button"
                    title="点击编辑"
                  >
                    {job.name}
                  </button>
                  <span className="settings-cron-row__schedule">{scheduleText}</span>
                  {isCompleted ? (
                    <span className={`settings-cron-status settings-cron-status--${statusTone}`}>
                      {statusText}
                    </span>
                  ) : (
                    <button
                      className={`settings-toggle ${job.enabled ? 'on' : ''}`}
                      disabled={cronActioningId === job.id}
                      onClick={() => void handleToggleCronJob(job)}
                      type="button"
                      aria-label={job.enabled ? '点击停用' : '点击启用'}
                    >
                      {job.enabled ? '已启用' : '已停用'}
                    </button>
                  )}
                  <div className="settings-cron-row__menu">
                    <button
                      className="settings-cron-menu-trigger"
                      onClick={() =>
                        setCronMenuOpenId((current) => (current === job.id ? null : job.id))
                      }
                      type="button"
                      aria-label="更多操作"
                    >
                      ⋯
                    </button>
                    {cronMenuOpenId === job.id ? (
                      <div className="settings-cron-menu">
                        <button
                          onClick={() => {
                            setCronMenuOpenId(null);
                            void handleRunCronJob(job.id);
                          }}
                          type="button"
                        >
                          重新执行
                        </button>
                        <button
                          onClick={() => {
                            setCronMenuOpenId(null);
                            openCronEditor(job);
                          }}
                          type="button"
                        >
                          编辑
                        </button>
                        <button
                          className="settings-cron-menu__danger"
                          onClick={() => {
                            setCronMenuOpenId(null);
                            void handleDeleteCronJob(job.id);
                          }}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {cronEditorOpen ? renderCronEditor() : null}
      </div>
    );
  };

  const renderStorageCenter = () => {
    if (storageLoading && !storageOverview) {
      return <div className="settings-loading">正在加载文件中心...</div>;
    }

    if (!storageOverview) {
      return <div className="settings-empty">当前还没有可展示的文件数据。</div>;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="已用空间" value={formatBytes(storageOverview.summary.used_bytes)} />
          <Metric label="总配额" value={formatBytes(storageOverview.summary.quota_bytes)} />
          <Metric label="待清理文件" value={`${storageOverview.summary.stale_unreferenced_file_count} 个`} />
        </div>

        <div className="settings-grid">
          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>存储概览</h3>
              <p>当前上传文件会保存在工作区里，并按你设置的清理策略自动清理。</p>
            </div>
            <div className="settings-usage-row">
              <strong>{storageUsagePercent}%</strong>
              <span>
                {formatBytes(storageOverview.summary.used_bytes)} / {formatBytes(storageOverview.summary.quota_bytes)}
              </span>
            </div>
            <div className="settings-usage-bar">
              <div className="settings-usage-fill" style={{ width: `${storageUsagePercent}%` }} />
            </div>
            <div className="settings-facts-list">
              <div className="settings-fact-row">
                <span>单文件上限</span>
                <strong>{formatBytes(storageOverview.summary.max_file_bytes)}</strong>
              </div>
              <div className="settings-fact-row">
                <span>保留天数</span>
                <strong>{storageOverview.summary.retention_days} 天</strong>
              </div>
              <div className="settings-fact-row">
                <span>清理间隔</span>
                <strong>{storageOverview.summary.cleanup_interval_hours} 小时</strong>
              </div>
              <div className="settings-fact-row">
                <span>剩余空间</span>
                <strong>{formatBytes(storageOverview.summary.available_bytes)}</strong>
              </div>
            </div>
            <div className="settings-actions">
              <button
                className="settings-button"
                disabled={storageActionPath === '__cleanup__'}
                onClick={() => void handleCleanupStorage()}
                type="button"
              >
                {storageActionPath === '__cleanup__' ? '正在清理' : '立即清理过期文件'}
              </button>
            </div>
          </section>

          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>文件列表</h3>
              <p>按引用状态筛选上传文件，并快速跳回引用它的会话。</p>
            </div>
            <div className="settings-memory-toolbar">
              <input
                className="settings-input"
                onChange={(event) => setStorageQuery(event.target.value)}
                placeholder="搜索文件名、路径或会话"
                type="text"
                value={storageQuery}
              />
              <div className="settings-filter-group">
                {[
                  ['all', '全部'],
                  ['referenced', '已引用'],
                  ['orphan', '未引用'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={`settings-filter-button ${storageFilterMode === value ? 'active' : ''}`}
                    onClick={() => setStorageFilterMode(value as StorageFilterMode)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {filteredStorageFiles.length === 0 ? (
              <div className="settings-empty">当前筛选条件下没有文件。</div>
            ) : (
              <div className="settings-file-list">
                {filteredStorageFiles.slice(0, 12).map((file) => (
                  <article className="settings-file-card" key={file.path}>
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name" title={file.name}>
                          {truncateMiddle(file.name, 36)}
                        </div>
                        <div className="settings-badges">
                          <span className="settings-badge">{badgeLabel(file)}</span>
                          <span className={`settings-badge ${file.referenced ? 'active' : ''}`}>
                            {file.referenced ? `已引用 ${file.reference_count} 次` : '未引用'}
                          </span>
                          <span className="settings-badge">{formatBytes(file.size)}</span>
                        </div>
                      </div>
                      <button
                        className="settings-button-danger"
                        disabled={!file.can_delete || storageActionPath === file.path}
                        onClick={() => void handleDeleteStoredFile(file)}
                        type="button"
                      >
                        {storageActionPath === file.path ? '删除中' : '删除'}
                      </button>
                    </div>
                    <div className="settings-file-path" title={file.path}>
                      {truncateMiddle(file.path, 72)}
                    </div>
                    <div className="settings-job-facts">
                      <span>更新于 {formatTimestamp(file.modified_at)}</span>
                      <span>{file.can_delete ? '可直接删除' : '仍被会话引用'}</span>
                    </div>
                    {file.referenced_by.length > 0 ? (
                      <div className="settings-reference-list">
                        {file.referenced_by.map((reference) => (
                          <button
                            key={`${file.path}-${reference.session_id}`}
                            className="settings-reference-pill"
                            onClick={() => {
                              navigateToSession(reference.session_id);
                            }}
                            type="button"
                          >
                            {reference.title}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    );
  };

  const renderMemoryWorkspace = () => {
    if (memoryLoading && !memoryOverview) {
      return <div className="settings-loading">正在加载记忆中心...</div>;
    }

    if (!memoryOverview) {
      return <div className="settings-empty">当前还没有可展示的记忆数据。</div>;
    }

    return (
      <div className="settings-section settings-memory-section">
        <div className="settings-metrics">
          <Metric label="长期记忆字数" value={`${longTermMeta.words} 词`} />
          <Metric label="当前上下文条目" value={`${memoryOverview.current_context.items.length} 条`} />
          <Metric label="近期归档条目" value={`${memoryOverview.archive.total} 条`} />
        </div>

        <div className="settings-memory-workspace">
          <section className="settings-panel settings-memory-editor-card">
            <div className="settings-panel-header settings-panel-header--split">
              <div>
                <h3>长期记忆</h3>
                <p>保留真正会跨会话持续生效的事实、偏好和背景，让 TokenMind 长期理解你的工作方式。</p>
              </div>
              <div className="settings-memory-actions">
                <button
                  className="settings-button-secondary"
                  onClick={() => void loadMemoryOverview('', true)}
                  type="button"
                >
                  刷新
                </button>
                <button
                  className="settings-button"
                  disabled={!memoryDraftDirty || memorySaving || !memoryOverview.long_term.editable}
                  onClick={() => void handleSaveLongTermMemory()}
                  type="button"
                >
                  {memorySaving ? '保存中' : '保存长期记忆'}
                </button>
              </div>
            </div>

            <div className="settings-memory-editor-shell">
              <textarea
                className="settings-textarea settings-memory-editor settings-memory-editor--rich"
                onChange={(event) => setMemoryDraft(event.target.value)}
                placeholder="这里还没有长期记忆。你可以记录固定偏好、工作背景和重要事实。"
                spellCheck={false}
                value={memoryDraft}
              />
            </div>

            <div className="settings-memory-editor-footer">
              <span className={`settings-badge ${memoryDraftDirty ? 'active' : ''}`}>
                {memoryDraftDirty ? '有未保存修改' : '内容已同步'}
              </span>
              <span className="settings-inline-note">
                {memoryOverview.long_term.editable ? '当前可编辑' : '当前不可编辑'}
              </span>
              <span className="settings-inline-note">最后更新 {formatTimestamp(memoryOverview.long_term.updated_at)}</span>
            </div>
          </section>

          <aside className="settings-memory-sidebar-v2">
            <section className="settings-panel">
              <div className="settings-panel-header">
                <h3>记忆状态</h3>
                <p>快速确认当前长期记忆的保存状态、规模和更新时间。</p>
              </div>
              <div className="settings-memory-stat-grid">
                <div className="settings-memory-stat-card">
                  <span>保存状态</span>
                  <strong>{memoryDraftDirty ? '有未保存修改' : '已同步'}</strong>
                </div>
                <div className="settings-memory-stat-card">
                  <span>可编辑</span>
                  <strong>{memoryOverview.long_term.editable ? '是' : '否'}</strong>
                </div>
                <div className="settings-memory-stat-card">
                  <span>字符数</span>
                  <strong>{memoryDraft.length}</strong>
                </div>
                <div className="settings-memory-stat-card">
                  <span>最后更新</span>
                  <strong>{formatTimestamp(memoryOverview.long_term.updated_at)}</strong>
                </div>
              </div>
            </section>

            <section className="settings-panel">
              <div className="settings-panel-header">
                <h3>当前上下文</h3>
                <p>这里显示当前会话里仍在参与推理的上下文，不会把历史内容全部一股脑塞进来。</p>
              </div>
              {memoryOverview.current_context.items.length === 0 ? (
                <div className="settings-empty">
                  还没有活动会话内容。开始一段对话后，这里会显示当前真正参与推理的内容。
                </div>
              ) : (
                <div className="settings-memory-card-list">
                  {memoryOverview.current_context.items.slice(0, 4).map((item, index) => (
                    <article className="settings-memory-card" key={`${item.timestamp || index}-${index}`}>
                      <div className="settings-memory-card__head">
                        <span className="settings-badge active">{memoryRoleLabel(item.role)}</span>
                        <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                      </div>
                      <SettingsMarkdown className="settings-markdown--compact" content={item.content} />
                    </article>
                  ))}
                </div>
              )}
            </section>
          </aside>
        </div>

        <section className="settings-panel settings-memory-archive-card">
          <div className="settings-panel-header">
            <h3>近期归档</h3>
            <p>已经从主上下文移出的历史片段会显示在这里，适合回看、核对和搜索，不会打扰当前工作流。</p>
          </div>
          <div className="settings-memory-toolbar">
            <input
              className="settings-input"
              onChange={(event) => setMemoryArchiveQuery(event.target.value)}
              placeholder="搜索归档内容"
              type="text"
              value={memoryArchiveQuery}
            />
            <span className="settings-badge">{memoryOverview.archive.total} 条</span>
          </div>

          {memoryOverview.archive.items.length === 0 ? (
            <div className="settings-empty">
              {memoryArchiveQuery.trim()
                ? '没有匹配当前关键字的归档内容。'
                : '还没有近期归档内容。对话足够长之后，这里会出现整理过的历史片段。'}
            </div>
          ) : (
            <div className="settings-memory-card-list settings-memory-card-list--archive">
              {memoryOverview.archive.items.slice(0, 6).map((item) => (
                <article className="settings-memory-card settings-memory-card--archive" key={item.id}>
                  <div className="settings-memory-card__head">
                    <span className="settings-badge active">归档片段</span>
                    <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <SettingsMarkdown className="settings-markdown--compact" content={item.content} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  };

  const renderMemoryWorkspaceV2 = () => {
    if (memoryLoading && !memoryOverview) {
      return <div className="settings-loading">正在加载记忆中心...</div>;
    }

    if (!memoryOverview) {
      return <div className="settings-empty">当前还没有可展示的记忆数据。</div>;
    }

    return (
      <div className="settings-section settings-memory-section settings-memory-section--v2">
        <div className="settings-metrics">
          <Metric label="长期记忆字数" value={`${longTermMeta.words} 词`} />
          <Metric label="当前上下文条目" value={`${memoryOverview.current_context.items.length} 条`} />
          <Metric label="近期归档条目" value={`${memoryOverview.archive.total} 条`} />
        </div>

        <div className="settings-memory-top">
          <section className="settings-panel settings-memory-editor-card">
            <div className="settings-panel-header settings-panel-header--split">
              <div>
                <h3>长期记忆</h3>
                <p>保留真正会跨会话持续生效的事实、偏好和背景，让 TokenMind 长期理解你的工作方式。</p>
              </div>
              <div className="settings-memory-actions">
                <button
                  className="settings-button-secondary"
                  onClick={() => void loadMemoryOverview('', true)}
                  type="button"
                >
                  刷新
                </button>
                <button
                  className="settings-button"
                  disabled={!memoryDraftDirty || memorySaving || !memoryOverview.long_term.editable}
                  onClick={() => void handleSaveLongTermMemory()}
                  type="button"
                >
                  {memorySaving ? '保存中' : '保存长期记忆'}
                </button>
              </div>
            </div>

            <div className="settings-memory-editor-shell">
              <textarea
                className="settings-textarea settings-memory-editor settings-memory-editor--rich"
                onChange={(event) => setMemoryDraft(event.target.value)}
                placeholder="这里还没有长期记忆。你可以记录固定偏好、工作背景和重要事实。"
                spellCheck={false}
                value={memoryDraft}
              />
            </div>

            <div className="settings-memory-editor-footer">
              <span className={`settings-badge ${memoryDraftDirty ? 'active' : ''}`}>
                {memoryDraftDirty ? '有未保存修改' : '内容已同步'}
              </span>
              <span className="settings-inline-note">
                {memoryOverview.long_term.editable ? '当前可编辑' : '当前不可编辑'}
              </span>
              <span className="settings-inline-note">最后更新 {formatTimestamp(memoryOverview.long_term.updated_at)}</span>
            </div>
          </section>

          <aside className="settings-panel settings-memory-summary-panel settings-memory-summary-panel--v2">
            <div className="settings-panel-header">
              <h3>记忆状态</h3>
              <p>快速确认当前长期记忆的保存状态、规模和更新时间。</p>
            </div>
            <div className="settings-memory-stat-grid settings-memory-stat-grid--stacked">
              <div className="settings-memory-stat-card">
                <span>保存状态</span>
                <strong>{memoryDraftDirty ? '有未保存修改' : '已同步'}</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>可编辑</span>
                <strong>{memoryOverview.long_term.editable ? '是' : '否'}</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>字符数</span>
                <strong>{memoryDraft.length}</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>最后更新</span>
                <strong>{formatTimestamp(memoryOverview.long_term.updated_at)}</strong>
              </div>
            </div>
          </aside>
        </div>

        <section className="settings-panel settings-memory-context-wide">
          <div className="settings-panel-header">
            <h3>当前上下文</h3>
            <p>这里显示当前会话里仍在参与推理的上下文，让你一眼知道模型此刻还“带着什么”在思考。</p>
          </div>
          {memoryOverview.current_context.items.length === 0 ? (
            <div className="settings-empty">
              还没有活动会话内容。开始一段对话后，这里会显示当前真正参与推理的内容。
            </div>
          ) : (
            <div className="settings-memory-context-grid">
              {memoryOverview.current_context.items.slice(-6).map((item, index) => (
                <article className="settings-memory-card settings-memory-card--context" key={`${item.timestamp || index}-${index}`}>
                  <div className="settings-memory-card__head">
                    <span className="settings-badge active">{memoryRoleLabel(item.role)}</span>
                    <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <SettingsMarkdown className="settings-markdown--compact" content={item.content} />
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="settings-panel settings-memory-archive-card">
          <div className="settings-panel-header">
            <h3>近期归档</h3>
            <p>已经从主上下文移出的历史片段会显示在这里，适合回看、核对和搜索，不会打扰当前工作流。</p>
          </div>
          <div className="settings-memory-toolbar">
            <input
              className="settings-input"
              onChange={(event) => setMemoryArchiveQuery(event.target.value)}
              placeholder="搜索归档内容"
              type="text"
              value={memoryArchiveQuery}
            />
            <span className="settings-badge">{memoryOverview.archive.total} 条</span>
          </div>

          {memoryOverview.archive.items.length === 0 ? (
            <div className="settings-empty">
              {memoryArchiveQuery.trim()
                ? '没有匹配当前关键字的归档内容。'
                : '还没有近期归档内容。对话足够长之后，这里会出现整理过的历史片段。'}
            </div>
          ) : (
            <div className="settings-memory-card-list settings-memory-card-list--archive">
              {memoryOverview.archive.items.slice(0, 6).map((item) => (
                <article className="settings-memory-card settings-memory-card--archive" key={item.id}>
                  <div className="settings-memory-card__head">
                    <span className="settings-badge active">归档片段</span>
                    <span className="settings-inline-note">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <SettingsMarkdown className="settings-markdown--compact" content={item.content} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  };

  const renderStorageWorkspace = () => {
    if (storageLoading && !storageOverview) {
      return <div className="settings-loading">正在加载文件中心...</div>;
    }

    if (!storageOverview) {
      return <div className="settings-empty">当前还没有可展示的文件数据。</div>;
    }

    return (
      <div className="settings-section settings-storage-section">
        <div className="settings-metrics">
          <Metric label="已用空间" value={formatBytes(storageOverview.summary.used_bytes)} />
          <Metric label="总配额" value={formatBytes(storageOverview.summary.quota_bytes)} />
          <Metric label="待清理文件" value={`${storageOverview.summary.stale_unreferenced_file_count} 个`} />
        </div>

        <div className="settings-grid">
          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>存储概览</h3>
              <p>上传的文件会保存在工作区，并按当前策略自动清理。这里先看空间，再决定是否需要手动整理。</p>
            </div>
            <div className="settings-usage-row">
              <strong>{storageUsagePercent}%</strong>
              <span>
                {formatBytes(storageOverview.summary.used_bytes)} / {formatBytes(storageOverview.summary.quota_bytes)}
              </span>
            </div>
            <div className="settings-usage-bar">
              <div className="settings-usage-fill" style={{ width: `${storageUsagePercent}%` }} />
            </div>
            <div className="settings-memory-stat-grid">
              <div className="settings-memory-stat-card">
                <span>单文件上限</span>
                <strong>{formatBytes(storageOverview.summary.max_file_bytes)}</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>保留天数</span>
                <strong>{storageOverview.summary.retention_days} 天</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>清理间隔</span>
                <strong>{storageOverview.summary.cleanup_interval_hours} 小时</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>剩余空间</span>
                <strong>{formatBytes(storageOverview.summary.available_bytes)}</strong>
              </div>
            </div>
            <div className="settings-actions">
              <button
                className="settings-button"
                disabled={storageActionPath === '__cleanup__'}
                onClick={() => void handleCleanupStorage()}
                type="button"
              >
                {storageActionPath === '__cleanup__' ? '正在清理' : '立即清理过期文件'}
              </button>
            </div>
          </section>

          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>文件列表</h3>
              <p>可以按引用状态查看文件。被会话引用的文件不会被直接删除，但现在会明确告诉你原因。</p>
            </div>
            <div className="settings-memory-toolbar">
              <input
                className="settings-input"
                onChange={(event) => setStorageQuery(event.target.value)}
                placeholder="搜索文件名、路径或会话"
                type="text"
                value={storageQuery}
              />
              <div className="settings-filter-group">
                {[
                  ['all', '全部'],
                  ['referenced', '已引用'],
                  ['orphan', '未引用'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={`settings-filter-button ${storageFilterMode === value ? 'active' : ''}`}
                    onClick={() => setStorageFilterMode(value as StorageFilterMode)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {filteredStorageFiles.length === 0 ? (
              <div className="settings-empty">当前筛选条件下没有文件。</div>
            ) : (
              <div className="settings-file-list">
                {filteredStorageFiles.slice(0, 12).map((file) => (
                  <article className="settings-file-card settings-file-card--refined" key={file.path}>
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name">{file.name}</div>
                        <div className="settings-badges">
                          <span className="settings-badge">{badgeLabel(file)}</span>
                          <span className={`settings-badge ${file.referenced ? 'active' : ''}`}>
                            {file.referenced ? `已引用 ${file.reference_count} 次` : '未引用'}
                          </span>
                          <span className="settings-badge">{formatBytes(file.size)}</span>
                        </div>
                      </div>
                      <button
                        className="settings-button-danger"
                        disabled={storageActionPath === file.path}
                        onClick={() => void handleDeleteStoredFile(file)}
                        title={file.can_delete ? '删除文件' : '文件仍被会话引用，点击查看原因'}
                        type="button"
                      >
                        {storageActionPath === file.path ? '删除中' : file.can_delete ? '删除' : '查看原因'}
                      </button>
                    </div>
                    <div className="settings-file-path">{file.path}</div>
                    <div className="settings-job-facts">
                      <span>更新于 {formatTimestamp(file.modified_at)}</span>
                      <span>{file.can_delete ? '可直接删除' : '仍被会话引用，需先解除引用'}</span>
                    </div>
                    {file.referenced_by.length > 0 ? (
                      <div className="settings-reference-list">
                        {file.referenced_by.map((reference) => (
                          <button
                            key={`${file.path}-${reference.session_id}`}
                            className="settings-reference-pill"
                            onClick={() => {
                              navigateToSession(reference.session_id);
                            }}
                            type="button"
                          >
                            {reference.title}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    );
  };

  const renderStorageWorkspaceV2 = () => {
    if (storageLoading && !storageOverview) {
      return <div className="settings-loading">正在加载文件中心...</div>;
    }

    if (!storageOverview) {
      return <div className="settings-empty">当前还没有可展示的文件数据。</div>;
    }

    return (
      <div className="settings-section settings-storage-section">
        <div className="settings-metrics">
          <Metric label="已用空间" value={formatBytes(storageOverview.summary.used_bytes)} />
          <Metric label="总配额" value={formatBytes(storageOverview.summary.quota_bytes)} />
          <Metric label="待清理文件" value={`${storageOverview.summary.stale_unreferenced_file_count} 个`} />
        </div>

        <div className="settings-grid">
          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>存储概览</h3>
              <p>上传的文件会保存在工作区，并按当前策略自动清理。你可以先看空间，再决定是否需要手动整理。</p>
            </div>
            <div className="settings-usage-row">
              <strong>{storageUsagePercent}%</strong>
              <span>
                {formatBytes(storageOverview.summary.used_bytes)} / {formatBytes(storageOverview.summary.quota_bytes)}
              </span>
            </div>
            <div className="settings-usage-bar">
              <div className="settings-usage-fill" style={{ width: `${storageUsagePercent}%` }} />
            </div>
            <div className="settings-memory-stat-grid settings-memory-stat-grid--stacked">
              <div className="settings-memory-stat-card">
                <span>单文件上限</span>
                <strong>{formatBytes(storageOverview.summary.max_file_bytes)}</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>保留天数</span>
                <strong>{storageOverview.summary.retention_days} 天</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>清理间隔</span>
                <strong>{storageOverview.summary.cleanup_interval_hours} 小时</strong>
              </div>
              <div className="settings-memory-stat-card">
                <span>剩余空间</span>
                <strong>{formatBytes(storageOverview.summary.available_bytes)}</strong>
              </div>
            </div>
            <div className="settings-actions">
              <button
                className="settings-button"
                disabled={storageActionPath === '__cleanup__'}
                onClick={() => void handleCleanupStorage()}
                type="button"
              >
                {storageActionPath === '__cleanup__' ? '正在清理' : '立即清理过期文件'}
              </button>
            </div>
          </section>

          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>文件列表</h3>
              <p>可以按引用状态查看文件。删除按钮始终保留；如果文件还被会话引用，点击后会直接告诉你原因。</p>
            </div>
            <div className="settings-memory-toolbar">
              <input
                className="settings-input"
                onChange={(event) => setStorageQuery(event.target.value)}
                placeholder="搜索文件名、路径或会话"
                type="text"
                value={storageQuery}
              />
              <div className="settings-filter-group">
                {[
                  ['all', '全部'],
                  ['referenced', '已引用'],
                  ['orphan', '未引用'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={`settings-filter-button ${storageFilterMode === value ? 'active' : ''}`}
                    onClick={() => setStorageFilterMode(value as StorageFilterMode)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {filteredStorageFiles.length === 0 ? (
              <div className="settings-empty">当前筛选条件下没有文件。</div>
            ) : (
              <div className="settings-file-list">
                {filteredStorageFiles.slice(0, 12).map((file) => (
                  <article className="settings-file-card settings-file-card--refined" key={file.path}>
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name" title={file.name}>
                          {truncateMiddle(file.name, 36)}
                        </div>
                        <div className="settings-badges">
                          <span className="settings-badge">{badgeLabel(file)}</span>
                          <span className={`settings-badge ${file.referenced ? 'active' : ''}`}>
                            {file.referenced ? `已引用 ${file.reference_count} 次` : '未引用'}
                          </span>
                          <span className="settings-badge">{formatBytes(file.size)}</span>
                        </div>
                      </div>
                      <button
                        className="settings-button-danger"
                        disabled={storageActionPath === file.path}
                        onClick={() => void handleDeleteStoredFile(file)}
                        title="删除文件"
                        type="button"
                      >
                        {storageActionPath === file.path ? '删除中' : '删除'}
                      </button>
                    </div>
                    <div className="settings-file-path" title={file.path}>
                      {truncateMiddle(file.path, 72)}
                    </div>
                    <div className="settings-job-facts">
                      <span>更新于 {formatTimestamp(file.modified_at)}</span>
                      <span>{file.can_delete ? '可直接删除' : '仍被会话引用，需先解除引用'}</span>
                    </div>
                    {file.referenced_by.length > 0 ? (
                      <div className="settings-reference-list">
                        {file.referenced_by.map((reference) => (
                          <button
                            key={`${file.path}-${reference.session_id}`}
                            className="settings-reference-pill"
                            onClick={() => {
                              navigateToSession(reference.session_id);
                            }}
                            type="button"
                          >
                            {truncateMiddle(reference.title, 26)}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    );
  };

  void renderMemoryCenter;
  void renderMemoryWorkspace;
  void renderStorageCenter;
  void renderStorageWorkspace;

  const renderRuntime = () => {
    if (!runtimeDraft) {
      return null;
    }

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-mcp-toolbar__text">
            <h3>运行时与渠道</h3>
            <p>控制 Web 服务监听、心跳，以及外部渠道能看到的中间过程。</p>
          </div>
          <div className="settings-mcp-toolbar__actions">
            <button
              className="settings-button"
              disabled={savingSection === 'runtime'}
              onClick={() => void handleSaveRuntime()}
              type="button"
            >
              {savingSection === 'runtime' ? '保存中…' : '保存'}
            </button>
          </div>
        </div>

        <div className="settings-grid">
          <div className="settings-panel">
            <div className="settings-panel-header">
              <h3>渠道行为</h3>
              <p>控制外部渠道是否看到中间过程。</p>
            </div>
            <div className="settings-grid one">
              <ToggleRow
                title="发送进度消息"
                copy="在渠道中同步助手的中间文本进度。"
                value={runtimeDraft.channels.send_progress}
                onToggle={() =>
                  setRuntimeDraft((current) =>
                    current
                      ? {
                          ...current,
                          channels: {
                            ...current.channels,
                            send_progress: !current.channels.send_progress,
                          },
                        }
                      : current
                  )
                }
              />
              <ToggleRow
                title="发送工具提示"
                copy="在渠道中展示工具调用提示。"
                value={runtimeDraft.channels.send_tool_hints}
                onToggle={() =>
                  setRuntimeDraft((current) =>
                    current
                      ? {
                          ...current,
                          channels: {
                            ...current.channels,
                            send_tool_hints: !current.channels.send_tool_hints,
                          },
                        }
                      : current
                  )
                }
              />
            </div>
          </div>

          <div className="settings-panel">
            <div className="settings-panel-header">
              <h3>网关与心跳</h3>
              <p>host、port 和心跳参数通常需要在重启服务后完全生效。</p>
            </div>
            <div className="settings-grid">
              <Field label="Host" copy="Web 服务监听地址。">
                <input
                  className="settings-input"
                  onChange={(event) =>
                    setRuntimeDraft((current) =>
                      current
                        ? {
                            ...current,
                            gateway: {
                              ...current.gateway,
                              host: event.target.value,
                            },
                          }
                        : current
                    )
                  }
                  type="text"
                  value={runtimeDraft.gateway.host}
                />
              </Field>
              <Field label="Port" copy="Web 服务端口。">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setRuntimeDraft((current) =>
                      current
                        ? {
                            ...current,
                            gateway: {
                              ...current.gateway,
                              port: Number(event.target.value) || 1,
                            },
                          }
                        : current
                    )
                  }
                  type="number"
                  value={runtimeDraft.gateway.port}
                />
              </Field>
            </div>
            <div className="settings-grid one">
              <ToggleRow
                title="启用心跳"
                copy="按固定周期执行心跳任务。"
                value={runtimeDraft.gateway.heartbeat.enabled}
                onToggle={() =>
                  setRuntimeDraft((current) =>
                    current
                      ? {
                          ...current,
                          gateway: {
                            ...current.gateway,
                            heartbeat: {
                              ...current.gateway.heartbeat,
                              enabled: !current.gateway.heartbeat.enabled,
                            },
                          },
                        }
                      : current
                  )
                }
              />
              <Field label="心跳间隔（秒）" copy="心跳任务触发间隔。">
                <input
                  className="settings-input"
                  min={1}
                  onChange={(event) =>
                    setRuntimeDraft((current) =>
                      current
                        ? {
                            ...current,
                            gateway: {
                              ...current.gateway,
                              heartbeat: {
                                ...current.gateway.heartbeat,
                                interval_s: Number(event.target.value) || 1,
                              },
                            },
                          }
                        : current
                    )
                  }
                  type="number"
                  value={runtimeDraft.gateway.heartbeat.interval_s}
                />
              </Field>
            </div>
          </div>
        </div>

      </div>
    );
  };

  const renderMcpPanel = () => {
    if (!toolsDraft) {
      return null;
    }

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-mcp-toolbar__text">
            <h3>MCP 服务</h3>
            <p>把外部工具（数据库、文件系统、API 等）通过 MCP 协议接入 TokenMind。</p>
          </div>
          <div className="settings-mcp-toolbar__actions">
            <button
              className="settings-button-secondary"
              disabled={loadingMcpCatalog || mcpEntries.length === 0}
              onClick={() => void loadMcpCatalog()}
              type="button"
            >
              {loadingMcpCatalog ? '刷新中…' : '刷新工具'}
            </button>
            <button
              className="settings-button-secondary"
              onClick={() => {
                setMcpJsonImportText('');
                setMcpJsonImportError(null);
                setMcpJsonImportOpen(true);
              }}
              type="button"
            >
              JSON 导入
            </button>
            <button
              className="settings-button"
              onClick={() => openMcpEditor(null)}
              type="button"
            >
              + 添加 MCP 服务
            </button>
          </div>
        </div>

        {mcpEntries.length === 0 ? (
          <div className="settings-mcp-empty">
            <div className="settings-mcp-empty__title">还没有配置任何 MCP 服务</div>
            <div className="settings-mcp-empty__hint">
              点击右上角 “+ 添加 MCP 服务” 开始配置，或粘贴 Claude Desktop 的 JSON 一键导入。
            </div>
          </div>
        ) : (
          <div className="settings-mcp-grid">
            {mcpEntries.map(([name, server]) => {
              const probe = mcpCatalog[name];
              const tone = getMcpConnectionTone(probe);
              const transportLabel =
                probe?.transport_type ||
                (server.type === 'streamableHttp'
                  ? 'HTTP'
                  : server.type === 'sse'
                    ? 'SSE'
                    : server.type === 'stdio'
                      ? '本地命令'
                      : '自动识别');
              return (
                <div
                  className={`settings-mcp-card ${server.enabled === false ? 'is-disabled' : ''}`}
                  key={name}
                >
                  <div className="settings-mcp-card__head">
                    <div className="settings-mcp-card__icon">
                      {server.icon ? (
                        <img src={server.icon} alt="" />
                      ) : (
                        <span>{name.charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="settings-mcp-card__title">
                      <div className="settings-mcp-card__name">{name}</div>
                      <div className="settings-mcp-card__transport">
                        {transportLabel} · {server.url || server.command || '未填写地址'}
                      </div>
                    </div>
                    <button
                      className={`settings-toggle ${server.enabled !== false ? 'on' : ''}`}
                      onClick={() => void handleToggleMcpEnabled(name, !(server.enabled !== false))}
                      type="button"
                      aria-label={server.enabled !== false ? '点击停用' : '点击启用'}
                    >
                      {server.enabled !== false ? '已启用' : '已停用'}
                    </button>
                  </div>

                  {server.notes ? (
                    <div className="settings-mcp-card__notes">{server.notes}</div>
                  ) : null}

                  <div className="settings-mcp-card__meta">
                    <span className={`settings-badge ${tone === 'connected' ? 'active' : tone === 'error' ? 'error' : ''}`}>
                      {getMcpConnectionLabel(probe)}
                    </span>
                    <span className="settings-badge">{probe?.tool_count || 0} 个工具</span>
                  </div>

                  <div className="settings-mcp-card__actions">
                    <button
                      className="settings-button-secondary"
                      onClick={() => openMcpEditor(name)}
                      type="button"
                    >
                      编辑
                    </button>
                    <button
                      className="settings-button-danger"
                      disabled={savingSection === 'mcp'}
                      onClick={() => void handleDeleteMcp(name)}
                      type="button"
                    >
                      删除
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {mcpEditorOpen ? renderMcpEditor() : null}
        {renderMcpJsonImport()}
      </div>
    );
  };

  const renderChannelEditor = () => {
    if (!channelEditorName || !channelCatalog) {
      return null;
    }
    const entry = channelCatalog.find((item) => item.name === channelEditorName);
    if (!entry) {
      return null;
    }

    const stringValue = (key: string): string => {
      const v = channelDraft[key];
      if (v == null) return '';
      if (Array.isArray(v)) return v.join(', ');
      return String(v);
    };

    const setField = (key: string, value: unknown) => {
      setChannelDraft((current) => ({ ...current, [key]: value }));
    };

    const missingRequired = entry.required.filter((field) => {
      const v = channelDraft[field];
      return v == null || (typeof v === 'string' && !v.trim()) || (Array.isArray(v) && v.length === 0);
    });
    const canEnable = missingRequired.length === 0;

    const fieldLabels: Record<string, string> = {
      app_id: 'App ID',
      app_secret: 'App Secret',
      client_id: 'Client ID',
      client_secret: 'Client Secret',
      bot_id: 'Bot ID',
      secret: 'Secret',
      encrypt_key: 'Encrypt Key（可选）',
      verification_token: 'Verification Token（可选）',
      welcome_message: '欢迎语（可选）',
      msg_format: '消息格式',
      base_url: 'Mochat 地址',
      claw_token: 'Claw Token',
      agent_user_id: '机器人用户 ID',
      allow_from: '允许的用户 / 群（多个用逗号分隔，* 表示全部）',
    };

    const renderField = (fieldKey: string) => {
      const label = fieldLabels[fieldKey] || fieldKey;

      if (fieldKey === 'msg_format') {
        return (
          <Field label={label} key={fieldKey}>
            <select
              className="settings-select"
              value={stringValue(fieldKey) || 'plain'}
              onChange={(event) => setField(fieldKey, event.target.value)}
            >
              <option value="plain">纯文本</option>
              <option value="markdown">Markdown</option>
            </select>
          </Field>
        );
      }

      if (fieldKey === 'allow_from') {
        return (
          <Field label={label} key={fieldKey}>
            <input
              className="settings-input"
              type="text"
              value={stringValue(fieldKey)}
              onChange={(event) =>
                setField(
                  fieldKey,
                  event.target.value
                    .split(',')
                    .map((item) => item.trim())
                    .filter(Boolean),
                )
              }
              placeholder="* 或 user_id1, user_id2"
            />
          </Field>
        );
      }

      const isSecret =
        fieldKey.includes('secret') ||
        fieldKey.includes('token') ||
        fieldKey === 'encrypt_key';
      const isMultiline = fieldKey === 'welcome_message';

      return (
        <Field label={label} key={fieldKey}>
          {isMultiline ? (
            <textarea
              className="settings-textarea"
              value={stringValue(fieldKey)}
              onChange={(event) => setField(fieldKey, event.target.value)}
            />
          ) : (
            <input
              className="settings-input"
              type={isSecret ? 'password' : 'text'}
              value={stringValue(fieldKey)}
              onChange={(event) => setField(fieldKey, event.target.value)}
              placeholder={isSecret ? '请输入' : ''}
            />
          )}
        </Field>
      );
    };

    return (
      <div className="settings-mcp-editor">
        <div className="settings-mcp-editor__head">
          <div>
            <h3>{entry.label}</h3>
            <div className="settings-inline-note">{entry.description}</div>
          </div>
          <button
            className="settings-mcp-editor__close"
            onClick={closeChannelEditor}
            type="button"
            aria-label="关闭编辑器"
          >
            ×
          </button>
        </div>

        <div className="settings-cron-toggle-row">
          <div className="settings-toggle-text">
            <strong>启用此渠道</strong>
            <span>
              {!canEnable && !channelDraft.enabled
                ? `请先填写：${missingRequired.join('、')}`
                : '启用后，TokenMind 会尝试连接此渠道并接收消息。'}
            </span>
          </div>
          <button
            className={`settings-toggle ${channelDraft.enabled ? 'on' : ''}`}
            disabled={!canEnable && !channelDraft.enabled}
            onClick={() => setField('enabled', !channelDraft.enabled)}
            type="button"
            title={!canEnable && !channelDraft.enabled ? '请先填写必填项' : undefined}
          >
            {channelDraft.enabled ? '已启用' : '已停用'}
          </button>
        </div>

        {entry.fields.map(renderField)}

        <div className="settings-actions settings-mcp-editor__actions">
          <button
            className="settings-button-secondary"
            onClick={closeChannelEditor}
            type="button"
          >
            取消
          </button>
          <button
            className="settings-button"
            disabled={channelSavingName === channelEditorName}
            onClick={() => void handleSaveChannel()}
            type="button"
          >
            {channelSavingName === channelEditorName ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    );
  };

  const renderChannels = () => {
    if (channelLoading && !channelCatalog) {
      return <div className="settings-loading">正在加载渠道…</div>;
    }
    const items = channelCatalog ?? [];

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-mcp-toolbar__text">
            <h3>外部渠道接入</h3>
            <p>把 TokenMind 接到飞书 / 钉钉 / 企业微信 / QQ / 个微，让你在这些应用里直接对话。</p>
          </div>
        </div>

        <div className="settings-mcp-grid">
          {items.map((entry) => {
            const isConfigured = entry.required.every((field) => {
              const v = entry.config[field];
              return typeof v === 'string' && v.trim().length > 0;
            });
            const toggleDisabled =
              channelSavingName === entry.name || (!isConfigured && !entry.enabled);
            return (
              <div
                className={`settings-mcp-card ${entry.enabled ? '' : 'is-disabled'}`}
                key={entry.name}
              >
                <div className="settings-mcp-card__head">
                  <div className="settings-mcp-card__icon settings-tools-card__icon">
                    {entry.label.charAt(0)}
                  </div>
                  <div className="settings-mcp-card__title">
                    <div className="settings-mcp-card__name">{entry.label}</div>
                    <div className="settings-mcp-card__transport">
                      {entry.enabled
                        ? '已配置启用'
                        : isConfigured
                          ? '已配置 · 待启用'
                          : '未配置'}
                    </div>
                  </div>
                  <button
                    className={`settings-toggle ${entry.enabled ? 'on' : ''}`}
                    disabled={toggleDisabled}
                    onClick={() => void handleToggleChannel(entry, !entry.enabled)}
                    type="button"
                    aria-label={entry.enabled ? '点击停用' : '点击启用'}
                    title={!isConfigured && !entry.enabled ? '请先点「配置」填写必填项' : undefined}
                  >
                    {entry.enabled ? '已启用' : '已停用'}
                  </button>
                </div>

                <div className="settings-mcp-card__notes">{entry.description}</div>

                <div className="settings-mcp-card__actions">
                  <button
                    className="settings-button-secondary"
                    onClick={() => openChannelEditor(entry)}
                    type="button"
                  >
                    配置
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {renderChannelEditor()}
      </div>
    );
  };

  const renderSkillSuggestionDetail = () => {
    const suggestion = selectedSkillSuggestion;
    if (!suggestion) {
      return null;
    }
    const busy = skillSuggestionBusy === suggestion.id;
    const kind = suggestion.kind === 'update' ? '更新已有技能' : '新增技能';
    const previewPath = suggestion.path || `workspace/skills/${suggestion.name}/SKILL.md`;

    return (
      <div
        className="settings-modal-overlay"
        role="presentation"
        onClick={() => setSelectedSkillSuggestion(null)}
      >
        <div
          className="settings-skill-detail"
          role="dialog"
          aria-modal="true"
          aria-label="技能建议详情"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="settings-skill-detail__head">
            <div>
              <span>待确认技能建议</span>
              <h3>{suggestion.name}</h3>
              <p>{suggestion.description}</p>
            </div>
            <button
              aria-label="关闭技能建议详情"
              className="settings-close"
              onClick={() => setSelectedSkillSuggestion(null)}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>

          <div className="settings-skill-detail__meta">
            <div>
              <span>类型</span>
              <code>{kind}</code>
            </div>
            {suggestion.target_skill ? (
              <div>
                <span>目标技能</span>
                <code>{suggestion.target_skill}</code>
              </div>
            ) : null}
            <div>
              <span>写入位置</span>
              <code>{previewPath}</code>
            </div>
            {suggestion.source_session_id ? (
              <div>
                <span>来源会话</span>
                <code>{suggestion.source_session_id}</code>
              </div>
            ) : null}
          </div>

          {suggestion.triggers.length > 0 ? (
            <div className="settings-skill-detail__tags">
              {suggestion.triggers.map((trigger) => (
                <span key={trigger}>{trigger}</span>
              ))}
            </div>
          ) : null}

          <div className="settings-skill-detail__preview">
            <div className="settings-skill-detail__preview-title">SKILL.md 预览</div>
            <pre>{suggestion.preview_markdown}</pre>
          </div>

          {suggestion.kind === 'update' && suggestion.diff_markdown ? (
            <div className="settings-skill-detail__preview">
              <div className="settings-skill-detail__preview-title">变更 Diff</div>
              <pre>{suggestion.diff_markdown}</pre>
            </div>
          ) : null}

          <div className="settings-provider-actions">
            <button
              className="settings-button-secondary"
              disabled={busy}
              onClick={() => void rejectSkillSuggestion(suggestion)}
              type="button"
            >
              忽略
            </button>
            <button
              className="settings-button"
              disabled={busy}
              onClick={() => void approveSkillSuggestion(suggestion)}
              type="button"
            >
              {busy ? '处理中…' : '确认保存'}
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderSkills = () => {
    if (skillsLoading && !skills) {
      return <div className="settings-loading">正在加载技能…</div>;
    }
    if (skillsError) {
      return <div className="settings-notice error">{skillsError}</div>;
    }
    const items = skills ?? [];
    const enabledCount = items.filter((item) => item.enabled).length;

    return (
      <div className="settings-section">
        <div className="settings-mcp-toolbar">
          <div className="settings-mcp-toolbar__text">
            <h3>智能体技能</h3>
            <p>
              {items.length === 0
                ? '在工作区的 skills/ 目录下放入带 SKILL.md 的文件夹后，它会自动出现在这里。'
                : `共 ${items.length} 个技能，已启用 ${enabledCount} 个。停用后智能体不会在系统提示里看到这个技能。`}
            </p>
          </div>
        </div>

        {skillSuggestions.length > 0 ? (
          <div className="settings-skill-suggestions">
            <div className="settings-skill-suggestions__head">
              <h4>待确认建议</h4>
              <span>{skillSuggestions.length} 条</span>
            </div>
            <div className="settings-skill-suggestions__list">
              {skillSuggestions.map((suggestion) => {
                const busy = skillSuggestionBusy === suggestion.id;
                return (
                  <div key={suggestion.id} className="settings-skill-suggestion">
                    <div className="settings-skill-suggestion__body">
                      <div className="settings-skill-suggestion__name">
                        {suggestion.name}
                        {suggestion.kind === 'update' ? ' · 更新' : ''}
                      </div>
                      <div className="settings-skill-suggestion__desc">{suggestion.description}</div>
                      {suggestion.triggers.length > 0 ? (
                        <div className="settings-skill-suggestion__tags">
                          {suggestion.triggers.slice(0, 4).map((trigger) => (
                            <span key={trigger}>{trigger}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="settings-skill-suggestion__actions">
                      <button
                        className="settings-button-secondary"
                        disabled={busy}
                        onClick={() => void rejectSkillSuggestion(suggestion)}
                        type="button"
                      >
                        忽略
                      </button>
                      <button
                        className="settings-button"
                        disabled={busy}
                        onClick={() => setSelectedSkillSuggestion(suggestion)}
                        type="button"
                      >
                        查看详情
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {items.length === 0 ? (
          <div className="settings-mcp-empty">
            <div className="settings-mcp-empty__title">还没有安装技能</div>
            <div className="settings-mcp-empty__hint">
              将带有 <code>SKILL.md</code> 的目录放进 <code>workspace/skills/</code>，刷新即可加载。
            </div>
          </div>
        ) : (
          <div className="settings-mcp-grid">
            {items.map((item) => {
              const busy = togglingSkill === item.name;
              return (
                <div
                  key={item.name}
                  className={`settings-mcp-card ${item.enabled ? '' : 'is-disabled'}`}
                >
                  <div className="settings-mcp-card__head">
                    <div className="settings-mcp-card__icon">
                      {item.emoji ? (
                        <span>{item.emoji}</span>
                      ) : (
                        <span>{item.name.charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="settings-mcp-card__title">
                      <div className="settings-mcp-card__name">{item.name}</div>
                      <div className="settings-mcp-card__transport">
                        {item.source === 'workspace' ? '工作区' : '内置'}
                        {item.always ? ' · 始终加载' : ''}
                      </div>
                    </div>
                    <button
                      type="button"
                      className={`settings-toggle ${item.enabled ? 'on' : ''}`}
                      onClick={() => void toggleSkillEnabled(item, !item.enabled)}
                      disabled={busy}
                      aria-label={item.enabled ? '点击停用' : '点击启用'}
                    >
                      {busy ? '处理中…' : item.enabled ? '已启用' : '已停用'}
                    </button>
                  </div>

                  {item.description ? (
                    <div className="settings-mcp-card__notes">{item.description}</div>
                  ) : null}

                  {!item.available ? (
                    <div className="settings-mcp-card__meta">
                      <span className="settings-badge error">
                        缺少依赖{item.missing_requirements ? ` · ${item.missing_requirements}` : ''}
                      </span>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
        {renderSkillSuggestionDetail()}
      </div>
    );
  };

  const renderSection = () => {
    switch (selectedSection) {
      case 'models':
        return renderModelsPanel();
      case 'tools':
        return renderTools();
      case 'memory':
        return renderMemoryWorkspaceV2();
      case 'automation':
        return renderAutomationCenter();
      case 'storage':
        return renderStorageWorkspaceV2();
      case 'mcp':
        return renderMcpPanel();
      case 'channels':
        return renderChannels();
      case 'skills':
        return renderSkills();
      case 'runtime':
        return renderRuntime();
      default:
        return null;
    }
  };

  return (
    <div className={`settings-page ${hideNav ? 'settings-page--no-nav' : ''}`}>
      <div className="settings-modal settings-modal--manus settings-modal--inline">
        {hideNav ? null : (
        <aside className="settings-sidebar">
          {onNavigateBack ? (
            <button
              className="settings-sidebar-back"
              onClick={onNavigateBack}
              type="button"
              title="返回聊天"
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M10 3.5 5.5 8 10 12.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>返回</span>
            </button>
          ) : null}

          <div className="settings-sidebar-title">设置中心</div>

          <nav className="settings-nav">
            {SECTION_META.filter((section) => !HIDDEN_NAV_SECTIONS.has(section.id)).map((section) => (
              <button
                className={`settings-nav-button ${selectedSection === section.id ? 'is-active' : ''}`}
                key={section.id}
                onClick={() => setSelectedSection(section.id)}
                type="button"
              >
                <span className="settings-nav-icon">
                  <SettingsNavIcon section={section.id} />
                </span>
                <span className="settings-nav-text">
                  <span className="settings-nav-title">{section.title}</span>
                  <span className="settings-nav-copy">{section.copy}</span>
                </span>
              </button>
            ))}
          </nav>
        </aside>
        )}

        <section className="settings-main">
          <header className="settings-header">
            <h1>{currentSectionMeta.title}</h1>
            {onClose ? (
              <button aria-label="关闭设置中心" className="settings-close" onClick={onClose} type="button">
                <CloseIcon />
              </button>
            ) : null}
          </header>

          <div className="settings-content">
            {notice ? <div className={`settings-notice ${notice.tone}`}>{notice.text}</div> : null}
            {loading || !agentDraft || !toolsDraft || !runtimeDraft || !creativeDraft ? (
              <div className="settings-loading">正在加载配置...</div>
            ) : (
              renderSection()
            )}
          </div>
        </section>

        {renderCreativeEditor()}
        {renderProviderEditor()}
        {renderKnowledgeModelEditor()}
      </div>
    </div>
  );
};

interface SettingsPageProps extends Pick<SettingsModalProps, 'initialSection' | 'hideNav'> {
  onNavigateToSession?: (sessionId: string) => void;
  onNavigateBack?: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  onNavigateToSession,
  onNavigateBack,
  initialSection,
  hideNav,
}) => (
  <SettingsModal
    onNavigateToSession={onNavigateToSession}
    onNavigateBack={onNavigateBack}
    initialSection={initialSection}
    hideNav={hideNav}
  />
);
