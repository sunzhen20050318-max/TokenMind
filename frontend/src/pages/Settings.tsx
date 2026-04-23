import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BrandMark } from '../components/BrandMark';
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
  McpServerSettings,
  McpServerToolsState,
  ProviderSettings,
  RuntimeSettings,
  ToolsSettings,
} from '../types/config';
import type { CronJob, CronStatus, CreateCronJobPayload } from '../types/cron';
import type { MemoryOverviewResponse } from '../types/memory';
import type { StorageFileItem, StorageOverviewResponse } from '../types/storage';
import './settings.css';

const PROVIDER_META: Record<
  string,
  {
    label: string;
    defaultModel: string;
    mode: 'api' | 'local' | 'oauth';
  }
> = {
  custom: { label: '自定义', defaultModel: 'default', mode: 'api' },
  azure_openai: { label: 'Azure OpenAI', defaultModel: 'gpt-5.2-chat', mode: 'api' },
  anthropic: { label: 'Anthropic', defaultModel: 'claude-sonnet-4-5', mode: 'api' },
  openai: { label: 'OpenAI', defaultModel: 'gpt-4o', mode: 'api' },
  openrouter: { label: 'OpenRouter', defaultModel: 'anthropic/claude-sonnet-4-5', mode: 'api' },
  deepseek: { label: 'DeepSeek', defaultModel: 'deepseek-chat', mode: 'api' },
  groq: { label: 'Groq', defaultModel: 'llama-3.3-70b-versatile', mode: 'api' },
  zhipu: { label: '智谱', defaultModel: 'glm-4', mode: 'api' },
  dashscope: { label: 'DashScope', defaultModel: 'qwen-max', mode: 'api' },
  vllm: { label: 'vLLM', defaultModel: 'llama-3.1-8b-instruct', mode: 'local' },
  ollama: { label: 'Ollama', defaultModel: 'llama3.2', mode: 'local' },
  gemini: { label: 'Gemini', defaultModel: 'gemini-2.0-flash', mode: 'api' },
  moonshot: { label: 'Moonshot', defaultModel: 'kimi-k2.5', mode: 'api' },
  minimax: { label: 'MiniMax', defaultModel: 'MiniMax-M2.7', mode: 'api' },
  aihubmix: { label: 'AiHubMix', defaultModel: 'anthropic/claude-sonnet-4-5', mode: 'api' },
  siliconflow: { label: 'SiliconFlow', defaultModel: 'Qwen/Qwen2.5-7B-Instruct', mode: 'api' },
  volcengine: { label: 'VolcEngine', defaultModel: 'doubao-1-5-pro-32k', mode: 'api' },
  volcengine_coding_plan: {
    label: 'VolcEngine Coding Plan',
    defaultModel: 'doubao-seed-1-6',
    mode: 'api',
  },
  byteplus: { label: 'BytePlus', defaultModel: 'doubao-1-5-pro-32k', mode: 'api' },
  byteplus_coding_plan: {
    label: 'BytePlus Coding Plan',
    defaultModel: 'doubao-seed-1-6',
    mode: 'api',
  },
  openai_codex: {
    label: 'OpenAI Codex',
    defaultModel: 'openai-codex/gpt-5.1-codex',
    mode: 'oauth',
  },
  github_copilot: {
    label: 'GitHub Copilot',
    defaultModel: 'github-copilot/gpt-5.3-codex',
    mode: 'oauth',
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
    description: '用于独立声音克隆页的模型配置，当前版本先提供入口和状态。',
    defaultProvider: 'minimax',
    defaultModel: 'voice-clone-01',
    usage: '独立页面',
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
  { id: 'agent', title: '智能体', copy: '管理默认模型参数、工作目录和工具预算。' },
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
  { id: 'agent', title: '智能体', copy: '管理默认模型参数、工作目录和工具预算。', group: 'core' },
  { id: 'tools', title: '工具', copy: '管理搜索、命令执行、上传和安全边界。', group: 'core' },
  { id: 'mcp', title: 'MCP', copy: '管理 MCP 服务列表和工具可见范围。', group: 'core' },
  { id: 'runtime', title: '运行时', copy: '管理进度推送、网关和心跳设置。', group: 'core' },
  { id: 'memory', title: '记忆中心', copy: '查看长期记忆、当前上下文和近期归档。', group: 'workspace' },
  { id: 'automation', title: '定时任务', copy: '统一管理自动化任务、结果投递和失败状态。', group: 'workspace' },
  { id: 'storage', title: '文件中心', copy: '管理上传文件、存储配额和清理策略。', group: 'workspace' },
] as const;

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

type SectionId = (typeof SECTION_META)[number]['id'];
type TasksScheduleKind = 'every' | 'cron' | 'at';
type FixedCronPreset = 'daily' | 'weekdays' | 'weekly' | 'custom';
type StorageFilterMode = 'all' | 'referenced' | 'orphan';

const TASK_RESULTS_SESSION_ID = 'web:task-results';
const TASK_RESULTS_SESSION_TITLE = '任务结果';
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

interface McpFormState {
  name: string;
  type: '' | 'stdio' | 'sse' | 'streamableHttp';
  command: string;
  argsText: string;
  envText: string;
  url: string;
  headersText: string;
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
  onClose: () => void;
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
    apiBase: provider?.api_base || '',
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

function emptyMcpForm(): McpFormState {
  return {
    name: '',
    type: '',
    command: '',
    argsText: '',
    envText: '',
    url: '',
    headersText: '',
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
    type: server.type || '',
    command: server.command,
    argsText: listToText(server.args),
    envText: prettyJson(server.env),
    url: server.url,
    headersText: prettyJson(server.headers),
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
  void providerId;
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
  if (section === 'agent') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 2v4" />
        <path d="M8 7h8a4 4 0 0 1 4 4v3a6 6 0 0 1-6 6h-4a6 6 0 0 1-6-6v-3a4 4 0 0 1 4-4Z" />
        <path d="M8 15h8" />
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

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const {
    currentSession,
    sessions,
    fetchModelProviders,
    loadSessions,
    setCreativeCapabilities,
    setCurrentSession,
  } = useChatStore();
  const [selectedSection, setSelectedSection] = useState<SectionId>('models');
  const [providers, setProviders] = useState<Record<string, ProviderSettings>>({});
  const [agentDraft, setAgentDraft] = useState<AgentSettings | null>(null);
  const [toolsDraft, setToolsDraft] = useState<ToolsSettings | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeSettings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState('openai');
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [providerForm, setProviderForm] = useState<ProviderFormState>(buildProviderForm('openai'));
  const [selectedMcpName, setSelectedMcpName] = useState<string | null>(null);
  const [mcpForm, setMcpForm] = useState<McpFormState>(emptyMcpForm());
  const [searchApiKeyMasked, setSearchApiKeyMasked] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingSection, setSavingSection] = useState<string | null>(null);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [creativeDraft, setCreativeDraft] = useState<CreativeSettings | null>(null);
  const [selectedCreativeId, setSelectedCreativeId] = useState<CreativeCapabilityKey>('image');
  const [editingCreativeId, setEditingCreativeId] = useState<CreativeCapabilityKey | null>(null);
  const [creativeForm, setCreativeForm] = useState<CreativeCapabilityFormState>(
    buildCreativeCapabilityForm('image')
  );
  const [mcpCatalog, setMcpCatalog] = useState<Record<string, McpServerToolsState>>({});
  const [loadingMcpCatalog, setLoadingMcpCatalog] = useState(false);
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
  const [taskName, setTaskName] = useState('早间提醒');
  const [taskMessage, setTaskMessage] = useState('请提醒我查看今天的重要事项，并整理成一段简短总结。');
  const [scheduleKind, setScheduleKind] = useState<TasksScheduleKind>('every');
  const [fixedCronPreset, setFixedCronPreset] = useState<FixedCronPreset>('weekdays');
  const [everySeconds, setEverySeconds] = useState(3600);
  const [cronExpr, setCronExpr] = useState('0 9 * * 1-5');
  const [fixedTime, setFixedTime] = useState('09:00');
  const [weeklyDay, setWeeklyDay] = useState('1');
  const [taskTimezone, setTaskTimezone] = useState('Asia/Shanghai');
  const [taskAtValue, setTaskAtValue] = useState(defaultAtValue());
  const [taskTargetSessionId, setTaskTargetSessionId] = useState(TASK_RESULTS_SESSION_ID);

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
        });

        const providerKeys = Object.keys(PROVIDER_META);
        const nextProvider =
          (data.agent.provider && data.providers[data.agent.provider] ? data.agent.provider : '') ||
          providerKeys.find((id) => data.providers[id]) ||
          providerKeys[0];
        setSelectedProviderId(nextProvider);
        setProviderForm(buildProviderForm(nextProvider, data.providers[nextProvider]));
        setCreativeForm(buildCreativeCapabilityForm('image', data.creative.image));

        const mcpKeys = Object.keys(data.tools.mcp_servers);
        const firstMcp = mcpKeys[0] || null;
        setSelectedMcpName(firstMcp);
        setMcpForm(firstMcp ? buildMcpForm(firstMcp, data.tools.mcp_servers[firstMcp]) : emptyMcpForm());
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

  const mcpEntries = useMemo(
    () => Object.entries(toolsDraft?.mcp_servers || {}).sort(([a], [b]) => a.localeCompare(b)),
    [toolsDraft]
  );
  const selectedMcpProbe = selectedMcpName ? mcpCatalog[selectedMcpName] || null : null;
  const connectedMcpCount = Object.values(mcpCatalog).filter(
    (server) => server.status === 'connected'
  ).length;

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
  const activeCronJobs = useMemo(() => cronJobs.filter((job) => job.enabled), [cronJobs]);
  const nextCronJob = useMemo(
    () =>
      [...cronJobs]
        .filter((job) => job.enabled && job.state.next_run_at_ms)
        .sort((a, b) => (a.state.next_run_at_ms || 0) - (b.state.next_run_at_ms || 0))[0],
    [cronJobs]
  );
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
  const sessionLabelMap = useMemo<Record<string, string>>(
    () => ({
      [TASK_RESULTS_SESSION_ID]: TASK_RESULTS_SESSION_TITLE,
      ...Object.fromEntries(sessionOptions.map((session) => [session.id, session.label])),
    }),
    [sessionOptions]
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
  }, [
    selectedSection,
    loading,
    memoryOverview,
    memoryLoading,
    memoryArchiveQuery,
    cronStatus,
    cronLoading,
    storageOverview,
    storageLoading,
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
      setAgentDraft((current) =>
        current
          ? {
              ...current,
              provider: response.defaults.provider,
              model: response.defaults.model,
            }
          : current
      );
      setEditingProviderId(null);
      await fetchModelProviders();
      setSuccess(`${PROVIDER_META[selectedProviderId]?.label || selectedProviderId} 配置已保存`);
    } catch (error) {
      setFailure(error, '保存提供商配置失败');
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

  const handleSaveAgent = async () => {
    if (!agentDraft) {
      return;
    }

    setSavingSection('agent');
    setNotice(null);
    try {
      const response = await api.updateAgentConfig({
        ...agentDraft,
        reasoning_effort: agentDraft.reasoning_effort || null,
      });
      setAgentDraft(response.agent);
      await fetchModelProviders();
      setSuccess('智能体默认参数已保存');
    } catch (error) {
      setFailure(error, '保存智能体参数失败');
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
                ...response.tools.knowledge,
                embedding_api_key: '',
                rerank_api_key: '',
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
        type: mcpForm.type || null,
        command: mcpForm.command.trim(),
        args: textToList(mcpForm.argsText),
        env: parseJsonObject(mcpForm.envText, 'Env'),
        url: mcpForm.url.trim(),
        headers: parseJsonObject(mcpForm.headersText, 'Headers'),
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
      setSuccess(`MCP 服务 ${nextName} 已保存`);
    } catch (error) {
      setFailure(error, '保存 MCP 服务失败');
    } finally {
      setSavingSection(null);
    }
  };

  const handleDeleteMcp = async () => {
    if (!toolsDraft || !selectedMcpName) {
      return;
    }

    setSavingSection('mcp');
    setNotice(null);
    try {
      await api.deleteMcpServer(selectedMcpName);
      const nextServers = { ...toolsDraft.mcp_servers };
      delete nextServers[selectedMcpName];
      const nextName = Object.keys(nextServers)[0] || null;

      setToolsDraft({
        ...toolsDraft,
        mcp_servers: nextServers,
      });
      setSelectedMcpName(nextName);
      setMcpForm(nextName ? buildMcpForm(nextName, nextServers[nextName]) : emptyMcpForm());
      setSuccess(`MCP 服务 ${selectedMcpName} 已删除`);
    } catch (error) {
      setFailure(error, '删除 MCP 服务失败');
    } finally {
      setSavingSection(null);
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

  const handleCreateTask = async () => {
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

      await api.createCronJob(payload);
      await loadSessions();
      await loadAutomationData(true);
      setSuccess('定时任务已创建');
    } catch (error) {
      setFailure(error, '创建定时任务失败');
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
      await loadAutomationData(true);
    } catch (error) {
      setFailure(error, '删除任务失败');
    } finally {
      setCronActioningId(null);
    }
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
              className={`settings-provider-card ${selectedProviderId === provider.id ? 'active' : ''}`}
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
          {creativeCards.map((capability) => (
            <div
              className={`settings-provider-card ${selectedCreativeId === capability.id ? 'active' : ''}`}
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
                <div>{capability.provider} / {capability.model}</div>
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
          ))}
        </div>
      </div>
    </div>
  );

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
              <div className="settings-actions">
                <button
                  className="settings-button"
                  disabled={savingSection === 'models'}
                  onClick={() => void handleSaveProvider()}
                  type="button"
                >
                  保存提供商配置
                </button>
              </div>
            </div>
          </div>
        </aside>
      </>
    );
  };

  const renderAgent = () => {
    if (!agentDraft) {
      return null;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="工作目录" value={agentDraft.workspace} />
          <Metric label="工具迭代" value={`${agentDraft.max_tool_iterations} 次`} />
          <Metric label="推理强度" value={agentDraft.reasoning_effort || '关闭'} />
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>默认参数</h3>
            <p>这些参数会影响新的会话和默认执行行为。</p>
          </div>
          <div className="settings-grid">
            <Field label="提供商" copy="可以保留 auto，也可以固定某一个提供商。">
              <select
                className="settings-select"
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current ? { ...current, provider: event.target.value } : current
                  )
                }
                value={agentDraft.provider}
              >
                <option value="auto">auto</option>
                {Object.entries(PROVIDER_META).map(([id, meta]) => (
                  <option key={id} value={id}>
                    {meta.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="模型" copy="默认模型字符串。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setAgentDraft((current) =>
                    current ? { ...current, model: event.target.value } : current
                  )
                }
                type="text"
                value={agentDraft.model}
              />
            </Field>
          </div>
          <div className="settings-grid">
            <Field label="工作目录" copy="智能体默认使用的 workspace。">
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
          <div className="settings-actions">
            <button
              className="settings-button"
              disabled={savingSection === 'agent'}
              onClick={() => void handleSaveAgent()}
              type="button"
            >
              保存智能体参数
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderTools = () => {
    if (!toolsDraft) {
      return null;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="搜索提供商" value={toolsDraft.web.search.provider} />
          <Metric label="命令超时" value={`${toolsDraft.exec.timeout} 秒`} />
          <Metric label="上传总配额" value={`${toolsDraft.uploads.max_total_mb} MB`} />
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>安全边界</h3>
            <p>建议先确定 workspace 限制和命令超时，再调整搜索提供商。</p>
          </div>
          <div className="settings-grid one">
            <ToggleRow
              title="限制工具访问工作目录"
              copy="开启后，工具会尽量只访问当前 workspace 内的内容。"
              value={toolsDraft.restrict_to_workspace}
              onToggle={() =>
                setToolsDraft((current) =>
                  current
                    ? {
                        ...current,
                        restrict_to_workspace: !current.restrict_to_workspace,
                      }
                    : current
                )
              }
            />
          </div>
        </div>

        <div className="settings-grid">
          <div className="settings-panel">
            <div className="settings-panel-header">
              <h3>Web 搜索</h3>
              <p>管理搜索提供商、代理和搜索返回数量。</p>
            </div>
            <div className="settings-grid one">
              <Field label="代理" copy="支持 HTTP 和 SOCKS5。留空表示不使用代理。">
                <input
                  className="settings-input"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            web: {
                              ...current.web,
                              proxy: event.target.value,
                            },
                          }
                        : current
                    )
                  }
                  placeholder="http://127.0.0.1:7890"
                  type="text"
                  value={toolsDraft.web.proxy || ''}
                />
              </Field>
              <Field label="搜索提供商" copy="brave / tavily / duckduckgo / searxng / jina">
                <select
                  className="settings-select"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            web: {
                              ...current.web,
                              search: {
                                ...current.web.search,
                                provider: event.target.value,
                              },
                            },
                          }
                        : current
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
              <Field
                label="搜索 API Key"
                copy={`当前显示：${searchApiKeyMasked || '未配置'}。仅在输入新值时更新。`}
              >
                <input
                  className="settings-input"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            web: {
                              ...current.web,
                              search: {
                                ...current.web.search,
                                api_key: event.target.value,
                              },
                            },
                          }
                        : current
                    )
                  }
                  placeholder="输入新的搜索 API Key"
                  type="password"
                  value={toolsDraft.web.search.api_key || ''}
                />
              </Field>
              <Field label="搜索地址" copy="SearXNG 或自定义搜索地址时使用。">
                <input
                  className="settings-input"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            web: {
                              ...current.web,
                              search: {
                                ...current.web.search,
                                base_url: event.target.value,
                              },
                            },
                          }
                        : current
                    )
                  }
                  placeholder="https://search.example.com"
                  type="text"
                  value={toolsDraft.web.search.base_url || ''}
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
                        : current
                    )
                  }
                  type="number"
                  value={toolsDraft.web.search.max_results}
                />
              </Field>
            </div>
          </div>

          <div className="settings-panel">
            <div className="settings-panel-header">
              <h3>命令执行</h3>
              <p>管理 exec 工具的超时和 PATH 追加项。</p>
            </div>
            <div className="settings-grid one">
              <Field label="超时时间" copy="超过后会取消 exec 工具。">
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
                        : current
                    )
                  }
                  type="number"
                  value={toolsDraft.exec.timeout}
                />
              </Field>
              <Field label="PATH 追加项" copy="会追加到 exec 环境里的 PATH。">
                <input
                  className="settings-input"
                  onChange={(event) =>
                    setToolsDraft((current) =>
                      current
                        ? {
                            ...current,
                            exec: {
                              ...current.exec,
                              path_append: event.target.value,
                            },
                          }
                        : current
                    )
                  }
                  placeholder="C:\\tools;D:\\bin"
                  type="text"
                  value={toolsDraft.exec.path_append}
                />
              </Field>
            </div>
          </div>

          <div className="settings-panel">
            <div className="settings-panel-header">
              <h3>审批与审计</h3>
              <p>控制 exec 的确认策略，以及是否记录关键操作审计日志。</p>
            </div>
            <div className="settings-grid one">
              <ToggleRow
                title="高风险 exec 需要确认"
                copy="Web 会话里执行命令前，先弹出确认层；如果你在会话里手动设为允许，后续会自动放行。"
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
                      : current
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
                      ? {
                          ...current,
                          audit_enabled: !current.audit_enabled,
                        }
                      : current
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
                        : current
                    )
                  }
                  type="number"
                  value={toolsDraft.exec.approval_timeout_s}
                />
              </Field>
            </div>
          </div>
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>上传与存储</h3>
            <p>控制单文件上限、总配额和自动清理周期，文件中心会直接使用这里的策略。</p>
          </div>
          <div className="settings-grid">
            <Field label="单文件上限 (MB)" copy="超过后会直接拒绝上传。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.uploads.max_file_mb}
              />
            </Field>
            <Field label="总配额 (MB)" copy="所有上传文件共享的上限。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.uploads.max_total_mb}
              />
            </Field>
            <Field label="保留天数" copy="未被任何会话引用的文件超过这个天数后可被清理。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.uploads.retention_days}
              />
            </Field>
            <Field label="清理检查间隔 (小时)" copy="后台清理器会按这个周期重新检查旧文件。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.uploads.cleanup_interval_hours}
              />
            </Field>
          </div>
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>知识库检索</h3>
            <p>配置向量库、Embedding 与可选 Rerank，让知识库回答更稳定也更可控。</p>
          </div>
          <div className="settings-grid">
            <Field label="向量后端" copy="默认推荐 Qdrant，本地单机也能直接运行。">
              <select
                className="settings-select"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            vector_backend: event.target.value,
                          },
                        }
                      : current
                  )
                }
                value={toolsDraft.knowledge.vector_backend}
              >
                <option value="qdrant">Qdrant</option>
                <option value="sqlite">SQLite（轻量兜底）</option>
              </select>
            </Field>
            <Field label="召回数量 Top-K" copy="每次检索最多召回多少条知识片段参与回答。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.knowledge.top_k}
              />
            </Field>
            <Field label="分块长度" copy="单个 chunk 的目标长度，过大会影响精度，过小会影响上下文完整性。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.knowledge.chunk_size}
              />
            </Field>
            <Field label="分块重叠" copy="相邻 chunk 的重叠长度，适当保留上下文衔接。">
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
                      : current
                  )
                }
                type="number"
                value={toolsDraft.knowledge.chunk_overlap}
              />
            </Field>
          </div>
          <div className="settings-grid">
            <Field label="Embedding 模型" copy="留空时只使用关键词检索；填写后会叠加向量召回。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            embedding_model: event.target.value,
                          },
                        }
                      : current
                  )
                }
                placeholder="text-embedding-3-small"
                type="text"
                value={toolsDraft.knowledge.embedding_model}
              />
            </Field>
            <Field label="Embedding Base URL" copy="使用兼容 OpenAI 的 embedding 服务时可填写自定义地址。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            embedding_api_base: event.target.value || null,
                          },
                        }
                      : current
                  )
                }
                placeholder="https://api.openai.com/v1"
                type="text"
                value={toolsDraft.knowledge.embedding_api_base ?? ''}
              />
            </Field>
            <Field label="Embedding API Key" copy="出于安全考虑，保存后这里会重新变空。">
              <input
                autoComplete="off"
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            embedding_api_key: event.target.value,
                          },
                        }
                      : current
                  )
                }
                placeholder={toolsDraft.knowledge.embedding_model ? 'sk-...' : '未启用 embedding 时可留空'}
                type="password"
                value={toolsDraft.knowledge.embedding_api_key}
              />
            </Field>
          </div>
          <div className="settings-grid">
            <Field label="Rerank 模型" copy="可选增强。先粗召回，再用该模型重排结果，适合资料较多时提高命中质量。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            rerank_model: event.target.value,
                          },
                        }
                      : current
                  )
                }
                placeholder="留空则关闭 rerank"
                type="text"
                value={toolsDraft.knowledge.rerank_model}
              />
            </Field>
            <Field label="Rerank Base URL" copy="使用兼容服务时可填写自定义地址。">
              <input
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            rerank_api_base: event.target.value || null,
                          },
                        }
                      : current
                  )
                }
                placeholder="https://api.openai.com/v1"
                type="text"
                value={toolsDraft.knowledge.rerank_api_base ?? ''}
              />
            </Field>
            <Field label="Rerank API Key" copy="如果启用了 rerank，需要填写对应服务的密钥。">
              <input
                autoComplete="off"
                className="settings-input"
                onChange={(event) =>
                  setToolsDraft((current) =>
                    current
                      ? {
                          ...current,
                          knowledge: {
                            ...current.knowledge,
                            rerank_api_key: event.target.value,
                          },
                        }
                      : current
                  )
                }
                placeholder={toolsDraft.knowledge.rerank_model ? 'sk-...' : '未启用 rerank 时可留空'}
                type="password"
                value={toolsDraft.knowledge.rerank_api_key}
              />
            </Field>
            <Field label="Rerank 重排条数" copy="进入重排阶段的候选片段数量。">
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
                            rerank_top_n: Number(event.target.value) || 1,
                          },
                        }
                      : current
                  )
                }
                type="number"
                value={toolsDraft.knowledge.rerank_top_n}
              />
            </Field>
          </div>
        </div>

        <div className="settings-actions">
          <button
            className="settings-button"
            disabled={savingSection === 'tools'}
            onClick={() => void handleSaveTools()}
            type="button"
          >
            保存工具配置
          </button>
        </div>
      </div>
    );
  };

  const renderMcp = () => {
    if (!toolsDraft) {
      return null;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="已登记服务" value={`${mcpEntries.length} 个`} />
          <Metric label="当前选择" value={selectedMcpName || '新建服务'} />
          <Metric label="工具范围" value={mcpForm.enabledToolsText || '*'} />
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>MCP 服务</h3>
            <p>这里保存的是 MCP 服务定义，不是实时运行状态。</p>
          </div>
          <div className="settings-split">
            <div className="settings-list">
              <button
                className={`settings-list-item ${selectedMcpName === null ? 'active' : ''}`}
                onClick={() => {
                  setSelectedMcpName(null);
                  setMcpForm(emptyMcpForm());
                }}
                type="button"
              >
                <div className="settings-list-head">
                  <div>
                    <div className="settings-provider-name">新建服务</div>
                    <div className="settings-provider-desc">创建一条新的 MCP 服务配置。</div>
                  </div>
                </div>
              </button>

              {mcpEntries.length === 0 ? (
                <div className="settings-empty">当前还没有 MCP 服务配置。</div>
              ) : (
                mcpEntries.map(([name, server]) => (
                  <button
                    className={`settings-list-item ${selectedMcpName === name ? 'active' : ''}`}
                    key={name}
                    onClick={() => setSelectedMcpName(name)}
                    type="button"
                  >
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name">{name}</div>
                        <div className="settings-provider-desc">
                          {server.type || 'auto'} · {server.command || server.url || '未填写地址'}
                        </div>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="settings-panel">
              <div className="settings-grid">
                <Field label="服务名称" copy="作为配置字典的 key，同名会覆盖。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setMcpForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="filesystem"
                    type="text"
                    value={mcpForm.name}
                  />
                </Field>
                <Field label="类型" copy="留空时由后端自动识别。">
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
                    <option value="stdio">stdio</option>
                    <option value="sse">sse</option>
                    <option value="streamableHttp">streamableHttp</option>
                  </select>
                </Field>
              </div>
              <div className="settings-grid">
                <Field label="命令" copy="stdio 模式下的启动命令。">
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
                <Field label="URL" copy="HTTP 或 SSE 模式下的服务地址。">
                  <input
                    className="settings-input"
                    onChange={(event) =>
                      setMcpForm((current) => ({ ...current, url: event.target.value }))
                    }
                    placeholder="http://localhost:3001/sse"
                    type="text"
                    value={mcpForm.url}
                  />
                </Field>
              </div>
              <div className="settings-grid">
                <Field label="参数列表" copy="每行一个参数，也支持逗号分隔。">
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setMcpForm((current) => ({ ...current, argsText: event.target.value }))
                    }
                    placeholder="-y&#10;@modelcontextprotocol/server-filesystem"
                    value={mcpForm.argsText}
                  />
                </Field>
                <Field label="允许的工具" copy="每行一个工具名，使用 * 表示全部。">
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setMcpForm((current) => ({
                        ...current,
                        enabledToolsText: event.target.value,
                      }))
                    }
                    placeholder="*"
                    value={mcpForm.enabledToolsText}
                  />
                </Field>
              </div>
              <div className="settings-grid">
                <Field label="环境变量" copy="JSON 对象，留空表示不设置。">
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setMcpForm((current) => ({ ...current, envText: event.target.value }))
                    }
                    placeholder='{"ROOT":"D:/project"}'
                    value={mcpForm.envText}
                  />
                </Field>
                <Field label="请求头" copy="JSON 对象，HTTP 和 SSE 模式常用。">
                  <textarea
                    className="settings-textarea"
                    onChange={(event) =>
                      setMcpForm((current) => ({ ...current, headersText: event.target.value }))
                    }
                    placeholder='{"Authorization":"Bearer ..."}'
                    value={mcpForm.headersText}
                  />
                </Field>
              </div>
              <div className="settings-grid one">
                <Field label="工具超时（秒）" copy="单次 MCP 工具调用的超时时间。">
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
              <div className="settings-actions">
                <button
                  className="settings-button"
                  disabled={savingSection === 'mcp'}
                  onClick={() => void handleSaveMcp()}
                  type="button"
                >
                  保存 MCP 服务
                </button>
                <button
                  className="settings-button-danger"
                  disabled={savingSection === 'mcp' || !selectedMcpName}
                  onClick={() => void handleDeleteMcp()}
                  type="button"
                >
                  删除当前服务
                </button>
              </div>
            </div>
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

  const renderAutomationCenter = () => {
    if (cronLoading && !cronStatus) {
      return <div className="settings-loading">正在加载定时任务...</div>;
    }

    return (
      <div className="settings-section">
        <div className="settings-metrics">
          <Metric label="运行状态" value={cronStatus?.enabled ? '运行中' : '未启动'} />
          <Metric label="已启用任务" value={`${activeCronJobs.length} 个`} />
          <Metric label="下次执行" value={nextCronJob ? formatTimestamp(nextCronJob.state.next_run_at_ms) : '--'} />
        </div>

        <div className="settings-grid">
          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>任务列表</h3>
              <p>这里可以统一查看、启停、立即执行和删除现有自动化任务。</p>
            </div>
            {cronJobs.length === 0 ? (
              <div className="settings-empty">还没有自动化任务。先在右侧创建一个试试看。</div>
            ) : (
              <div className="settings-job-list">
                {cronJobs.map((job) => (
                  <article className="settings-job-card" key={job.id}>
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name">{job.name}</div>
                        <div className="settings-badges">
                          <span className={`settings-badge ${job.enabled ? 'active' : ''}`}>
                            {job.enabled ? '已启用' : '已暂停'}
                          </span>
                          <span className="settings-badge">{job.schedule.label}</span>
                          <span className="settings-badge">
                            {job.deliver ? `发送到：${sessionLabelMap[job.to || ''] || job.to}` : '仅执行不发送'}
                          </span>
                        </div>
                      </div>
                      <span className="settings-inline-note">#{job.id}</span>
                    </div>
                    <div className="settings-job-message">{job.message}</div>
                    <div className="settings-job-facts">
                      <span>下次执行：{formatTimestamp(job.state.next_run_at_ms)}</span>
                      <span>最近执行：{formatTimestamp(job.state.last_run_at_ms)}</span>
                      <span>最近状态：{job.state.last_status || '--'}</span>
                    </div>
                    {job.state.last_error ? (
                      <div className="settings-inline-error">{job.state.last_error}</div>
                    ) : null}
                    <div className="settings-actions">
                      <button
                        className="settings-button"
                        disabled={cronActioningId === job.id}
                        onClick={() => void handleRunCronJob(job.id)}
                        type="button"
                      >
                        立即执行
                      </button>
                      <button
                        className="settings-button-secondary"
                        disabled={cronActioningId === job.id}
                        onClick={() => void handleToggleCronJob(job)}
                        type="button"
                      >
                        {job.enabled ? '暂停任务' : '启用任务'}
                      </button>
                      <button
                        className="settings-button-danger"
                        disabled={cronActioningId === job.id}
                        onClick={() => void handleDeleteCronJob(job.id)}
                        type="button"
                      >
                        删除
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="settings-panel">
            <div className="settings-panel-header">
              <h3>新建任务</h3>
              <p>把重复动作整理成稳定的自动化流程，让 TokenMind 按计划主动执行。</p>
            </div>
            <div className="settings-grid one">
              <Field label="任务名称" copy="给这个自动化起一个一眼能懂的名字。">
                <input className="settings-input" type="text" value={taskName} onChange={(event) => setTaskName(event.target.value)} />
              </Field>
              <Field label="执行内容" copy="这里填写任务执行时要完成的自然语言说明。">
                <textarea className="settings-textarea" value={taskMessage} onChange={(event) => setTaskMessage(event.target.value)} />
              </Field>
            </div>

            <div className="settings-segmented">
              {[
                ['every', '间隔执行'],
                ['cron', '固定时间'],
                ['at', '单次执行'],
              ].map(([kind, label]) => (
                <button
                  key={kind}
                  className={`settings-segmented-button ${scheduleKind === kind ? 'active' : ''}`}
                  onClick={() => setScheduleKind(kind as TasksScheduleKind)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>

            {scheduleKind === 'every' ? (
              <div className="settings-grid one">
                <Field label="间隔秒数" copy="例如 3600 表示每小时执行一次。">
                  <input
                    className="settings-input"
                    min={1}
                    onChange={(event) => setEverySeconds(Number(event.target.value) || 1)}
                    type="number"
                    value={everySeconds}
                  />
                </Field>
              </div>
            ) : null}

            {scheduleKind === 'cron' ? (
              <>
                <div className="settings-segmented settings-segmented--wrap">
                  {[
                    ['daily', '每天'],
                    ['weekdays', '工作日'],
                    ['weekly', '每周'],
                    ['custom', '高级 Cron'],
                  ].map(([preset, label]) => (
                    <button
                      key={preset}
                      className={`settings-segmented-button ${fixedCronPreset === preset ? 'active' : ''}`}
                      onClick={() => setFixedCronPreset(preset as FixedCronPreset)}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="settings-grid">
                  {fixedCronPreset === 'weekly' ? (
                    <Field label="每周哪一天" copy="固定每周的某一天执行。">
                      <select className="settings-select" value={weeklyDay} onChange={(event) => setWeeklyDay(event.target.value)}>
                        {WEEKDAY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                  ) : null}
                  <Field label={fixedCronPreset === 'custom' ? 'Cron 表达式' : '执行时间'} copy="支持本地时区显示和固定时刻预览。">
                    {fixedCronPreset === 'custom' ? (
                      <input
                        className="settings-input"
                        onChange={(event) => setCronExpr(event.target.value)}
                        placeholder="0 9 * * 1-5"
                        type="text"
                        value={cronExpr}
                      />
                    ) : (
                      <input className="settings-input" onChange={(event) => setFixedTime(event.target.value)} type="time" value={fixedTime} />
                    )}
                  </Field>
                  <Field label="时区" copy="默认使用 Asia/Shanghai。">
                    <input className="settings-input" onChange={(event) => setTaskTimezone(event.target.value)} type="text" value={taskTimezone} />
                  </Field>
                </div>
                <div className="settings-preview-card">
                  <strong>执行预览</strong>
                  <span>{cronPreview}</span>
                  <code>{cronGeneratedExpr || '--'}</code>
                </div>
              </>
            ) : null}

            {scheduleKind === 'at' ? (
              <div className="settings-grid one">
                <Field label="执行时间" copy="一次性任务会在指定时刻触发后自动结束。">
                  <input
                    className="settings-input"
                    onChange={(event) => setTaskAtValue(event.target.value)}
                    type="datetime-local"
                    value={taskAtValue}
                  />
                </Field>
              </div>
            ) : null}

            <div className="settings-grid one">
              <Field label="结果投递" copy="执行结果默认发送到任务结果会话，也可以选择已有会话。">
                <select
                  className="settings-select"
                  onChange={(event) => setTaskTargetSessionId(event.target.value)}
                  value={taskTargetSessionId}
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
            </div>

            <div className="settings-actions">
              <button
                className="settings-button"
                disabled={savingSection === 'automation'}
                onClick={() => void handleCreateTask()}
                type="button"
              >
                {savingSection === 'automation' ? '正在创建' : '创建任务'}
              </button>
            </div>
          </section>
        </div>
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
                              setCurrentSession(reference.session_id);
                              onClose();
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
                              setCurrentSession(reference.session_id);
                              onClose();
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
                              setCurrentSession(reference.session_id);
                              onClose();
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
        <div className="settings-metrics">
          <Metric label="发送进度" value={runtimeDraft.channels.send_progress ? '开启' : '关闭'} />
          <Metric label="网关地址" value={`${runtimeDraft.gateway.host}:${runtimeDraft.gateway.port}`} />
          <Metric
            label="心跳状态"
            value={
              runtimeDraft.gateway.heartbeat.enabled
                ? `${runtimeDraft.gateway.heartbeat.interval_s} 秒`
                : '关闭'
            }
          />
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

        <div className="settings-actions">
          <button
            className="settings-button"
            disabled={savingSection === 'runtime'}
            onClick={() => void handleSaveRuntime()}
            type="button"
          >
            保存运行时配置
          </button>
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
        <div className="settings-metrics">
          <Metric label="已登记服务" value={`${mcpEntries.length} 个`} />
          <Metric label="已连通服务" value={`${connectedMcpCount} 个`} />
          <Metric
            label="当前工具数"
            value={selectedMcpName ? `${selectedMcpProbe?.tool_count || 0} 个` : '--'}
          />
        </div>

        <div className="settings-panel">
          <div className="settings-panel-header">
            <h3>MCP 工具总览</h3>
            <p>这里展示的是当前 MCP 服务实时探测到的工具列表，方便直接核对接入结果。</p>
          </div>

          <div className="settings-split">
            <div className="settings-list">
              {mcpEntries.length === 0 ? (
                <div className="settings-empty">当前还没有 MCP 服务配置。</div>
              ) : (
                mcpEntries.map(([name, server]) => (
                  <button
                    className={`settings-list-item ${selectedMcpName === name ? 'active' : ''}`}
                    key={name}
                    onClick={() => setSelectedMcpName(name)}
                    type="button"
                  >
                    <div className="settings-list-head">
                      <div>
                        <div className="settings-provider-name">{name}</div>
                        <div className="settings-provider-desc">
                          {(mcpCatalog[name]?.transport_type || server.type || 'auto') +
                            ' · ' +
                            (server.command || server.url || '未填写地址')}
                        </div>
                        <div className="settings-badges">
                          <span
                            className={`settings-badge ${
                              getMcpConnectionTone(mcpCatalog[name]) === 'connected'
                                ? 'active'
                                : getMcpConnectionTone(mcpCatalog[name]) === 'error'
                                  ? 'error'
                                  : ''
                            }`}
                          >
                            {getMcpConnectionLabel(mcpCatalog[name])}
                          </span>
                          <span className="settings-badge">
                            {mcpCatalog[name]?.tool_count || 0} 个工具
                          </span>
                        </div>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="settings-mcp-main">
              <div className="settings-panel settings-mcp-overview">
                <div className="settings-mcp-overview-row">
                  <div className="settings-mcp-overview-text">
                    <div className="settings-mcp-status">
                      <span
                        className={`settings-mcp-status-dot ${getMcpConnectionTone(selectedMcpProbe)}`}
                      />
                      <div>
                        <div className="settings-provider-name">
                          {selectedMcpName || '先选择一个 MCP 服务'}
                        </div>
                        <div className="settings-inline-note">
                          {!selectedMcpName
                            ? '左侧选择一个已保存的 MCP 服务，或先创建并保存后再来查看工具。'
                            : selectedMcpProbe?.status === 'connected'
                              ? `已探测到 ${selectedMcpProbe.tool_count} 个工具，其中 ${selectedMcpProbe.enabled_count} 个在当前配置下可用。`
                              : selectedMcpProbe?.error ||
                                '还没有拿到实时探测结果，点击右侧按钮刷新即可。'}
                        </div>
                      </div>
                    </div>

                    {selectedMcpName ? (
                      <div className="settings-mcp-facts">
                        <span className="settings-badge">
                          传输方式：{selectedMcpProbe?.transport_type || mcpForm.type || '自动识别'}
                        </span>
                        <span className="settings-badge">
                          允许范围：{mcpForm.enabledToolsText || '*'}
                        </span>
                      </div>
                    ) : null}
                  </div>

                  <button
                    className="settings-button-secondary"
                    disabled={loadingMcpCatalog || mcpEntries.length === 0}
                    onClick={() => void loadMcpCatalog()}
                    type="button"
                  >
                    {loadingMcpCatalog ? '正在刷新' : '刷新工具列表'}
                  </button>
                </div>
              </div>

              {!selectedMcpName ? (
                <div className="settings-empty">
                  当前还没有选中 MCP 服务。你可以先在下方服务配置里保存一条服务，然后再回来刷新工具列表。
                </div>
              ) : selectedMcpProbe?.status === 'error' ? (
                <div className="settings-empty">
                  {selectedMcpProbe.error || '当前服务连接失败，请检查命令、URL、Headers 或环境变量。'}
                </div>
              ) : loadingMcpCatalog && !selectedMcpProbe ? (
                <div className="settings-empty">正在探测 MCP 工具列表...</div>
              ) : selectedMcpProbe && selectedMcpProbe.tools.length > 0 ? (
                <div className="settings-mcp-tool-grid">
                  {selectedMcpProbe.tools.map((tool) => (
                    <div className="settings-mcp-tool-card" key={tool.wrapped_name}>
                      <div className="settings-list-head">
                        <div>
                          <div className="settings-provider-name">{tool.name}</div>
                          <div className="settings-mcp-tool-call">{tool.wrapped_name}</div>
                        </div>
                        <span className={`settings-badge ${tool.enabled ? 'active' : ''}`}>
                          {tool.enabled ? '已允许' : '未允许'}
                        </span>
                      </div>
                      <div className="settings-mcp-tool-desc">
                        {tool.description || '这个工具没有提供额外说明。'}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="settings-empty">当前服务已连接，但还没有探测到任何工具。</div>
              )}
            </div>
          </div>
        </div>

        <div className="settings-mcp-config">{renderMcp()}</div>
      </div>
    );
  };

  const renderSection = () => {
    switch (selectedSection) {
      case 'models':
        return renderModelsPanel();
      case 'agent':
        return renderAgent();
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
      case 'runtime':
        return renderRuntime();
      default:
        return null;
    }
  };

  return (
    <div
      className="settings-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="settings-modal settings-modal--manus" onClick={(event) => event.stopPropagation()}>
        <aside className="settings-sidebar">
          <div className="settings-profile-card">
            <div className="settings-profile-card__avatar">
              <BrandMark size={18} alt="TokenMind 标志" variant="icon" />
            </div>
            <div className="settings-profile-card__body">
              <div className="settings-profile-card__name">TokenMind</div>
              <div className="settings-profile-card__role">系统设置</div>
            </div>
            <div className="settings-profile-card__chevron" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M5.5 3.5 10 8l-4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div className="settings-sidebar-divider" />

          <div className="settings-sidebar-group-label">偏好与能力</div>

          <nav className="settings-nav">
            {SECTION_META.map((section) => (
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

          <button className="settings-sidebar-help" type="button">
            <span>获取帮助</span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M6 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10.5 5.5 4.5 11.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </aside>

        <section className="settings-main">
          <header className="settings-header">
            <div>
              <div className="settings-kicker">设置</div>
              <h1>{currentSectionMeta.title}</h1>
              <p>{currentSectionMeta.copy}</p>
            </div>
            <button aria-label="关闭设置中心" className="settings-close" onClick={onClose} type="button">
              <CloseIcon />
            </button>
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
      </div>
    </div>
  );
};
