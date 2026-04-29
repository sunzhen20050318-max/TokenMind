import React, { useEffect, useMemo, useState } from 'react';
import { browserAgentApi } from '../services/browserAgent';
import { useBrowserAgentStore } from '../stores/browserAgentStore';
import { useChatStore } from '../stores/chatStore';
import type {
  BrowserAgentEnvCheck,
  BrowserArtifact,
  BrowserStep,
  BrowserTaskListItem,
  BrowserTaskStatus,
} from '../types/browserAgent';
import './browserAgent.css';

const STATUS_LABELS: Record<BrowserTaskStatus, string> = {
  pending: '排队中',
  running: '执行中',
  awaiting_user: '等待接管',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const PHASE_LABELS: Record<BrowserStep['phase'], string> = {
  thinking: 'Thinking',
  action: 'Action',
  observation: 'Observation',
  intervention: 'Intervention',
};

const BUSY_STATUSES = new Set<BrowserTaskStatus>(['pending', 'running', 'awaiting_user']);

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function statusClass(status: BrowserTaskStatus): string {
  return `browser-agent__status browser-agent__status--${status}`;
}

function formatFileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

function formatActionName(action: string | null | undefined): string {
  if (!action) return '等待下一步';
  const labels: Record<string, string> = {
    llm_decide: '判断下一步',
    open: '打开网页',
    snapshot: '读取页面',
    click: '点击元素',
    click_xy_fallback: '坐标兜底点击',
    fill: '填写内容',
    type: '输入文字',
    press: '按键',
    scroll: '滚动页面',
    wait: '等待页面',
    back: '返回上一页',
    forward: '前进',
    reload: '刷新页面',
    get_text: '读取文本',
    screenshot: '保存截图',
    save_page_text: '保存页面文本',
    extract: '提取数据',
    finish: '完成任务',
    await_user: '等待人工接管',
    resume: '继续执行',
    user_instruction: '追加指令',
  };
  return labels[action] || action;
}

function compactArgs(args: Record<string, unknown> | null | undefined): string | null {
  if (!args || Object.keys(args).length === 0) return null;
  return JSON.stringify(args, null, 2);
}

function initialInstructionFromMetadata(metadata: Record<string, unknown>, fallback: string): string {
  const turns = metadata.turns;
  if (!Array.isArray(turns) || turns.length === 0) {
    return fallback;
  }
  const first = turns[0];
  if (typeof first === 'object' && first !== null && 'content' in first) {
    const content = (first as { content?: unknown }).content;
    if (typeof content === 'string' && content.trim()) {
      return content;
    }
  }
  return fallback;
}

function BrowserAgentSetup({
  envCheck,
  loading,
  error,
  onRetry,
}: {
  envCheck: BrowserAgentEnvCheck | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const issues = envCheck?.issues ?? [];
  return (
    <section className="browser-agent__setup">
      <span className="browser-agent__eyebrow">Setup</span>
      <h2>启用本地浏览器控制</h2>
      <p>
        TokenMind 会调用本机 agent-browser 控制一个独立 Chrome 窗口。环境检测只检查 CLI
        和浏览器文件，不会自动弹出浏览器。
      </p>
      <div className="browser-agent__setup-steps">
        <div>
          <strong>安装 CLI</strong>
          <code>npm install -g agent-browser</code>
        </div>
        <div>
          <strong>下载浏览器内核</strong>
          <code>agent-browser install</code>
        </div>
        <div>
          <strong>手动诊断</strong>
          <code>agent-browser doctor</code>
        </div>
      </div>
      {error ? <div className="browser-agent__error">{error}</div> : null}
      {issues.length > 0 ? (
        <ul className="browser-agent__setup-issues">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
      <button type="button" className="browser-agent__button browser-agent__button--primary" onClick={onRetry} disabled={loading}>
        {loading ? '检测中...' : '重新检测'}
      </button>
    </section>
  );
}

function EnvHealth({ envCheck }: { envCheck: BrowserAgentEnvCheck | null }) {
  return (
    <section className="browser-agent__panel browser-agent__env">
      <div className="browser-agent__panel-head">
        <div>
          <span className="browser-agent__eyebrow">Environment</span>
          <h3>运行环境</h3>
        </div>
        <span className={envCheck?.is_ready ? 'browser-agent__pill is-good' : 'browser-agent__pill is-bad'}>
          {envCheck?.is_ready ? '已就绪' : '未就绪'}
        </span>
      </div>
      <div className="browser-agent__health-grid">
        <div>
          <span>CLI</span>
          <strong>{envCheck?.cli_installed ? '已安装' : '缺失'}</strong>
        </div>
        <div>
          <span>Chrome</span>
          <strong>{envCheck?.chrome_installed ? '已下载' : '缺失'}</strong>
        </div>
        <div>
          <span>版本</span>
          <strong>{envCheck?.version || '—'}</strong>
        </div>
      </div>
    </section>
  );
}

function TaskList({
  items,
  selectedId,
  loading,
  error,
  onSelect,
  onRefresh,
}: {
  items: BrowserTaskListItem[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="browser-agent__panel browser-agent__task-list">
      <div className="browser-agent__panel-head">
        <div>
          <span className="browser-agent__eyebrow">History</span>
          <h3>任务记录</h3>
        </div>
        <button type="button" className="browser-agent__button browser-agent__button--ghost" onClick={onRefresh} disabled={loading}>
          {loading ? '刷新中' : '刷新'}
        </button>
      </div>
      {error ? <div className="browser-agent__error">{error}</div> : null}
      {items.length === 0 ? (
        <div className="browser-agent__empty">还没有任务。输入一个网页目标，让 AI 开始操作。</div>
      ) : (
        <ul className="browser-agent__task-items">
          {items.map((item) => {
            const active = item.id === selectedId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className={`browser-agent__task-item ${active ? 'is-active' : ''}`}
                  onClick={() => onSelect(item.id)}
                >
                  <span className={statusClass(item.status)}>{STATUS_LABELS[item.status]}</span>
                  <strong>{item.instruction}</strong>
                  <small>
                    {formatDateTime(item.created_at)} · {item.step_count} 步 · {item.artifact_count} 个产物
                  </small>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ArtifactPanel({ artifacts }: { artifacts: BrowserArtifact[] }) {
  return (
    <section className="browser-agent__panel browser-agent__artifacts">
      <div className="browser-agent__panel-head">
        <div>
          <span className="browser-agent__eyebrow">Artifacts</span>
          <h3>浏览器产物</h3>
        </div>
      </div>
      {artifacts.length === 0 ? (
        <div className="browser-agent__empty">截图、下载文件、页面文本会出现在这里。</div>
      ) : (
        <ul>
          {artifacts.map((art) => (
            <li key={art.id}>
              <a href={browserAgentApi.artifactUrl(art.id)} target="_blank" rel="noreferrer">
                <span>{art.kind}</span>
                <strong>{(art.metadata?.label as string) || formatFileName(art.file_path)}</strong>
                <small>{Math.max(1, Math.round(art.size_bytes / 1024))} KB</small>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StepMessage({ step }: { step: BrowserStep }) {
  const isThinking = step.phase === 'thinking';
  const isObservation = step.phase === 'observation';
  const isUserTurn = step.action_name === 'user_instruction';
  const decisionAction = step.action_args?.action;
  const decisionArgs = step.action_args?.args;
  const title = isUserTurn
    ? '继续任务'
    : isThinking
      ? formatActionName(typeof decisionAction === 'string' ? decisionAction : step.action_name)
      : formatActionName(step.action_name);
  const argsText = compactArgs(
    isThinking && typeof decisionArgs === 'object' && decisionArgs !== null
      ? (decisionArgs as Record<string, unknown>)
      : step.action_args,
  );

  return (
    <article
      className={`browser-agent__message ${
        isUserTurn ? 'browser-agent__message--user' : `browser-agent__message--assistant browser-agent__message--${step.phase}`
      } ${step.success ? '' : 'is-error'}`}
    >
      <div className="browser-agent__message-meta">
        <span>{isUserTurn ? 'User' : PHASE_LABELS[step.phase]}</span>
        <span>#{step.step_index}</span>
        <time>{formatDateTime(step.timestamp)}</time>
      </div>
      <h4>{title}</h4>
      {step.thinking ? <p>{step.thinking}</p> : null}
      {step.error ? <div className="browser-agent__message-error">{step.error}</div> : null}
      {isObservation && step.observation ? (
        <details>
          <summary>查看页面快照</summary>
          <pre>{step.observation}</pre>
        </details>
      ) : null}
      {!isObservation && step.observation ? <p>{step.observation}</p> : null}
      {!isUserTurn && argsText ? (
        <details>
          <summary>参数</summary>
          <pre>{argsText}</pre>
        </details>
      ) : null}
    </article>
  );
}

function EmptyConversation() {
  return (
    <div className="browser-agent__empty-chat">
      <span>Web Agent</span>
      <h2>把网页任务交给 TokenMind</h2>
      <p>输入自然语言任务，AI 会打开本地浏览器、读取页面、点击、填写、下载并保存产物。</p>
    </div>
  );
}

function TaskConversation() {
  const {
    detail,
    detailLoading,
    detailError,
    cancelTask,
    refreshDetail,
    takeoverTask,
    resumeTask,
    intervene,
  } = useBrowserAgentStore();
  const [interveneText, setInterveneText] = useState('');
  const [intervening, setIntervening] = useState(false);

  if (!detail) {
    return (
      <section className="browser-agent__conversation">
        <EmptyConversation />
        {detailLoading ? <div className="browser-agent__loading">正在加载任务...</div> : null}
        {detailError ? <div className="browser-agent__error">{detailError}</div> : null}
      </section>
    );
  }

  const { task, steps } = detail;
  const isRunning = task.status === 'running' || task.status === 'pending';
  const isAwaitingUser = task.status === 'awaiting_user';

  const dispatch = async (
    action: Parameters<typeof intervene>[1],
    args: Record<string, unknown>,
  ) => {
    setIntervening(true);
    try {
      await intervene(task.id, action, args);
    } finally {
      setIntervening(false);
    }
  };

  const handleSendText = async () => {
    const text = interveneText.trim();
    if (!text) return;
    setInterveneText('');
    await dispatch('type', { text });
  };

  return (
    <section className="browser-agent__conversation">
      <div className="browser-agent__chat-toolbar">
        <div>
          <span className={statusClass(task.status)}>{STATUS_LABELS[task.status]}</span>
          <strong>{task.start_url || '沿用当前浏览器页面'}</strong>
        </div>
        <div className="browser-agent__toolbar-actions">
          <button type="button" className="browser-agent__button browser-agent__button--ghost" onClick={() => void refreshDetail()} disabled={detailLoading}>
            刷新
          </button>
          {isRunning ? (
            <button type="button" className="browser-agent__button browser-agent__button--ghost" onClick={() => void takeoverTask(task.id)}>
              手动接管
            </button>
          ) : null}
          {(isRunning || isAwaitingUser) ? (
            <button type="button" className="browser-agent__button browser-agent__button--danger" onClick={() => void cancelTask(task.id)}>
              取消
            </button>
          ) : null}
        </div>
      </div>

      <article className="browser-agent__message browser-agent__message--user">
        <div className="browser-agent__message-meta">
          <span>User</span>
          <time>{formatDateTime(task.created_at)}</time>
        </div>
        <h4>初始任务</h4>
        <p>{initialInstructionFromMetadata(task.metadata, task.instruction)}</p>
      </article>

      {steps.map((step) => (
        <StepMessage key={step.id} step={step} />
      ))}

      {isAwaitingUser ? (
        <section className="browser-agent__handoff">
          <span className="browser-agent__eyebrow">Human in the loop</span>
          <h3>AI 已暂停，等待你完成网页操作</h3>
          <p>请切到弹出的浏览器窗口完成登录、验证码或其他人工步骤，然后回到这里继续执行。</p>
          <div className="browser-agent__handoff-actions">
            <button type="button" className="browser-agent__button browser-agent__button--primary" onClick={() => void resumeTask(task.id)}>
              我已完成，继续执行
            </button>
            <input
              type="text"
              placeholder="可选：发送文字到当前焦点"
              value={interveneText}
              onChange={(event) => setInterveneText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void handleSendText();
                }
              }}
              disabled={intervening}
            />
            <button type="button" className="browser-agent__button browser-agent__button--ghost" onClick={() => void handleSendText()} disabled={intervening || !interveneText.trim()}>
              发送
            </button>
          </div>
          <div className="browser-agent__quick-keys">
            {['Enter', 'Tab', 'Escape', 'ArrowDown', 'ArrowUp'].map((key) => (
              <button key={key} type="button" onClick={() => void dispatch('press', { key })} disabled={intervening}>
                {key}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {task.result_summary ? (
        <div className="browser-agent__result">{task.result_summary}</div>
      ) : null}
      {task.error_detail ? (
        <div className="browser-agent__error">{task.error_detail}</div>
      ) : null}
    </section>
  );
}

export const BrowserAgentPage: React.FC = () => {
  const {
    envCheck,
    envCheckLoading,
    envCheckError,
    refreshEnvCheck,
    tasks,
    tasksLoading,
    tasksError,
    refreshTasks,
    selectTask,
    selectedTaskId,
    detail,
    submitInFlight,
    submitError,
    createTask,
    continueTask,
  } = useBrowserAgentStore();

  const activeProjectId = useChatStore((s) => s.activeProjectId);
  const fallbackProjectId = useMemo(() => activeProjectId ?? 'default', [activeProjectId]);

  const [instruction, setInstruction] = useState('');
  const [startUrl, setStartUrl] = useState('');

  useEffect(() => {
    void refreshEnvCheck();
    void refreshTasks();
  }, [refreshEnvCheck, refreshTasks]);

  const ready = !!envCheck?.is_ready;
  const task = detail?.task ?? null;
  const artifacts = detail?.artifacts ?? [];
  const hasSelectedTask = Boolean(selectedTaskId && task);
  const selectedTaskBusy = Boolean(task && BUSY_STATUSES.has(task.status));
  const composerMode = hasSelectedTask ? 'continue' : 'create';
  const submitLabel = composerMode === 'continue' ? '继续当前任务' : '开始新任务';

  const handleStartNew = () => {
    selectTask(null);
    setInstruction('');
    setStartUrl('');
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = instruction.trim();
    if (!text || selectedTaskBusy) return;

    if (task) {
      const taskId = await continueTask(task.id, {
        instruction: text,
        start_url: startUrl.trim() || undefined,
      });
      if (taskId) {
        setInstruction('');
        setStartUrl('');
      }
      return;
    }

    const taskId = await createTask({
      project_id: fallbackProjectId,
      instruction: text,
      start_url: startUrl.trim() || undefined,
      keep_browser_open: true,
    });
    if (taskId) {
      setInstruction('');
    }
  };

  return (
    <main className="browser-agent">
      <section className="browser-agent__left">
        <header className="browser-agent__topbar">
          <div>
            <span className="browser-agent__eyebrow">Browser Agent</span>
            <h1>浏览器智能体</h1>
          </div>
          <div className="browser-agent__top-actions">
            {task ? (
              <button type="button" className="browser-agent__button browser-agent__button--ghost" onClick={handleStartNew}>
                新任务
              </button>
            ) : null}
            <span className={ready ? 'browser-agent__pill is-good' : 'browser-agent__pill is-bad'}>
              {ready ? '环境已就绪' : '需要配置'}
            </span>
          </div>
        </header>

        {!ready ? (
          <BrowserAgentSetup
            envCheck={envCheck}
            loading={envCheckLoading}
            error={envCheckError}
            onRetry={() => void refreshEnvCheck()}
          />
        ) : (
          <>
            <TaskConversation />
            <form className="browser-agent__composer" onSubmit={handleSubmit}>
              <div className="browser-agent__composer-mode">
                <span>{composerMode === 'continue' ? '继续对话' : '任务输入'}</span>
                <strong>
                  {selectedTaskBusy
                    ? '当前任务正在执行，请等待完成或人工接管'
                    : composerMode === 'continue'
                      ? '将新指令追加到当前浏览器任务'
                      : '创建一个新的浏览器任务'}
                </strong>
              </div>
              <input
                type="url"
                value={startUrl}
                onChange={(event) => setStartUrl(event.target.value)}
                placeholder={composerMode === 'continue' ? '可选：输入新网址，否则沿用当前页面' : '起始网址，可选，例如 https://example.com'}
                disabled={selectedTaskBusy}
              />
              <textarea
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                rows={3}
                placeholder={
                  composerMode === 'continue'
                    ? '继续给 AI 指令，例如：返回搜索结果页，再打开第二个帖子点赞'
                    : '描述网页任务，例如：打开 GitHub 搜索 browser-use，提取 README 重点并保存页面文本'
                }
                disabled={selectedTaskBusy}
              />
              {submitError ? <div className="browser-agent__error">{submitError}</div> : null}
              <div className="browser-agent__composer-foot">
                <span>任务会在本地可见浏览器窗口中执行，登录/验证码可随时人工接管。</span>
                <button type="submit" className="browser-agent__button browser-agent__button--primary" disabled={submitInFlight || !instruction.trim() || selectedTaskBusy}>
                  {submitInFlight ? '提交中...' : submitLabel}
                </button>
              </div>
            </form>
          </>
        )}
      </section>

      <aside className="browser-agent__right">
        <section className="browser-agent__panel browser-agent__intro">
          <span className="browser-agent__eyebrow">Local session</span>
          <h3>AI 操作真实浏览器</h3>
          <p>适合查网页、填表单、提取信息、保存页面文本和下载文件。每个任务会保留可回放的执行链和产物。</p>
        </section>
        <EnvHealth envCheck={envCheck} />
        <TaskList
          items={tasks}
          selectedId={selectedTaskId}
          loading={tasksLoading}
          error={tasksError}
          onSelect={selectTask}
          onRefresh={() => void refreshTasks()}
        />
        <ArtifactPanel artifacts={artifacts} />
      </aside>
    </main>
  );
};

export default BrowserAgentPage;
