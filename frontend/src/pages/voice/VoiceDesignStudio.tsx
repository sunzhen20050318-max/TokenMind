import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../services/api';
import {
  selectTasksByKind,
  useCreativeTasksStore,
} from '../../stores/creativeTasksStore';
import type { CreativeCapabilitySettings } from '../../types/config';
import { isCreativeCapabilityConfigured } from '../../types/config';
import type { VoiceCloneRecord } from '../../types';
import {
  daysUntilExpiry,
  expiryLabel,
} from './voiceClonePageState';
import {
  DESIGN_PREVIEW_MAX,
  DESIGN_PROMPT_MAX,
  DESIGN_PROMPT_MIN,
  DESIGN_PROMPT_TEMPLATES,
  validateVoiceDesignForm,
} from './voiceDesignPageState';
import type { VoiceDesignFormInput } from './voiceDesignPageState';
import './voiceClone.css';

interface VoiceDesignPageProps {
  capability: CreativeCapabilitySettings | null | undefined;
}

type SubmitPhase = 'idle' | 'running' | 'success' | 'error';

const EMPTY_FORM: VoiceDesignFormInput = {
  prompt: '',
  previewText: '',
  displayName: '',
};

function formatRelative(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function persistSplit(fraction: number): void {
  try {
    window.localStorage.setItem('tokenmind:voice-design-split', fraction.toFixed(3));
  } catch {
    // ignore
  }
}

function loadSplit(): number {
  try {
    const raw = window.localStorage.getItem('tokenmind:voice-design-split');
    const parsed = raw ? Number.parseFloat(raw) : NaN;
    if (Number.isFinite(parsed) && parsed >= 0.3 && parsed <= 0.8) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return 0.56;
}

export function VoiceDesignPage({ capability }: VoiceDesignPageProps) {
  const [form, setForm] = useState<VoiceDesignFormInput>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const voiceDesignTasks = useCreativeTasksStore(selectTasksByKind('voice-design'));
  const startVoiceDesign = useCreativeTasksStore((s) => s.startVoiceDesign);
  const removeTask = useCreativeTasksStore((s) => s.removeTask);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const activeTask = activeTaskId
    ? voiceDesignTasks.find((task) => task.id === activeTaskId) ?? null
    : null;
  const submit: SubmitPhase = (() => {
    if (!activeTask) return 'idle';
    if (activeTask.status === 'running') return 'running';
    if (activeTask.status === 'success') return 'success';
    return 'error';
  })();
  const [records, setRecords] = useState<VoiceCloneRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState<boolean>(true);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null);
  const [leftFraction, setLeftFraction] = useState<number>(loadSplit);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const configured = isCreativeCapabilityConfigured(capability);
  const enabled = Boolean(capability?.enabled);
  const ready = configured && enabled;
  const capabilityNotice = !configured
    ? '还没有配置音色设计模型。请先到设置中心的声音工程里填入 API Key 并启用音色设计。'
    : !enabled
      ? '音色设计模型已经配置完成，但当前还没有启用。请到设置中心启用音色设计能力。'
      : null;

  const refreshRecords = useCallback(async () => {
    setRecordsLoading(true);
    setRecordsError(null);
    try {
      const items = await api.listVoiceClones({ source: 'design' });
      setRecords(items);
      setSelectedVoiceId((current) => {
        if (current && items.some((item) => item.voice_id === current)) {
          return current;
        }
        return items[0]?.voice_id ?? null;
      });
    } catch (err) {
      setRecordsError(err instanceof Error ? err.message : '无法加载音色列表');
    } finally {
      setRecordsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshRecords();
  }, [refreshRecords]);

  useEffect(() => {
    persistSplit(leftFraction);
  }, [leftFraction]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (event: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (rect.width <= 0) return;
      const raw = (event.clientX - rect.left) / rect.width;
      setLeftFraction(Math.min(0.78, Math.max(0.32, raw)));
    };
    const handleUp = () => setIsDragging(false);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [isDragging]);

  const updateForm = useCallback(
    <K extends keyof VoiceDesignFormInput>(key: K, value: VoiceDesignFormInput[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const applyTemplate = useCallback(
    (templateId: string) => {
      const template = DESIGN_PROMPT_TEMPLATES.find((item) => item.id === templateId);
      if (!template) return;
      setForm((prev) => ({
        ...prev,
        prompt: template.prompt,
        previewText: prev.previewText.trim() ? prev.previewText : template.preview,
        displayName: prev.displayName.trim() ? prev.displayName : template.label,
      }));
    },
    [],
  );

  const validationErrors = useMemo(() => validateVoiceDesignForm(form), [form]);
  const canSubmit = ready && submit !== 'running' && validationErrors.length === 0;

  const handleSubmit = useCallback(() => {
    if (!ready) return;
    const errors = validateVoiceDesignForm(form);
    if (errors.length > 0) {
      setError(errors[0].message);
      return;
    }
    setError(null);
    const taskId = startVoiceDesign(
      {
        prompt: form.prompt.trim(),
        preview_text: form.previewText.trim(),
        display_name: form.displayName.trim() || null,
      },
      form.displayName.trim() || form.prompt.trim().slice(0, 24) || '设计音色',
    );
    setActiveTaskId(taskId);
  }, [form, ready, startVoiceDesign]);

  // Drain finished voice-design tasks: success → select voice + refresh records.
  useEffect(() => {
    if (!activeTask) return;
    if (activeTask.status === 'success' && activeTask.response) {
      setSelectedVoiceId(activeTask.response.voice_id);
      void refreshRecords();
      const taskId = activeTask.id;
      const timer = window.setTimeout(() => {
        removeTask(taskId);
        setActiveTaskId((curr) => (curr === taskId ? null : curr));
      }, 1500);
      return () => window.clearTimeout(timer);
    }
    if (activeTask.status === 'error') {
      setError(activeTask.error || '音色生成失败，请稍后重试。');
    }
  }, [activeTask, refreshRecords, removeTask]);

  const handleDelete = useCallback(
    async (voiceId: string) => {
      if (!window.confirm('删除后本地记录和试听音频将一并清除，确定继续？')) return;
      setBusyVoiceId(voiceId);
      try {
        await api.deleteVoiceClone(voiceId);
        if (selectedVoiceId === voiceId) {
          setSelectedVoiceId(null);
        }
        await refreshRecords();
      } catch (err) {
        setRecordsError(err instanceof Error ? err.message : '删除失败');
      } finally {
        setBusyVoiceId(null);
      }
    },
    [refreshRecords, selectedVoiceId],
  );

  const handleKeepAlive = useCallback(
    async (voiceId: string) => {
      setBusyVoiceId(voiceId);
      try {
        await api.keepAliveVoiceClone(voiceId);
        await refreshRecords();
      } catch (err) {
        setRecordsError(err instanceof Error ? err.message : '保活失败');
      } finally {
        setBusyVoiceId(null);
      }
    },
    [refreshRecords],
  );

  const selectedRecord = useMemo(
    () => records.find((record) => record.voice_id === selectedVoiceId) ?? null,
    [records, selectedVoiceId],
  );

  const selectedAudioUrl = useMemo(() => {
    if (!selectedRecord) return null;
    if (selectedRecord.demo_attachment_id) {
      return api.getVoiceCloneDemoUrl(selectedRecord.demo_attachment_id);
    }
    return selectedRecord.demo_audio_url ?? null;
  }, [selectedRecord]);

  const submitLabel = submit === 'running' ? '生成中…' : '生成音色';

  return (
    <section
      ref={containerRef}
      className={`voice-maker ${isDragging ? 'is-dragging' : ''}`}
      style={{ gridTemplateColumns: `${leftFraction * 100}% 8px 1fr` }}
    >
      <div className="voice-maker__left">
        <header className="voice-maker__topbar">
          <h1>音色设计</h1>
          <p>用文字描述生成全新音色，不需要上传参考音频</p>
        </header>

        {capabilityNotice ? <div className="voice-maker__notice">{capabilityNotice}</div> : null}

        <div className="voice-maker__form">
          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>选一个模板快速开始</strong>
            </div>
            <div className="voice-maker__chips">
              {DESIGN_PROMPT_TEMPLATES.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className="voice-maker__chip"
                  onClick={() => applyTemplate(template.id)}
                >
                  <span>{template.label}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>音色描述</strong>
              <span className="voice-maker__field-foot">
                {form.prompt.length} / {DESIGN_PROMPT_MAX}
              </span>
            </div>
            <textarea
              className="voice-maker__textarea"
              rows={4}
              maxLength={DESIGN_PROMPT_MAX}
              value={form.prompt}
              onChange={(event) => updateForm('prompt', event.target.value)}
              placeholder={`描述你想要的音色风格，至少 ${DESIGN_PROMPT_MIN} 个字符。包含性别、年龄、语气、节奏、情绪会更准确。`}
            />
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>试听文本</strong>
              <span className="voice-maker__field-foot">
                {form.previewText.length} / {DESIGN_PREVIEW_MAX}
              </span>
            </div>
            <textarea
              className="voice-maker__textarea"
              rows={3}
              maxLength={DESIGN_PREVIEW_MAX}
              value={form.previewText}
              onChange={(event) => updateForm('previewText', event.target.value)}
              placeholder="生成完成后会用这段文字合成一段试听音频"
            />
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>保存名称（可选）</strong>
            </div>
            <input
              type="text"
              className="voice-maker__textarea"
              value={form.displayName}
              onChange={(event) => updateForm('displayName', event.target.value)}
              placeholder="给这个音色起个名字，方便在语音合成里识别"
              maxLength={64}
            />
          </section>

          {error ? <div className="voice-maker__error">{error}</div> : null}

          <div className="voice-maker__submit-row">
            <div className="voice-maker__submit-hint">
              生成走 MiniMax 按量付费；生成完成后可直接在语音合成里选用
            </div>
            <button
              type="button"
              className="voice-maker__submit"
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
            >
              {submitLabel}
            </button>
          </div>
        </div>
      </div>

      <div
        className={`voice-maker__divider ${isDragging ? 'is-dragging' : ''}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="拖动调整左右栏宽度"
        onMouseDown={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDoubleClick={() => setLeftFraction(0.56)}
      >
        <span className="voice-maker__divider-handle" />
      </div>

      <aside className="voice-maker__right">
        <header className="voice-maker__list-head">
          <h2>设计的音色</h2>
          <span className="voice-maker__list-count">
            {records.length} · MiniMax 7 天未使用会自动清理
          </span>
        </header>

        {recordsError ? <div className="voice-maker__warning">{recordsError}</div> : null}

        {recordsLoading && records.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">正在加载…</div>
          </div>
        ) : records.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">还没有设计过音色</div>
            <p>在左侧用一段文字描述你想要的声音，生成后会展示在这里。</p>
          </div>
        ) : (
          <div className="voice-maker__list">
            {records.map((item) => {
              const active = item.voice_id === selectedVoiceId;
              const remaining = daysUntilExpiry(item);
              const warn = remaining <= 2;
              const label = item.display_name?.trim() || '未命名音色';
              return (
                <button
                  key={item.voice_id}
                  type="button"
                  className={`voice-maker__item ${active ? 'is-active' : ''}`}
                  onClick={() => setSelectedVoiceId(item.voice_id)}
                >
                  <div className="voice-maker__item-head">
                    <code>{label}</code>
                    <span className={warn ? 'voice-maker__item-expiry is-warn' : 'voice-maker__item-expiry'}>
                      {expiryLabel(item)}
                    </span>
                  </div>
                  <div className="voice-maker__item-meta">
                    <span>{item.model}</span>
                    <span>· {formatRelative(item.created_at)}</span>
                  </div>
                  {item.notes ? (
                    <div className="voice-maker__tts-preview" title={item.notes}>
                      {item.notes}
                    </div>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}

        {selectedRecord ? (
          <div className="voice-maker__detail">
            <div className="voice-maker__detail-head">
              <code>{selectedRecord.display_name?.trim() || '未命名音色'}</code>
              <span>{selectedRecord.model}</span>
            </div>
            <div className="voice-maker__detail-meta">
              <span>创建 {formatRelative(selectedRecord.created_at)}</span>
              {selectedRecord.last_kept_alive_at ? (
                <span>· 上次保活 {formatRelative(selectedRecord.last_kept_alive_at)}</span>
              ) : null}
              <span>· {expiryLabel(selectedRecord)}</span>
            </div>
            {selectedRecord.notes ? (
              <p className="voice-maker__detail-text">描述：{selectedRecord.notes}</p>
            ) : null}
            {selectedRecord.preview_text ? (
              <p className="voice-maker__detail-text">试听：{selectedRecord.preview_text}</p>
            ) : null}
            {selectedAudioUrl ? (
              <audio
                controls
                src={selectedAudioUrl}
                className="voice-maker__detail-audio"
              />
            ) : (
              <div className="voice-maker__detail-empty">本次设计未生成试听音频</div>
            )}
            <div className="voice-maker__detail-actions">
              <button
                type="button"
                className="voice-maker__ghost-btn"
                onClick={() => void handleKeepAlive(selectedRecord.voice_id)}
                disabled={busyVoiceId === selectedRecord.voice_id}
              >
                {busyVoiceId === selectedRecord.voice_id ? '处理中…' : '立即保活'}
              </button>
              <button
                type="button"
                className="voice-maker__ghost-btn is-danger"
                onClick={() => void handleDelete(selectedRecord.voice_id)}
                disabled={busyVoiceId === selectedRecord.voice_id}
              >
                删除
              </button>
            </div>
          </div>
        ) : null}
      </aside>
    </section>
  );
}
