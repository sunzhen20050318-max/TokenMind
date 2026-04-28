import React, { useEffect, useMemo, useRef, useState } from 'react';
import { browserAgentApi } from '../services/browserAgent';
import {
  selectLatestScreenshot,
  selectScreenshotForStep,
  useBrowserAgentStore,
} from '../stores/browserAgentStore';
import { useChatStore } from '../stores/chatStore';
import type {
  BrowserArtifact,
  BrowserStep,
  BrowserTaskListItem,
  BrowserTaskStatus,
} from '../types/browserAgent';
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
    second: '2-digit',
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

interface StepRowProps {
  step: BrowserStep;
  isFocused: boolean;
  onFocus: (stepIndex: number) => void;
}

function StepRow({ step, isFocused, onFocus }: StepRowProps) {
  return (
    <li
      className={`browser-agent__step browser-agent__step--${step.phase} ${
        isFocused ? 'is-focused' : ''
      }`}
    >
      <button
        type="button"
        className="browser-agent__step-button"
        onClick={() => onFocus(step.step_index)}
      >
        <div className="browser-agent__step-head">
          <span className="browser-agent__step-index">#{step.step_index}</span>
          <span className="browser-agent__step-phase">{step.phase}</span>
          {step.action_name ? (
            <span className="browser-agent__step-action">{step.action_name}</span>
          ) : null}
          {!step.success ? <span className="browser-agent__step-fail">失败</span> : null}
          <span className="browser-agent__step-time">{formatDateTime(step.timestamp)}</span>
        </div>
        {step.thinking ? (
          <div className="browser-agent__step-thinking">💭 {step.thinking}</div>
        ) : null}
        {step.action_args ? (
          <pre className="browser-agent__step-args">{JSON.stringify(step.action_args, null, 2)}</pre>
        ) : null}
        {step.observation ? (
          <pre className="browser-agent__step-observation">{step.observation}</pre>
        ) : null}
        {step.error ? <div className="browser-agent__step-error">{step.error}</div> : null}
      </button>
    </li>
  );
}

interface InteractiveScreenshotProps {
  artifact: BrowserArtifact;
  enabled: boolean;
  onClick: (x: number, y: number) => void;
}

/**
 * Renders a screenshot. When ``enabled`` (i.e. task is awaiting_user), clicks
 * are translated from the rendered <img> coordinate space back to the actual
 * pixel coordinates the browser used when taking the shot, then forwarded
 * via ``onClick``.
 *
 * We rely on naturalWidth/Height vs the bounding rect to compute the scale,
 * which works regardless of how the image is sized by CSS.
 */
function InteractiveScreenshot({ artifact, enabled, onClick }: InteractiveScreenshotProps) {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const handleClick = (event: React.MouseEvent<HTMLImageElement>) => {
    if (!enabled) return;
    const img = imgRef.current;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;
    const rect = img.getBoundingClientRect();
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);
    onClick(x, y);
  };
  return (
    <img
      ref={imgRef}
      src={browserAgentApi.artifactUrl(artifact.id)}
      alt="任务截图"
      className={`browser-agent__live-img ${enabled ? 'is-interactive' : ''}`}
      onClick={handleClick}
    />
  );
}

function TaskDetail() {
  const {
    detail,
    detailLoading,
    detailError,
    cancelTask,
    refreshDetail,
    focusedStepIndex,
    focusStep,
    takeoverTask,
    resumeTask,
    intervene,
  } = useBrowserAgentStore();
  const [interveneText, setInterveneText] = useState('');
  const [intervening, setIntervening] = useState(false);

  if (!detail) {
    return (
      <div className="browser-agent__detail browser-agent__detail--empty">
        {detailLoading ? '加载任务详情…' : '从左侧选择一个任务以查看详情。'}
        {detailError ? <div className="browser-agent__error">{detailError}</div> : null}
      </div>
    );
  }

  const { task, steps, artifacts } = detail;
  const isRunning = task.status === 'running' || task.status === 'pending';
  const isAwaitingUser = task.status === 'awaiting_user';

  // The focused step (if user clicked one) drives which screenshot is shown.
  // Otherwise we always show the latest one — i.e. live preview.
  const focusedShot = selectScreenshotForStep(detail, focusedStepIndex);
  const latestShot = selectLatestScreenshot(detail);
  const displayedShot = focusedShot ?? latestShot;

  const nonScreenshotArtifacts = artifacts.filter((a) => a.kind !== 'screenshot');

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

  const handleScreenshotClick = (x: number, y: number) => {
    if (!isAwaitingUser) return;
    void dispatch('click_xy', { x, y });
  };

  const handleSendText = async () => {
    const text = interveneText;
    if (!text) return;
    setInterveneText('');
    await dispatch('type', { text });
  };

  const handlePressKey = (key: string) => {
    void dispatch('press', { key });
  };

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
              onClick={() => void takeoverTask(task.id)}
            >
              立即接管
            </button>
          ) : null}
          {isAwaitingUser ? (
            <button
              type="button"
              className="browser-agent__primary"
              onClick={() => void resumeTask(task.id)}
            >
              继续 AI
            </button>
          ) : null}
          {(isRunning || isAwaitingUser) ? (
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

      <div className="browser-agent__panes">
        <div className="browser-agent__live">
          <div className="browser-agent__live-head">
            <span>
              {focusedShot
                ? `步骤 #${focusedShot.step_index} 截图`
                : isAwaitingUser
                  ? '🎮 接管中（点击截图操作）'
                  : isRunning
                    ? '实时画面'
                    : '最终画面'}
            </span>
            {focusedStepIndex !== null ? (
              <button type="button" onClick={() => focusStep(null)}>
                回到最新
              </button>
            ) : null}
          </div>
          {displayedShot ? (
            <InteractiveScreenshot
              artifact={displayedShot}
              enabled={isAwaitingUser && focusedStepIndex === null}
              onClick={handleScreenshotClick}
            />
          ) : (
            <div className="browser-agent__live-placeholder">
              {isRunning ? '等待第一帧画面…' : '本任务没有截图。'}
            </div>
          )}

          {isAwaitingUser ? (
            <div className="browser-agent__intervene">
              <div className="browser-agent__intervene-row">
                <input
                  type="text"
                  placeholder="输入文字（发送到当前焦点）"
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
                <button
                  type="button"
                  onClick={() => void handleSendText()}
                  disabled={intervening || !interveneText}
                >
                  发送
                </button>
              </div>
              <div className="browser-agent__intervene-keys">
                {['Enter', 'Tab', 'Escape', 'Backspace', 'ArrowDown', 'ArrowUp'].map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => handlePressKey(key)}
                    disabled={intervening}
                  >
                    {key}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => void dispatch('scroll', { direction: 'down' })}
                  disabled={intervening}
                >
                  向下滚
                </button>
                <button
                  type="button"
                  onClick={() => void dispatch('scroll', { direction: 'up' })}
                  disabled={intervening}
                >
                  向上滚
                </button>
                <button
                  type="button"
                  onClick={() => void dispatch('back', {})}
                  disabled={intervening}
                >
                  后退
                </button>
                <button
                  type="button"
                  onClick={() => void dispatch('reload', {})}
                  disabled={intervening}
                >
                  刷新
                </button>
              </div>
            </div>
          ) : null}

          {nonScreenshotArtifacts.length > 0 ? (
            <div className="browser-agent__artifacts">
              <div className="browser-agent__artifacts-head">已落地的数据产物</div>
              <ul>
                {nonScreenshotArtifacts.map((art) => (
                  <li key={art.id}>
                    <a
                      href={browserAgentApi.artifactUrl(art.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {art.kind} · {(art.metadata?.label as string) || art.file_path.split('/').pop()}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <ol className="browser-agent__steps">
          {steps.map((step) => (
            <StepRow
              key={step.id}
              step={step}
              isFocused={focusedStepIndex === step.step_index}
              onFocus={focusStep}
            />
          ))}
        </ol>
      </div>
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
            让 AI 在隔离的浏览器里替你完成网页任务（M2 起由 LLM 决策每一步）。
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
                placeholder="例如：在 GitHub 搜索 browser-use 提取 README 重点"
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
