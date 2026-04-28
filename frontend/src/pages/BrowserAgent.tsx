import React, { useEffect, useMemo, useState } from 'react';
import { browserAgentApi } from '../services/browserAgent';
import { useBrowserAgentStore } from '../stores/browserAgentStore';
import { useChatStore } from '../stores/chatStore';
import type { BrowserTaskListItem, BrowserTaskStatus } from '../types/browserAgent';
import './browserAgent.css';

const STATUS_LABELS: Record<BrowserTaskStatus, string> = {
  pending: '排队中',
  running: '执行中',
  awaiting_user: '等待你接管',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusClass(status: BrowserTaskStatus): string {
  return `browser-agent__status browser-agent__status--${status}`;
}

interface BrowserAgentSetupProps {
  envCheck: ReturnType<typeof useBrowserAgentStore.getState>['envCheck'];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

function BrowserAgentSetup({ envCheck, loading, error, onRetry }: BrowserAgentSetupProps) {
  const issues = envCheck?.issues ?? [];
  return (
    <div className="browser-agent__setup">
      <h2>启用 Web Agent 前需要完成以下准备</h2>
      <ol className="browser-agent__setup-steps">
        <li>
          <strong>安装 agent-browser CLI</strong>
          <pre>npm install -g agent-browser</pre>
        </li>
        <li>
          <strong>下载 Chrome for Testing</strong>
          <pre>agent-browser install</pre>
        </li>
        <li>
          <strong>验证安装</strong>
          <pre>agent-browser doctor</pre>
        </li>
      </ol>
      {error ? <div className="browser-agent__setup-error">{error}</div> : null}
      {issues.length > 0 ? (
        <ul className="browser-agent__setup-issues">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
      <button type="button" className="browser-agent__primary" onClick={onRetry} disabled={loading}>
        {loading ? '检测中…' : '重新检测'}
      </button>
    </div>
  );
}

interface TaskListProps {
  items: BrowserTaskListItem[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}

function TaskList({ items, selectedId, loading, error, onSelect, onRefresh }: TaskListProps) {
  return (
    <div className="browser-agent__list">
      <div className="browser-agent__list-head">
        <span>任务历史</span>
        <button type="button" onClick={onRefresh} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </button>
      </div>
      {error ? <div className="browser-agent__error">{error}</div> : null}
      {items.length === 0 ? (
        <div className="browser-agent__empty">还没有任务，提交一条任务试试。</div>
      ) : (
        <ul className="browser-agent__list-items">
          {items.map((item) => {
            const active = item.id === selectedId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className={`browser-agent__list-item ${active ? 'is-active' : ''}`}
                  onClick={() => onSelect(item.id)}
                >
                  <div className="browser-agent__list-item-row">
                    <span className={statusClass(item.status)}>{STATUS_LABELS[item.status]}</span>
                    <span className="browser-agent__list-item-time">{formatDateTime(item.created_at)}</span>
                  </div>
                  <div className="browser-agent__list-item-instr">{item.instruction}</div>
                  <div className="browser-agent__list-item-meta">
                    {item.step_count} 步 · {item.artifact_count} 个产物
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function TaskDetail() {
  const { detail, detailLoading, detailError, cancelTask, refreshDetail } = useBrowserAgentStore();
  if (!detail) {
    return (
      <div className="browser-agent__detail browser-agent__detail--empty">
        {detailLoading ? '加载任务详情…' : '从左侧选择一个任务以查看详情。'}
        {detailError ? <div className="browser-agent__error">{detailError}</div> : null}
      </div>
    );
  }

  const { task, steps, artifacts } = detail;
  const screenshot = artifacts.find((a) => a.kind === 'screenshot');
  const isRunning = task.status === 'running' || task.status === 'pending';

  return (
    <div className="browser-agent__detail">
      <div className="browser-agent__detail-head">
        <div className="browser-agent__detail-instr">{task.instruction}</div>
        <div className="browser-agent__detail-actions">
          <span className={statusClass(task.status)}>{STATUS_LABELS[task.status]}</span>
          <button type="button" onClick={() => void refreshDetail()} disabled={detailLoading}>
            {detailLoading ? '刷新中…' : '刷新'}
          </button>
          {isRunning ? (
            <button
              type="button"
              className="browser-agent__danger"
              onClick={() => void cancelTask(task.id)}
            >
              取消任务
            </button>
          ) : null}
        </div>
      </div>

      <dl className="browser-agent__detail-meta">
        <div>
          <dt>起始页</dt>
          <dd>{task.start_url || '—'}</dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{formatDateTime(task.created_at)}</dd>
        </div>
        <div>
          <dt>结束时间</dt>
          <dd>{formatDateTime(task.finished_at)}</dd>
        </div>
        <div>
          <dt>步数</dt>
          <dd>{task.step_count}</dd>
        </div>
      </dl>

      {task.result_summary ? (
        <div className="browser-agent__detail-summary">{task.result_summary}</div>
      ) : null}
      {task.error_detail ? (
        <div className="browser-agent__detail-summary browser-agent__detail-summary--error">
          {task.error_detail}
        </div>
      ) : null}

      {screenshot ? (
        <div className="browser-agent__screenshot">
          <img src={browserAgentApi.artifactUrl(screenshot.id)} alt="任务截图" />
        </div>
      ) : null}

      <ol className="browser-agent__steps">
        {steps.map((step) => (
          <li key={step.id} className={`browser-agent__step browser-agent__step--${step.phase}`}>
            <div className="browser-agent__step-head">
              <span className="browser-agent__step-index">#{step.step_index}</span>
              <span className="browser-agent__step-phase">{step.phase}</span>
              {step.action_name ? (
                <span className="browser-agent__step-action">{step.action_name}</span>
              ) : null}
              <span className="browser-agent__step-time">{formatDateTime(step.timestamp)}</span>
            </div>
            {step.action_args ? (
              <pre className="browser-agent__step-args">{JSON.stringify(step.action_args, null, 2)}</pre>
            ) : null}
            {step.observation ? (
              <pre className="browser-agent__step-observation">{step.observation}</pre>
            ) : null}
            {step.error ? <div className="browser-agent__step-error">{step.error}</div> : null}
          </li>
        ))}
      </ol>
    </div>
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
    submitInFlight,
    submitError,
    createTask,
  } = useBrowserAgentStore();

  const activeProjectId = useChatStore((s) => s.activeProjectId);
  const fallbackProjectId = useMemo(() => activeProjectId ?? 'default', [activeProjectId]);

  const [instruction, setInstruction] = useState('');
  const [startUrl, setStartUrl] = useState('https://example.com');

  useEffect(() => {
    void refreshEnvCheck();
    void refreshTasks();
  }, [refreshEnvCheck, refreshTasks]);

  const ready = !!envCheck?.is_ready;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!instruction.trim()) return;
    const taskId = await createTask({
      project_id: fallbackProjectId,
      instruction: instruction.trim(),
      start_url: startUrl.trim() || undefined,
    });
    if (taskId) {
      setInstruction('');
    }
  };

  return (
    <div className="browser-agent">
      <div className="browser-agent__head">
        <div>
          <h1>Web Agent</h1>
          <p className="browser-agent__subtitle">
            让 AI 在隔离的浏览器里替你完成网页任务（M1 版本会先自动打开页面并截图）。
          </p>
        </div>
        {envCheck ? (
          <div className="browser-agent__env-pill">
            CLI {envCheck.cli_installed ? '✓' : '✗'} · Chrome {envCheck.chrome_installed ? '✓' : '✗'}
            {envCheck.version ? ` · v${envCheck.version}` : ''}
          </div>
        ) : null}
      </div>

      {!ready ? (
        <BrowserAgentSetup
          envCheck={envCheck}
          loading={envCheckLoading}
          error={envCheckError}
          onRetry={() => void refreshEnvCheck()}
        />
      ) : (
        <div className="browser-agent__body">
          <form className="browser-agent__form" onSubmit={handleSubmit}>
            <label>
              <span>任务指令</span>
              <textarea
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                rows={3}
                placeholder="例如：打开 baidu.com 并截图首页"
              />
            </label>
            <label>
              <span>起始页（可选）</span>
              <input
                type="url"
                value={startUrl}
                onChange={(event) => setStartUrl(event.target.value)}
                placeholder="https://example.com"
              />
            </label>
            {submitError ? <div className="browser-agent__error">{submitError}</div> : null}
            <button
              type="submit"
              className="browser-agent__primary"
              disabled={submitInFlight || !instruction.trim()}
            >
              {submitInFlight ? '提交中…' : '提交任务'}
            </button>
          </form>

          <div className="browser-agent__columns">
            <TaskList
              items={tasks}
              selectedId={selectedTaskId}
              loading={tasksLoading}
              error={tasksError}
              onSelect={selectTask}
              onRefresh={() => void refreshTasks()}
            />
            <TaskDetail />
          </div>
        </div>
      )}
    </div>
  );
};

export default BrowserAgentPage;
