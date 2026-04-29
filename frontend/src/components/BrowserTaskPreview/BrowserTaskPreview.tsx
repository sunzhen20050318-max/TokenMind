import { useEffect, useMemo, useRef, useState } from 'react';
import { browserAgentApi } from '../../services/browserAgent';
import { FINAL_STATUSES, useBrowserAgentStore } from '../../stores/browserAgentStore';
import type { BrowserArtifact, BrowserStep, BrowserTaskStatus } from '../../types/browserAgent';
import './browserTaskPreview.css';

const STATUS_LABELS: Record<BrowserTaskStatus, string> = {
  pending: '准备中',
  running: '执行中',
  awaiting_user: '等待接管',
  completed: '已完成',
  failed: '失败',
  cancelled: '已结束',
};

const PHASE_LABELS: Record<BrowserStep['phase'], string> = {
  thinking: 'thinking',
  action: 'action',
  observation: 'observation',
  intervention: 'handoff',
};

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

function artifactLabel(artifact: BrowserArtifact): string {
  const file = basename(artifact.file_path);
  return `${artifact.kind}${file ? ` · ${file}` : ''}`;
}

function formatArgs(args?: Record<string, unknown> | null): string {
  if (!args || Object.keys(args).length === 0) {
    return '';
  }
  try {
    return JSON.stringify(args);
  } catch {
    return String(args);
  }
}

function StepCard({ step }: { step: BrowserStep }) {
  const args = formatArgs(step.action_args);

  return (
    <article className={`browser-task-preview__step is-${step.phase} ${step.success ? '' : 'is-error'}`}>
      <div className="browser-task-preview__step-head">
        <span className="browser-task-preview__step-index">{String(step.step_index).padStart(2, '0')}</span>
        <span className="browser-task-preview__phase">{PHASE_LABELS[step.phase]}</span>
        {step.duration_ms != null ? (
          <span className="browser-task-preview__duration">{Math.round(step.duration_ms)}ms</span>
        ) : null}
      </div>

      {step.thinking ? <p className="browser-task-preview__thinking">{step.thinking}</p> : null}
      {step.action_name ? (
        <div className="browser-task-preview__action">
          <strong>{step.action_name}</strong>
          {args ? <code>{args}</code> : null}
        </div>
      ) : null}
      {step.observation ? <p className="browser-task-preview__observation">{step.observation}</p> : null}
      {step.error ? <p className="browser-task-preview__error">{step.error}</p> : null}
    </article>
  );
}

export function BrowserTaskPreview() {
  const previewOpen = useBrowserAgentStore((state) => state.previewOpen);
  const selectedTaskId = useBrowserAgentStore((state) => state.selectedTaskId);
  const detail = useBrowserAgentStore((state) => state.detail);
  const detailLoading = useBrowserAgentStore((state) => state.detailLoading);
  const detailError = useBrowserAgentStore((state) => state.detailError);
  const closePreview = useBrowserAgentStore((state) => state.closePreview);
  const refreshDetail = useBrowserAgentStore((state) => state.refreshDetail);
  const cancelTask = useBrowserAgentStore((state) => state.cancelTask);
  const takeoverTask = useBrowserAgentStore((state) => state.takeoverTask);
  const resumeTask = useBrowserAgentStore((state) => state.resumeTask);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const [resumeDialogOpen, setResumeDialogOpen] = useState(false);
  const [resumeNote, setResumeNote] = useState('');
  const [resumeSubmitting, setResumeSubmitting] = useState(false);

  const steps = useMemo(
    () => [...(detail?.steps || [])].sort((left, right) => left.step_index - right.step_index),
    [detail?.steps],
  );
  const artifacts = useMemo(
    () => [...(detail?.artifacts || [])].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)),
    [detail?.artifacts],
  );
  const task = detail?.task;
  const status = task?.status ?? 'pending';
  const canTakeover = task && (task.status === 'running' || task.status === 'pending');
  const canResume = task?.status === 'awaiting_user';
  const canCancel = task && !FINAL_STATUSES.has(task.status);

  async function submitResume(note?: string) {
    if (!task || task.status !== 'awaiting_user' || resumeSubmitting) {
      return;
    }
    setResumeSubmitting(true);
    try {
      await resumeTask(task.id, note);
      setResumeDialogOpen(false);
      setResumeNote('');
    } finally {
      setResumeSubmitting(false);
    }
  }

  useEffect(() => {
    if (!previewOpen) {
      return;
    }
    const node = timelineRef.current;
    if (!node) {
      return;
    }
    node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' });
  }, [previewOpen, steps.length, status, detail?.task.result_summary, detail?.task.error_detail]);

  useEffect(() => {
    if (!canResume) {
      setResumeDialogOpen(false);
      setResumeNote('');
    }
  }, [canResume]);

  if (!previewOpen) {
    return null;
  }

  return (
    <div className="browser-task-preview" aria-live="polite">
      <aside className="browser-task-preview__drawer" aria-label="浏览器执行过程">
        <header className="browser-task-preview__header">
          <div>
            <span className="browser-task-preview__kicker">WebAgent</span>
            <h2>浏览器执行</h2>
          </div>
          <button type="button" className="browser-task-preview__close" onClick={closePreview} aria-label="关闭">
            ×
          </button>
        </header>

        <section className="browser-task-preview__summary">
          <div>
            <span className={`browser-task-preview__status is-${status}`}>{STATUS_LABELS[status]}</span>
            <strong>{task?.instruction || 'AI 正在准备浏览器任务'}</strong>
          </div>
          <small>{selectedTaskId || '等待任务 ID'}</small>
        </section>

        <div className="browser-task-preview__actions">
          <button type="button" onClick={() => void refreshDetail()} disabled={!selectedTaskId}>
            刷新
          </button>
          {canTakeover ? (
            <button type="button" onClick={() => void takeoverTask(task.id, '用户从聊天侧边窗口接管')}>
              接管浏览器
            </button>
          ) : null}
          {canResume ? (
            <button type="button" className="is-primary" onClick={() => setResumeDialogOpen(true)}>
              我已完成
            </button>
          ) : null}
          {canCancel ? (
            <button type="button" className="is-danger" onClick={() => void cancelTask(task.id)}>
              结束任务
            </button>
          ) : null}
        </div>

        {resumeDialogOpen && canResume ? (
          <section className="browser-task-preview__resume-dialog" role="dialog" aria-label="恢复浏览器任务">
            <div>
              <strong>告诉 AI 你刚刚做了什么</strong>
              <p>比如：我完成了登录、关闭了弹窗、通过了验证码。这个说明会同步给浏览器 AI，帮助它继续下一步。</p>
            </div>
            <textarea
              value={resumeNote}
              onChange={(event) => setResumeNote(event.target.value)}
              placeholder="可选：我已经完成登录，现在页面停在搜索结果..."
              rows={3}
            />
            <div className="browser-task-preview__resume-actions">
              <button
                type="button"
                onClick={() => void submitResume('')}
                disabled={resumeSubmitting}
              >
                跳过说明
              </button>
              <button
                type="button"
                className="is-primary"
                onClick={() => void submitResume(resumeNote)}
                disabled={resumeSubmitting}
              >
                {resumeSubmitting ? '恢复中...' : '继续执行'}
              </button>
            </div>
          </section>
        ) : null}

        <div className="browser-task-preview__body" ref={timelineRef}>
          {detailLoading ? <div className="browser-task-preview__empty">正在连接浏览器任务...</div> : null}
          {detailError ? <div className="browser-task-preview__notice is-error">{detailError}</div> : null}

          {steps.length === 0 && !detailLoading ? (
            <div className="browser-task-preview__empty">
              <span className="browser-task-preview__pulse" />
              <strong>等待第一步执行</strong>
              <p>AI 调用浏览器后，thinking、action 和 observation 会在这里自动滚动显示。</p>
            </div>
          ) : (
            steps.map((step) => <StepCard key={step.id || step.step_index} step={step} />)
          )}

          {task?.result_summary ? (
            <section className="browser-task-preview__result">
              <span>结果</span>
              <p>{task.result_summary}</p>
            </section>
          ) : null}
          {task?.error_detail ? (
            <section className="browser-task-preview__notice is-error">
              <span>错误</span>
              <p>{task.error_detail}</p>
            </section>
          ) : null}
        </div>

        {artifacts.length > 0 ? (
          <footer className="browser-task-preview__artifacts">
            <span>保存的文件</span>
            <div>
              {artifacts.slice(0, 5).map((artifact) => (
                <a key={artifact.id} href={browserAgentApi.artifactUrl(artifact.id)} target="_blank" rel="noreferrer">
                  {artifactLabel(artifact)}
                </a>
              ))}
            </div>
          </footer>
        ) : null}
      </aside>
    </div>
  );
}
