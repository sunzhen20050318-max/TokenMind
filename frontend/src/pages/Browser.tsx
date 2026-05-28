import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import type {
  BrowserInstallStep,
  BrowserProfile,
  BrowserRegistryEntry,
  BrowserStatusResponse,
} from '../types/browser';
import './browser.css';

interface BrowserPageProps {
  onStartChat?: (prompt: string) => void;
}

export function BrowserPage({ onStartChat }: BrowserPageProps): React.ReactElement {
  const [status, setStatus] = useState<BrowserStatusResponse | null>(null);
  const [profiles, setProfiles] = useState<BrowserProfile[]>([]);
  const [sites, setSites] = useState<BrowserRegistryEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [installing, setInstalling] = useState(false);

  const loadAll = useCallback(async (force = false) => {
    try {
      const [statusRes, profilesRes, sitesRes] = await Promise.all([
        api.getBrowserStatus(force),
        api.listBrowserProfiles(force),
        api.listSiteRegistry(),
      ]);
      setStatus(statusRes);
      setProfiles(profilesRes.items);
      setSites(sitesRes.items);
      setBannerError(null);
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : '加载浏览器状态失败');
    }
  }, []);

  useEffect(() => {
    void loadAll(false);
  }, [loadAll]);

  // While the environment isn't ready (install wizard showing), poll status so
  // steps tick green as the user installs the extension / Node / opens Chrome.
  useEffect(() => {
    if (status?.ready) return;
    const timer = window.setInterval(() => {
      void api
        .getBrowserStatus(true)
        .then((s) => setStatus(s))
        .catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, [status?.ready]);

  // When the env transitions to ready, load the registry/profiles once.
  useEffect(() => {
    if (status?.ready) void loadAll(false);
  }, [status?.ready, loadAll]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await loadAll(true);
    } finally {
      setRefreshing(false);
    }
  };

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setBannerError(null);
    try {
      const res = await api.installBrowserCli();
      setStatus(res.status);
      if (!res.success) {
        setBannerError(`安装失败：${res.message}`);
      }
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : '安装失败');
    } finally {
      setInstalling(false);
    }
  }, []);

  const handleToggleLogin = useCallback(
    async (entry: BrowserRegistryEntry, next: boolean) => {
      setBusyId(entry.id);
      try {
        const updated = await api.updateSiteRegistry(entry.id, { logged_in: next });
        setSites((prev) => prev.map((e) => (e.id === entry.id ? updated : e)));
      } catch (err) {
        setBannerError(err instanceof Error ? err.message : '更新失败');
      } finally {
        setBusyId(null);
      }
    },
    []
  );

  const handleOpenLogin = useCallback(
    async (entry: BrowserRegistryEntry) => {
      if (!status?.ready) {
        setBannerError('OpenCLI 还没准备好。请按上方提示完成安装后再试。');
        return;
      }
      setBusyId(entry.id);
      try {
        await api.openSiteForLogin(entry.id);
      } catch (err) {
        setBannerError(err instanceof Error ? err.message : '打开站点失败');
      } finally {
        setBusyId(null);
      }
    },
    [status?.ready]
  );

  const handleRemove = useCallback(async (entry: BrowserRegistryEntry) => {
    if (entry.is_preset) return;
    if (!window.confirm(`删除站点 “${entry.name}”？`)) return;
    setBusyId(entry.id);
    try {
      await api.removeSiteRegistry(entry.id);
      setSites((prev) => prev.filter((e) => e.id !== entry.id));
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setBusyId(null);
    }
  }, []);

  const handleAdd = useCallback(async (name: string, url: string) => {
    const created = await api.addSiteRegistry({ name, url });
    setSites((prev) => [...prev, created].sort((a, b) => {
      if (a.is_preset !== b.is_preset) return a.is_preset ? -1 : 1;
      return a.name.localeCompare(b.name, 'zh-Hans-CN');
    }));
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sites;
    return sites.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.hostname.toLowerCase().includes(q) ||
        s.url.toLowerCase().includes(q)
    );
  }, [sites, filter]);

  return (
    <div className="browser-page">
      <div className="browser-page__inner">
        <div className="browser-page__title">
          <div>
            <h1>浏览器</h1>
          </div>
          <div className="browser-page__title-actions">
            <button
              className="browser-button"
              type="button"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
            >
              {refreshing ? '刷新中…' : '刷新状态'}
            </button>
            {onStartChat ? (
              <button
                className="browser-button browser-button--primary"
                type="button"
                onClick={() => onStartChat('打开小红书首页')}
              >
                在聊天里开始
              </button>
            ) : null}
          </div>
        </div>

        {bannerError ? (
          <div className="browser-banner">
            {bannerError}
            <button
              type="button"
              className="browser-banner__close"
              onClick={() => setBannerError(null)}
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        ) : null}

        {status && !status.ready ? (
          <InstallWizard
            status={status}
            installing={installing}
            onInstall={() => void handleInstall()}
          />
        ) : (
          <>
            <StatusBlock status={status} profiles={profiles} />

            <div className="browser-section">
              <div className="browser-section__head">
                <h2>站点登录</h2>
                <span>
                  {sites.filter((s) => s.logged_in).length}/{sites.length} 已登录
                </span>
              </div>
              <div className="browser-page__filter">
                <input
                  type="text"
                  placeholder="按名称、域名搜索"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
                <button
                  className="browser-button"
                  type="button"
                  onClick={() => setShowAddModal(true)}
                >
                  + 添加站点
                </button>
              </div>
              {filtered.length === 0 ? (
                <div className="browser-empty">没有匹配的站点</div>
              ) : (
                <div className="browser-registry">
                  {filtered.map((entry) => (
                    <SiteRow
                      key={entry.id}
                      entry={entry}
                      ready={Boolean(status?.ready)}
                      busy={busyId === entry.id}
                      onToggle={(next) => void handleToggleLogin(entry, next)}
                      onOpen={() => void handleOpenLogin(entry)}
                      onRemove={() => void handleRemove(entry)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {showAddModal ? (
        <AddSiteModal
          onClose={() => setShowAddModal(false)}
          onSubmit={async (name, url) => {
            try {
              await handleAdd(name, url);
              setShowAddModal(false);
            } catch (err) {
              setBannerError(err instanceof Error ? err.message : '添加失败');
            }
          }}
        />
      ) : null}
    </div>
  );
}

function SiteRow({
  entry,
  ready,
  busy,
  onToggle,
  onOpen,
  onRemove,
}: {
  entry: BrowserRegistryEntry;
  ready: boolean;
  busy: boolean;
  onToggle: (next: boolean) => void;
  onOpen: () => void;
  onRemove: () => void;
}): React.ReactElement {
  return (
    <div className={`browser-row ${entry.logged_in ? 'browser-row--ok' : ''}`}>
      <div className="browser-row__main">
        <div className="browser-row__name">
          {entry.name}
          {entry.is_preset ? (
            <span className="browser-row__tag">预设</span>
          ) : (
            <span className="browser-row__tag browser-row__tag--custom">自定义</span>
          )}
        </div>
        <div className="browser-row__url" title={entry.url}>
          {entry.hostname || entry.url}
        </div>
      </div>
      <div className="browser-row__actions">
        <button
          type="button"
          className="browser-button"
          onClick={onOpen}
          disabled={busy || !ready}
          title={ready ? '在 Chrome 中打开此站点（用于登录）' : 'OpenCLI 未就绪'}
        >
          打开登录
        </button>
        <label className="browser-toggle" title="切换登录状态">
          <input
            type="checkbox"
            checked={entry.logged_in}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
          <span>{entry.logged_in ? '已登录' : '未登录'}</span>
        </label>
        {entry.is_preset ? (
          <span style={{ width: 24 }} />
        ) : (
          <button
            type="button"
            className="browser-row__delete"
            onClick={onRemove}
            disabled={busy}
            aria-label="删除"
            title="删除"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}

function AddSiteModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (name: string, url: string) => Promise<void>;
}): React.ReactElement {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !url.trim()) {
      setLocalError('名称和 URL 都不能为空');
      return;
    }
    setLocalError(null);
    setSubmitting(true);
    try {
      await onSubmit(name.trim(), url.trim());
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : '添加失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="browser-modal-backdrop" onClick={onClose}>
      <div className="browser-modal" onClick={(e) => e.stopPropagation()}>
        <h3>添加站点</h3>
        <p className="browser-modal__hint">
          填写站点名称和首页 URL。当你让 TokenMind 操作这个域名下的页面时，会自动检查这里的登录状态。
        </p>
        <form onSubmit={handleSubmit}>
          <label className="browser-modal__field">
            <span>名称</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如 Notion"
              autoFocus
            />
          </label>
          <label className="browser-modal__field">
            <span>URL</span>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="例如 https://www.notion.so"
            />
          </label>
          {localError ? <div className="browser-modal__error">{localError}</div> : null}
          <div className="browser-modal__actions">
            <button
              type="button"
              className="browser-button"
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="browser-button browser-button--primary"
              disabled={submitting}
            >
              {submitting ? '添加中…' : '添加'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const CHROME_STORE_URL =
  'https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk';
const NODE_INSTALL_URL = 'https://nodejs.org/';

function InstallWizard({
  status,
  installing,
  onInstall,
}: {
  status: BrowserStatusResponse;
  installing: boolean;
  onInstall: () => void;
}): React.ReactElement {
  const nodeOk = status.node.installed && status.node.ok;
  const opencliOk = status.opencli.installed;
  const daemonOk = status.daemon.running;

  const steps = [
    {
      key: 'node',
      n: 1,
      title: 'Node.js ≥ 20',
      done: nodeOk,
      detail: status.node.installed
        ? `已装 Node ${status.node.version}${nodeOk ? '' : `，但需 ≥ ${status.node.required_major}`}`
        : '未检测到 Node.js — OpenCLI 是 Node 包，必须先装它（npm 会随 Node 一起装）',
      action: nodeOk ? null : (
        <a className="browser-button" href={NODE_INSTALL_URL} target="_blank" rel="noreferrer noopener">
          下载 Node.js
        </a>
      ),
    },
    {
      key: 'opencli',
      n: 2,
      title: 'OpenCLI 命令行',
      done: opencliOk,
      detail: opencliOk
        ? `已安装 ${status.opencli.version || ''}`.trim()
        : '一键安装锁定版本的 OpenCLI（需要 Node 就绪）',
      action: opencliOk ? null : (
        <button
          className="browser-button browser-button--primary"
          type="button"
          onClick={onInstall}
          disabled={!nodeOk || installing}
          title={nodeOk ? '安装锁定版本的 OpenCLI' : '请先安装 Node.js'}
        >
          {installing ? '安装中…（可能要一两分钟）' : '一键安装'}
        </button>
      ),
    },
    {
      key: 'extension',
      n: 3,
      title: 'Chrome 扩展',
      done: daemonOk,
      detail: daemonOk
        ? 'Chrome 扩展已连接，daemon 在线'
        : '浏览器安全限制无法自动安装：请在 Chrome 商店添加 OpenCLI 扩展，然后保持 Chrome 打开（daemon 会自动启动）',
      action: daemonOk ? null : (
        <a className="browser-button" href={CHROME_STORE_URL} target="_blank" rel="noreferrer noopener">
          打开 Chrome 商店
        </a>
      ),
    },
  ];

  return (
    <div className="browser-wizard">
      <div className="browser-wizard__head">
        <h2>启用浏览器能力</h2>
        <p>
          TokenMind 通过 OpenCLI 驱动你登录中的 Chrome。完成下面三步后这里会自动解锁站点登录管理 —— 页面每几秒自动检测一次，无需手动刷新。
        </p>
      </div>
      <div className="browser-wizard__steps">
        {steps.map((s) => (
          <div key={s.key} className={`browser-wizard__step ${s.done ? 'browser-wizard__step--done' : ''}`}>
            <div className={`browser-wizard__badge ${s.done ? 'browser-wizard__badge--done' : ''}`}>
              {s.done ? '✓' : s.n}
            </div>
            <div className="browser-wizard__body">
              <div className="browser-wizard__title">{s.title}</div>
              <div className="browser-wizard__detail">{s.detail}</div>
            </div>
            <div className="browser-wizard__action">{s.action}</div>
          </div>
        ))}
      </div>
      <div className="browser-wizard__foot">
        <span className="browser-status__dot browser-status__dot--warn" />
        正在等待环境就绪…
      </div>
    </div>
  );
}

function StatusBlock({
  status,
  profiles,
}: {
  status: BrowserStatusResponse | null;
  profiles: BrowserProfile[];
}): React.ReactElement {
  if (!status) {
    return (
      <div className="browser-status">
        <div className="browser-status__row">
          <span className="browser-status__pill">
            <span className="browser-status__dot browser-status__dot--warn" />
            读取浏览器集成状态…
          </span>
        </div>
      </div>
    );
  }

  const pills: Array<{ label: string; tone: 'ok' | 'warn' | 'bad' }> = [
    {
      label: status.opencli.installed
        ? `OpenCLI ${status.opencli.version || ''}`.trim()
        : 'OpenCLI 未安装',
      tone: status.opencli.installed ? 'ok' : 'bad',
    },
    {
      label: status.node.installed
        ? `Node ${status.node.version}${status.node.ok ? '' : ` (需 ≥ ${status.node.required_major})`}`
        : 'Node 未安装',
      tone: status.node.installed ? (status.node.ok ? 'ok' : 'warn') : 'bad',
    },
    {
      label: status.daemon.running
        ? `Daemon 已连接 :${status.daemon.port}`
        : `Daemon 未运行 :${status.daemon.port}`,
      tone: status.daemon.running ? 'ok' : 'warn',
    },
    {
      label:
        profiles.length === 0
          ? 'Chrome profile 未连接'
          : `Chrome profile ${profiles.length} 个${
              profiles.find((p) => p.is_default)?.alias
                ? ` · 默认 ${profiles.find((p) => p.is_default)?.alias}`
                : ''
            }`,
      tone: profiles.length > 0 ? 'ok' : 'warn',
    },
  ];

  return (
    <div className="browser-status">
      <div className="browser-status__row">
        {pills.map((p) => (
          <span key={p.label} className="browser-status__pill">
            <span className={`browser-status__dot browser-status__dot--${p.tone}`} />
            {p.label}
          </span>
        ))}
      </div>
      {status.missing_steps.length > 0 ? (
        <div className="browser-status__steps">
          {status.missing_steps.map((step) => (
            <InstallStepBlock key={step.key} step={step} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function InstallStepBlock({ step }: { step: BrowserInstallStep }): React.ReactElement {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    if (!step.command) return;
    try {
      await navigator.clipboard.writeText(step.command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };
  return (
    <div className="browser-status__step">
      <span className="browser-status__step-title">{step.title}</span>
      {step.detail ? <span className="browser-status__step-detail">{step.detail}</span> : null}
      {step.command || step.url ? (
        <div className="browser-status__step-actions">
          {step.command ? (
            <>
              <span className="browser-status__code">{step.command}</span>
              <button className="browser-button" type="button" onClick={() => void handleCopy()}>
                {copied ? '已复制' : '复制命令'}
              </button>
            </>
          ) : null}
          {step.url ? (
            <a
              className="browser-button"
              href={step.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              打开链接
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
