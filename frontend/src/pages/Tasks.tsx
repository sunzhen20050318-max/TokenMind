import React, { useEffect, useMemo, useState } from 'react';
import { BrandMark } from '../components/BrandMark';
import { CloseIcon } from '../components/CloseIcon';
import { api } from '../services/api';
import { ListSkeleton } from '../components/Skeleton/Skeleton';
import type { Session } from '../types';
import type { CreateCronJobPayload, CronJob, CronStatus } from '../types/cron';
import { useChatStore } from '../stores/chatStore';
import './tasks.css';

type ScheduleKind = 'every' | 'cron' | 'at';
type FixedCronPreset = 'daily' | 'weekdays' | 'weekly' | 'custom';
type TasksSection = 'overview' | 'jobs' | 'create' | 'delivery';

interface NoticeState {
  tone: 'success' | 'error';
  text: string;
}

interface TasksModalProps {
  onClose: () => void;
  currentSessionId: string | null;
  currentSessionLabel?: string;
  sessions: Session[];
}

const TASK_RESULTS_SESSION_ID = 'web:task-results';
const TASK_RESULTS_SESSION_TITLE = '任务结果';
const TASK_SECTION_META: Array<{
  id: TasksSection;
  title: string;
  copy: string;
}> = [
  { id: 'overview', title: '概览', copy: '查看自动化当前的运行状态、总量和下一次执行。' },
  { id: 'jobs', title: '任务列表', copy: '统一查看、启停、立即执行和删除已有任务。' },
  { id: 'create', title: '新建任务', copy: '把重复动作整理成稳定的自动化任务。' },
  { id: 'delivery', title: '结果投递', copy: '决定任务执行后把结果发到哪个会话。' },
];

const WEEKDAY_OPTIONS = [
  { value: '1', label: '周一' },
  { value: '2', label: '周二' },
  { value: '3', label: '周三' },
  { value: '4', label: '周四' },
  { value: '5', label: '周五' },
  { value: '6', label: '周六' },
  { value: '0', label: '周日' },
];

function formatTimestamp(timestamp: number | null | undefined): string {
  if (!timestamp) {
    return '--';
  }

  return new Date(timestamp).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatSessionLabel(session: Session): string {
  return session.title || session.first_message || session.session_id;
}

function defaultAtValue(): string {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
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

export const TasksModal: React.FC<TasksModalProps> = ({
  onClose,
  sessions,
}) => {
  const { loadSessions } = useChatStore();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [status, setStatus] = useState<CronStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>('every');
  const [fixedCronPreset, setFixedCronPreset] = useState<FixedCronPreset>('weekdays');
  const [name, setName] = useState('早间提醒');
  const [message, setMessage] = useState('请提醒我查看今天的重要事项，并整理成一段简短总结。');
  const [everySeconds, setEverySeconds] = useState(3600);
  const [cronExpr, setCronExpr] = useState('0 9 * * 1-5');
  const [fixedTime, setFixedTime] = useState('09:00');
  const [weeklyDay, setWeeklyDay] = useState('1');
  const [timezone, setTimezone] = useState('Asia/Shanghai');
  const [atValue, setAtValue] = useState(defaultAtValue());
  const [selectedTargetSessionId, setSelectedTargetSessionId] = useState(TASK_RESULTS_SESSION_ID);
  const [selectedSection, setSelectedSection] = useState<TasksSection>('overview');

  const availableTargetSessions = useMemo(
    () =>
      sessions.filter((session) => {
        if (session.session_id === TASK_RESULTS_SESSION_ID) {
          return false;
        }
        if (session.message_count > 0) {
          return true;
        }
        if (session.title?.trim() || session.first_message?.trim()) {
          return true;
        }
        return false;
      }),
    [sessions]
  );

  const sessionOptions = useMemo(
    () =>
      availableTargetSessions.map((session) => ({
        id: session.session_id,
        label: formatSessionLabel(session),
      })),
    [availableTargetSessions]
  );

  const sessionLabelMap = useMemo<Record<string, string>>(
    () =>
      ({
        [TASK_RESULTS_SESSION_ID]: TASK_RESULTS_SESSION_TITLE,
        ...Object.fromEntries(sessionOptions.map((session) => [session.id, session.label])),
      }),
    [sessionOptions]
  );

  const activeJobs = useMemo(() => jobs.filter((job) => job.enabled), [jobs]);
  const nextJob = useMemo(
    () =>
      [...jobs]
        .filter((job) => job.enabled && job.state.next_run_at_ms)
        .sort((a, b) => (a.state.next_run_at_ms || 0) - (b.state.next_run_at_ms || 0))[0],
    [jobs]
  );

  const generatedCronExpr = useMemo(
    () => buildCronExpression(fixedCronPreset, fixedTime, cronExpr, weeklyDay),
    [fixedCronPreset, fixedTime, cronExpr, weeklyDay]
  );

  const cronPreview = useMemo(
    () => buildCronPreview(fixedCronPreset, fixedTime, timezone, weeklyDay),
    [fixedCronPreset, fixedTime, timezone, weeklyDay]
  );

  const currentSectionMeta =
    TASK_SECTION_META.find((section) => section.id === selectedSection) || TASK_SECTION_META[0];

  const navigateTo = (section: TasksSection) => {
    setSelectedSection(section);
    window.requestAnimationFrame(() => {
      document
        .getElementById(`tasks-section-${section}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const loadData = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const [jobsData, statusData] = await Promise.all([
        api.listCronJobs(true),
        api.getCronStatus(),
      ]);
      setJobs(jobsData);
      setStatus(statusData);
    } catch (error) {
      if (!silent) {
        setNotice({
          tone: 'error',
          text: error instanceof Error ? error.message : '加载定时任务失败',
        });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleCreate = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const payload: CreateCronJobPayload = {
        name: name.trim(),
        message: message.trim(),
        schedule_kind: scheduleKind,
        deliver: Boolean(selectedTargetSessionId),
        session_id: selectedTargetSessionId || null,
      };

      if (scheduleKind === 'every') {
        payload.every_seconds = everySeconds;
      } else if (scheduleKind === 'cron') {
        payload.cron_expr = generatedCronExpr;
        payload.tz = timezone.trim();
      } else {
        payload.at = atValue ? `${atValue}:00` : '';
      }

      await api.createCronJob(payload);
      await loadSessions();
      setNotice({ tone: 'success', text: '任务已创建' });
      await loadData(true);
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '创建任务失败',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (job: CronJob) => {
    setActioningId(job.id);
    setNotice(null);
    try {
      const updated = await api.toggleCronJob(job.id, !job.enabled);
      setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '更新任务状态失败',
      });
    } finally {
      setActioningId(null);
      await loadData(true);
    }
  };

  const handleRunNow = async (jobId: string) => {
    setActioningId(jobId);
    setNotice(null);
    try {
      await api.runCronJob(jobId);
      setNotice({ tone: 'success', text: '任务已立即触发' });
      await loadData(true);
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '执行任务失败',
      });
    } finally {
      setActioningId(null);
    }
  };

  const handleDelete = async (jobId: string) => {
    setActioningId(jobId);
    setNotice(null);
    try {
      await api.deleteCronJob(jobId);
      setJobs((current) => current.filter((job) => job.id !== jobId));
      setNotice({ tone: 'success', text: '任务已删除' });
      await loadData(true);
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '删除任务失败',
      });
    } finally {
      setActioningId(null);
    }
  };

  return (
    <div
      className="tasks-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="tasks-modal" onClick={(event) => event.stopPropagation()}>
        <aside className="tasks-sidebar">
          <div className="tasks-profile-card">
            <div className="tasks-profile-card__avatar">
              <BrandMark size={18} alt="TokenMind 标志" variant="icon" />
            </div>
            <div className="tasks-profile-card__body">
              <div className="tasks-profile-card__name">TokenMind</div>
              <div className="tasks-profile-card__role">定时任务</div>
            </div>
            <div className="tasks-profile-card__chevron" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M5.5 3.5 10 8l-4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div className="tasks-sidebar-divider" />

          <div className="tasks-sidebar-group-label">任务视图</div>

          <nav className="tasks-nav">
            {TASK_SECTION_META.map((section) => (
              <button
                key={section.id}
                className={`tasks-nav-button ${selectedSection === section.id ? 'is-active' : ''}`}
                onClick={() => navigateTo(section.id)}
                type="button"
              >
                <span className="tasks-nav-title">{section.title}</span>
                <span className="tasks-nav-copy">{section.copy}</span>
              </button>
            ))}
          </nav>

          <button className="tasks-sidebar-help" type="button">
            <span>了解自动化建议</span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M6 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10.5 5.5 4.5 11.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </aside>

        <section className="tasks-main">
          <header className="tasks-header">
            <h2>{currentSectionMeta.title}</h2>
            <button aria-label="关闭定时任务" className="tasks-close" onClick={onClose} type="button">
              <CloseIcon />
            </button>
          </header>

          <div className="tasks-content">
          {notice ? <div className={`tasks-notice ${notice.tone}`}>{notice.text}</div> : null}

          <section className="tasks-metrics" id="tasks-section-overview">
            <div className="tasks-metric-card">
              <div className="tasks-metric-label">运行状态</div>
              <div className="tasks-metric-value">{status?.enabled ? '运行中' : '未启动'}</div>
            </div>
            <div className="tasks-metric-card">
              <div className="tasks-metric-label">已启用任务</div>
              <div className="tasks-metric-value">{activeJobs.length} 个</div>
            </div>
            <div className="tasks-metric-card">
              <div className="tasks-metric-label">下一次执行</div>
              <div className="tasks-metric-value">
                {nextJob ? formatTimestamp(nextJob.state.next_run_at_ms) : '--'}
              </div>
            </div>
          </section>

          <div className="tasks-layout">
            <section className="tasks-panel" id="tasks-section-jobs">
              <div className="tasks-panel-head">
                <div>
                  <h3>现有任务</h3>
                  <p>查看任务状态、立即执行，或暂停和删除已有任务。</p>
                </div>
                <button className="tasks-secondary" onClick={() => void loadData()} type="button">
                  刷新
                </button>
              </div>

              {loading ? (
                <div className="tasks-empty">
                  <ListSkeleton count={5} />
                </div>
              ) : jobs.length === 0 ? (
                <div className="tasks-empty">还没有自动化任务。先在右侧创建一个试试看。</div>
              ) : (
                <div className="tasks-job-list">
                  {jobs.map((job) => (
                    <div className="tasks-job-card" key={job.id}>
                      <div className="tasks-job-top">
                        <div>
                          <div className="tasks-job-name">{job.name}</div>
                          <div className="tasks-job-meta">
                            <span className={`tasks-badge ${job.enabled ? 'active' : ''}`}>
                              {job.enabled ? '已启用' : '已暂停'}
                            </span>
                            <span className="tasks-badge">{job.schedule.label}</span>
                            {job.deliver ? (
                              <span className="tasks-badge">
                                发送到：{sessionLabelMap[job.to || ''] || job.to}
                              </span>
                            ) : (
                              <span className="tasks-badge">仅执行不发送</span>
                            )}
                          </div>
                        </div>
                        <div className="tasks-job-id">#{job.id}</div>
                      </div>

                      <div className="tasks-job-message">{job.message}</div>

                      <div className="tasks-job-status">
                        <span>下次执行：{formatTimestamp(job.state.next_run_at_ms)}</span>
                        <span>最近执行：{formatTimestamp(job.state.last_run_at_ms)}</span>
                        <span>最近状态：{job.state.last_status || '--'}</span>
                      </div>

                      {job.state.last_error ? (
                        <div className="tasks-job-error">{job.state.last_error}</div>
                      ) : null}

                      <div className="tasks-actions">
                        <button
                          className="tasks-primary"
                          disabled={actioningId === job.id}
                          onClick={() => void handleRunNow(job.id)}
                          type="button"
                        >
                          立即执行
                        </button>
                        <button
                          className="tasks-secondary"
                          disabled={actioningId === job.id}
                          onClick={() => void handleToggle(job)}
                          type="button"
                        >
                          {job.enabled ? '暂停任务' : '启用任务'}
                        </button>
                        <button
                          className="tasks-danger"
                          disabled={actioningId === job.id}
                          onClick={() => void handleDelete(job.id)}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="tasks-panel" id="tasks-section-create">
              <div className="tasks-panel-head">
                <div>
                  <h3>创建任务</h3>
                  <p>把重复动作变成自动化，让 agent 按计划主动执行。</p>
                </div>
              </div>

              <div className="tasks-form">
                <label className="tasks-field">
                  <span>任务名称</span>
                  <input
                    className="tasks-input"
                    onChange={(event) => setName(event.target.value)}
                    type="text"
                    value={name}
                  />
                </label>

                <label className="tasks-field">
                  <span>执行内容</span>
                  <textarea
                    className="tasks-textarea"
                    onChange={(event) => setMessage(event.target.value)}
                    value={message}
                  />
                </label>

                <div className="tasks-field">
                  <span>计划类型</span>
                  <div className="tasks-kind-row">
                    {[
                      ['every', '间隔执行'],
                      ['cron', '固定时间'],
                      ['at', '单次执行'],
                    ].map(([kind, label]) => (
                      <button
                        key={kind}
                        className={`tasks-kind-button ${scheduleKind === kind ? 'active' : ''}`}
                        onClick={() => setScheduleKind(kind as ScheduleKind)}
                        type="button"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {scheduleKind === 'every' ? (
                  <label className="tasks-field">
                    <span>间隔秒数</span>
                    <input
                      className="tasks-input"
                      min={1}
                      onChange={(event) => setEverySeconds(Number(event.target.value) || 1)}
                      type="number"
                      value={everySeconds}
                    />
                  </label>
                ) : null}

                {scheduleKind === 'cron' ? (
                  <>
                    <div className="tasks-field">
                      <span>重复规则</span>
                      <div className="tasks-kind-row">
                        {[
                          ['daily', '每天'],
                          ['weekdays', '工作日'],
                          ['weekly', '每周'],
                          ['custom', '高级 Cron'],
                        ].map(([preset, label]) => (
                          <button
                            key={preset}
                            className={`tasks-kind-button ${
                              fixedCronPreset === preset ? 'active' : ''
                            }`}
                            onClick={() => setFixedCronPreset(preset as FixedCronPreset)}
                            type="button"
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {fixedCronPreset === 'weekly' ? (
                      <label className="tasks-field">
                        <span>每周哪一天</span>
                        <select
                          className="tasks-input"
                          onChange={(event) => setWeeklyDay(event.target.value)}
                          value={weeklyDay}
                        >
                          {WEEKDAY_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}

                    {fixedCronPreset === 'custom' ? (
                      <label className="tasks-field">
                        <span>Cron 表达式</span>
                        <input
                          className="tasks-input"
                          onChange={(event) => setCronExpr(event.target.value)}
                          placeholder="0 9 * * 1-5"
                          type="text"
                          value={cronExpr}
                        />
                      </label>
                    ) : (
                      <label className="tasks-field">
                        <span>执行时间</span>
                        <input
                          className="tasks-input"
                          onChange={(event) => setFixedTime(event.target.value)}
                          type="time"
                          value={fixedTime}
                        />
                      </label>
                    )}

                    <label className="tasks-field">
                      <span>时区</span>
                      <input
                        className="tasks-input"
                        onChange={(event) => setTimezone(event.target.value)}
                        placeholder="Asia/Shanghai"
                        type="text"
                        value={timezone}
                      />
                    </label>

                    <div className="tasks-schedule-preview">
                      <strong>执行预览</strong>
                      <span>{cronPreview}</span>
                      <code>{generatedCronExpr || '--'}</code>
                    </div>
                  </>
                ) : null}

                {scheduleKind === 'at' ? (
                  <label className="tasks-field">
                    <span>执行时间</span>
                    <input
                      className="tasks-input"
                      onChange={(event) => setAtValue(event.target.value)}
                      type="datetime-local"
                      value={atValue}
                    />
                  </label>
                ) : null}

                <label className="tasks-field">
                  <span>目标会话</span>
                  <select
                    className="tasks-input"
                    onChange={(event) => setSelectedTargetSessionId(event.target.value)}
                    value={selectedTargetSessionId}
                  >
                    <option value={TASK_RESULTS_SESSION_ID}>任务结果会话（推荐）</option>
                    {sessionOptions.map((session) => (
                      <option key={session.id} value={session.id}>
                        {session.label}
                      </option>
                    ))}
                    <option value="">仅执行，不发送到聊天窗口</option>
                  </select>
                </label>

                <div className="tasks-deliver-box" id="tasks-section-delivery">
                  <div>
                    <strong>任务结果投递</strong>
                    <span>
                      {selectedTargetSessionId
                        ? `执行结果会发送到：${
                            sessionLabelMap[selectedTargetSessionId] || selectedTargetSessionId
                          }`
                        : '当前设为仅执行任务，不自动发送到聊天窗口。'}
                    </span>
                  </div>
                </div>

                <div className="tasks-actions">
                  <button
                    className="tasks-primary"
                    disabled={saving}
                    onClick={() => void handleCreate()}
                    type="button"
                  >
                    {saving ? '正在创建' : '创建任务'}
                  </button>
                </div>
              </div>
            </section>
          </div>
        </div>
        </section>
      </div>
    </div>
  );
};
