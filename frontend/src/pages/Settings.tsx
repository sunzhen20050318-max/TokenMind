import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import { useChatStore } from '../stores/chatStore';
import type {
  AgentSettings,
  McpServerSettings,
  McpServerToolsState,
  ProviderSettings,
  RuntimeSettings,
  ToolsSettings,
} from '../types/config';
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

const SECTION_META = [
  { id: 'models', title: '模型', copy: '管理提供商、API Key 和默认模型。' },
  { id: 'agent', title: '智能体', copy: '管理默认模型参数、工作目录和工具预算。' },
  { id: 'tools', title: '工具', copy: '管理搜索、代理、命令执行和安全边界。' },
  { id: 'mcp', title: 'MCP', copy: '管理 MCP 服务列表和工具可见范围。' },
  { id: 'runtime', title: '运行时', copy: '管理渠道进度、网关和心跳设置。' },
] as const;

const SEARCH_PROVIDER_OPTIONS = ['brave', 'tavily', 'duckduckgo', 'searxng', 'jina'];
const REASONING_OPTIONS = [
  { value: '', label: '关闭' },
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
];

type SectionId = (typeof SECTION_META)[number]['id'];

interface ProviderFormState {
  apiBase: string;
  apiKey: string;
  defaultModel: string;
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

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { fetchModelProviders } = useChatStore();
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
  const [mcpCatalog, setMcpCatalog] = useState<Record<string, McpServerToolsState>>({});
  const [loadingMcpCatalog, setLoadingMcpCatalog] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await api.getConfig();
        setProviders(data.providers);
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
  }, []);

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

  const setSuccess = (text: string) => setNotice({ tone: 'success', text });
  const setFailure = (error: unknown, fallback: string) =>
    setNotice({
      tone: 'error',
      text: error instanceof Error ? error.message : fallback,
    });

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

  const openProviderEditor = (providerId: string) => {
    setSelectedProviderId(providerId);
    setEditingProviderId(providerId);
  };

  const closeProviderEditor = () => {
    setEditingProviderId(null);
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
      setEditingProviderId(null);
      await fetchModelProviders();
      setSuccess(`${PROVIDER_META[selectedProviderId]?.label || selectedProviderId} 配置已保存`);
    } catch (error) {
      setFailure(error, '保存提供商配置失败');
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
    </div>
  );

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
            <button className="settings-close" onClick={closeProviderEditor} type="button">
              关闭
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
                    placeholder='{"X-App":"SUN-AGENT"}'
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
      <div className="settings-modal" onClick={(event) => event.stopPropagation()}>
        <aside className="settings-sidebar">
          <div className="settings-kicker">SUN-AGENT</div>
          <h2>设置中心</h2>
          <p>按模块管理模型、智能体、工具和运行时配置，每个分组都可以单独保存。</p>

          <nav className="settings-nav">
            {SECTION_META.map((section) => (
              <button
                className={`settings-nav-button ${selectedSection === section.id ? 'is-active' : ''}`}
                key={section.id}
                onClick={() => setSelectedSection(section.id)}
                type="button"
              >
                <span className="settings-nav-title">{section.title}</span>
                <span className="settings-nav-copy">{section.copy}</span>
              </button>
            ))}
          </nav>

          <div className="settings-sidebar-note">
            这里集中管理真正可保存、可复用的系统设置，按模块维护会更清晰。
          </div>
        </aside>

        <section className="settings-main">
          <header className="settings-header">
            <div>
              <div className="settings-kicker">当前分组</div>
              <h1>{currentSectionMeta.title}</h1>
              <p>{currentSectionMeta.copy}</p>
            </div>
            <button className="settings-close" onClick={onClose} type="button">
              关闭
            </button>
          </header>

          <div className="settings-content">
            {notice ? <div className={`settings-notice ${notice.tone}`}>{notice.text}</div> : null}
            {loading || !agentDraft || !toolsDraft || !runtimeDraft ? (
              <div className="settings-loading">正在加载配置...</div>
            ) : (
              renderSection()
            )}
          </div>
        </section>

        {renderProviderEditor()}
      </div>
    </div>
  );
};
