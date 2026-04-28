import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../services/api';
import {
  selectTasksByKind,
  useCreativeTasksStore,
} from '../../stores/creativeTasksStore';
import type { CreativeCapabilitySettings } from '../../types/config';
import { isCreativeCapabilityConfigured } from '../../types/config';
import {
  PREVIEW_LANGUAGES,
  PREVIEW_TEXT_LIMIT,
  SCENE_PROMPTS,
  VOICE_CLONE_INACTIVITY_DAYS,
  VOICE_CLONE_MAX_BYTES,
  VOICE_CLONE_MAX_SECONDS,
  VOICE_CLONE_MIN_SECONDS,
  daysUntilExpiry,
  expiryLabel,
  formatRecordingDuration,
  getScenePrompt,
  isMiniMaxCompatibleMime,
  isSupportedCloneAudio,
  makeRecordedFilename,
  pickRecordMimeType,
} from './voiceClonePageState';
import type { VoiceCloneRecord } from '../../types';
import '../creativePages.css';
import './voiceClone.css';

interface VoiceClonePageProps {
  capability: CreativeCapabilitySettings | null | undefined;
}

type RecordingPhase = 'idle' | 'requesting' | 'recording' | 'stopping';
type SubmitPhase = 'idle' | 'uploading' | 'cloning' | 'success' | 'error';
type AudioSource = 'record' | 'upload';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

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

export function VoiceClonePage({ capability }: VoiceClonePageProps) {
  const [sceneId, setSceneId] = useState<string>('random');
  const [language, setLanguage] = useState<string>(PREVIEW_LANGUAGES[0].value);
  const [previewText, setPreviewText] = useState<string>(PREVIEW_LANGUAGES[0].defaultText);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioSource, setAudioSource] = useState<AudioSource | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState<RecordingPhase>('idle');
  const [recordDuration, setRecordDuration] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Voice clone tasks live in the shared store so navigating away from the
  // studio does NOT lose the in-flight upload/clone state. The page tracks
  // which task it spawned so the UI reflects the same SubmitPhase as before.
  const voiceCloneTasks = useCreativeTasksStore(selectTasksByKind('voice-clone'));
  const startVoiceClone = useCreativeTasksStore((s) => s.startVoiceClone);
  const removeTask = useCreativeTasksStore((s) => s.removeTask);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const activeTask = activeTaskId
    ? voiceCloneTasks.find((task) => task.id === activeTaskId) ?? null
    : null;
  const submit: SubmitPhase = (() => {
    if (!activeTask) return 'idle';
    if (activeTask.status === 'running') return activeTask.phase === 'cloning' ? 'cloning' : 'uploading';
    if (activeTask.status === 'success') return 'success';
    return 'error';
  })();
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [history, setHistory] = useState<VoiceCloneRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<'keep-alive' | 'delete' | null>(null);
  const [leftFraction, setLeftFraction] = useState<number>(() => {
    try {
      const stored = window.localStorage.getItem('tokenmind:voice-clone-split');
      const parsed = stored ? Number.parseFloat(stored) : NaN;
      if (Number.isFinite(parsed) && parsed >= 0.3 && parsed <= 0.8) {
        return parsed;
      }
    } catch {
      // Ignore storage failures and fall back to default.
    }
    return 0.56;
  });
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const items = await api.listVoiceClones();
      setHistory(items);
      setSelectedVoiceId((current) => {
        if (current && items.some((item) => item.voice_id === current)) {
          return current;
        }
        return items[0]?.voice_id ?? null;
      });
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : '无法加载克隆列表');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMove = (event: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (rect.width <= 0) return;
      const raw = (event.clientX - rect.left) / rect.width;
      const clamped = Math.min(0.78, Math.max(0.32, raw));
      setLeftFraction(clamped);
    };

    const handleUp = () => {
      setIsDragging(false);
    };

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

  useEffect(() => {
    try {
      window.localStorage.setItem('tokenmind:voice-clone-split', leftFraction.toFixed(3));
    } catch {
      // Persistence is best-effort; ignore quota errors.
    }
  }, [leftFraction]);

  const configured = isCreativeCapabilityConfigured(capability);
  const enabled = Boolean(capability?.enabled);
  const ready = configured && enabled;
  const capabilityNotice = !configured
    ? '还没有配置声音克隆模型，请先到设置中心的声音工程里填入 API Key 并启用。'
    : !enabled
      ? '声音克隆模型已经配置完成，但当前还没有启用。请到设置中心启用声音克隆能力。'
      : null;

  const scene = getScenePrompt(sceneId);

  const fileWarning = useMemo(() => {
    if (!audioFile) return null;
    if (audioFile.size > VOICE_CLONE_MAX_BYTES) {
      return `音频文件超过上限（${formatBytes(VOICE_CLONE_MAX_BYTES)}）。`;
    }
    if (!isSupportedCloneAudio(audioFile) && !isMiniMaxCompatibleMime(audioFile.type)) {
      return '当前音频格式可能不被 MiniMax 支持，建议改用 MP3 / M4A / WAV。';
    }
    return null;
  }, [audioFile]);

  const canSubmit =
    ready && audioFile !== null && submit !== 'uploading' && submit !== 'cloning';

  const selectedRecord = useMemo(
    () => history.find((item) => item.voice_id === selectedVoiceId) ?? null,
    [history, selectedVoiceId],
  );

  const selectedAudioUrl = useMemo(() => {
    if (!selectedRecord) return null;
    if (selectedRecord.demo_attachment_id) {
      return api.getVoiceCloneDemoUrl(selectedRecord.demo_attachment_id);
    }
    return selectedRecord.demo_audio_url ?? null;
  }, [selectedRecord]);

  const changeAudio = useCallback(
    (nextFile: File | null, source: AudioSource | null) => {
      setAudioFile(nextFile);
      setAudioSource(source);
      setAudioUrl((previous) => {
        if (previous) {
          URL.revokeObjectURL(previous);
        }
        return nextFile ? URL.createObjectURL(nextFile) : null;
      });
    },
    [],
  );

  const clearAudio = useCallback(() => {
    changeAudio(null, null);
    setRecordDuration(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [changeAudio]);

  const startRecording = useCallback(async () => {
    if (!ready) return;
    setError(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError('当前浏览器不支持录音，请改用上传文件。');
      return;
    }
    try {
      setRecording('requesting');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickRecordMimeType();
      const options = mimeType ? { mimeType } : undefined;
      const recorder = new MediaRecorder(stream, options);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const type = recorder.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        const filename = makeRecordedFilename(type);
        const file = new File([blob], filename, { type });
        changeAudio(file, 'record');
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }
        setRecording('idle');
      };

      recorder.start();
      startedAtRef.current = Date.now();
      setRecordDuration(0);
      timerRef.current = window.setInterval(() => {
        const elapsed = (Date.now() - startedAtRef.current) / 1000;
        setRecordDuration(elapsed);
        if (elapsed >= VOICE_CLONE_MAX_SECONDS && recorderRef.current?.state === 'recording') {
          recorderRef.current.stop();
          if (timerRef.current !== null) {
            window.clearInterval(timerRef.current);
            timerRef.current = null;
          }
        }
      }, 200);
      setRecording('recording');
    } catch (err) {
      setRecording('idle');
      setError(err instanceof Error ? err.message : '无法获取麦克风权限，请检查浏览器设置。');
    }
  }, [changeAudio, ready]);

  const stopRecording = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      setRecording('stopping');
      recorderRef.current.stop();
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const picked = event.target.files?.[0] ?? null;
      if (picked) {
        changeAudio(picked, 'upload');
        setRecordDuration(0);
        setError(null);
      }
    },
    [changeAudio],
  );

  const handleLanguageChange = useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const nextValue = event.target.value;
      const previous = PREVIEW_LANGUAGES.find((item) => item.value === language);
      const next = PREVIEW_LANGUAGES.find((item) => item.value === nextValue);
      setLanguage(nextValue);
      if (next && previous && previewText.trim() === previous.defaultText.trim()) {
        setPreviewText(next.defaultText);
      }
    },
    [language, previewText],
  );

  const handleSubmit = useCallback(() => {
    if (!ready || !audioFile) return;
    setError(null);
    const taskId = startVoiceClone({
      file: audioFile,
      label: `克隆音色：${audioFile.name}`,
      request: {
        voice_id: null,
        preview_text: previewText.trim() || null,
        need_noise_reduction: false,
        need_volume_normalization: false,
        language_boost: language || null,
        source_filename: audioFile.name,
      },
    });
    setActiveTaskId(taskId);
  }, [audioFile, language, previewText, ready, startVoiceClone]);

  // Watch the active voice-clone task — when it succeeds, hydrate UI selection
  // and refresh history; on error surface the message.
  useEffect(() => {
    if (!activeTask) return;
    if (activeTask.status === 'success' && activeTask.response) {
      setSelectedVoiceId(activeTask.response.voice_id);
      void refreshHistory();
      const taskId = activeTask.id;
      // Keep the success state visible briefly, then clean up.
      const timer = window.setTimeout(() => {
        removeTask(taskId);
        setActiveTaskId((current) => (current === taskId ? null : current));
      }, 1500);
      return () => window.clearTimeout(timer);
    }
    if (activeTask.status === 'error') {
      setError(activeTask.error || '声音克隆失败，请稍后重试。');
    }
  }, [activeTask, refreshHistory, removeTask]);

  const handleKeepAlive = useCallback(
    async (voiceId: string) => {
      setBusyVoiceId(voiceId);
      setBusyKind('keep-alive');
      setHistoryError(null);
      try {
        await api.keepAliveVoiceClone(voiceId);
        await refreshHistory();
      } catch (err) {
        setHistoryError(err instanceof Error ? err.message : '保活失败，请稍后重试。');
      } finally {
        setBusyVoiceId(null);
        setBusyKind(null);
      }
    },
    [refreshHistory],
  );

  const handleDelete = useCallback(
    async (voiceId: string) => {
      if (!window.confirm('删除后本地记录和试听音频将一并清除，确定继续？')) return;
      setBusyVoiceId(voiceId);
      setBusyKind('delete');
      setHistoryError(null);
      try {
        await api.deleteVoiceClone(voiceId);
        if (selectedVoiceId === voiceId) {
          setSelectedVoiceId(null);
        }
        await refreshHistory();
      } catch (err) {
        setHistoryError(err instanceof Error ? err.message : '删除失败，请稍后重试。');
      } finally {
        setBusyVoiceId(null);
        setBusyKind(null);
      }
    },
    [refreshHistory, selectedVoiceId],
  );

  const submitLabel =
    submit === 'uploading' ? '上传音频中…' : submit === 'cloning' ? '生成中…' : '生成音色';

  return (
    <section
      ref={containerRef}
      className={`voice-maker ${isDragging ? 'is-dragging' : ''}`}
      style={{ gridTemplateColumns: `${leftFraction * 100}% 8px 1fr` }}
    >
      <div className="voice-maker__left">
        <header className="voice-maker__topbar">
          <h1>声音克隆</h1>
          <p>朗读一段文字，即可克隆你的专属声音</p>
        </header>

        {capabilityNotice ? <div className="voice-maker__notice">{capabilityNotice}</div> : null}

        <div className="voice-maker__form">
          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>选择场景并朗读</strong>
            </div>
            <div className="voice-maker__chips">
              {SCENE_PROMPTS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`voice-maker__chip ${sceneId === item.id ? 'is-active' : ''}`}
                  onClick={() => setSceneId(item.id)}
                >
                  <span className="voice-maker__chip-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="voice-maker__panel voice-maker__reading">
            <p className="voice-maker__reading-script">{scene.script}</p>

            {!audioFile ? (
              <div className="voice-maker__capture">
                <div className="voice-maker__record">
                  <button
                    type="button"
                    className={`voice-maker__mic ${recording === 'recording' ? 'is-recording' : ''}`}
                    onClick={recording === 'recording' ? stopRecording : startRecording}
                    disabled={!ready || recording === 'requesting' || recording === 'stopping'}
                    aria-label={recording === 'recording' ? '停止录音' : '开始录音'}
                  >
                    {recording === 'recording' ? (
                      <svg viewBox="0 0 24 24" width="26" height="26">
                        <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="9" y="3" width="6" height="12" rx="3" />
                        <path d="M5 11a7 7 0 0 0 14 0" strokeLinecap="round" />
                        <path d="M12 18v3" strokeLinecap="round" />
                      </svg>
                    )}
                  </button>
                  <div className="voice-maker__record-hint">
                    {recording === 'recording'
                      ? `正在录音… ${formatRecordingDuration(recordDuration)}`
                      : recording === 'requesting'
                        ? '正在请求麦克风权限…'
                        : '开始录音即表示您已取得声音授权'}
                  </div>
                </div>

                <div className="voice-maker__capture-divider">
                  <span>或</span>
                </div>

                <button
                  type="button"
                  className="voice-maker__upload-box"
                  onClick={handleUploadClick}
                  disabled={!ready}
                >
                  <span className="voice-maker__upload-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M12 15V3" strokeLinecap="round" />
                      <path d="m7 8 5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" strokeLinecap="round" />
                    </svg>
                  </span>
                  <div className="voice-maker__upload-text">
                    <strong>上传音频文件</strong>
                    <span>支持 MP3 / M4A / WAV，单文件 ≤ {formatBytes(VOICE_CLONE_MAX_BYTES)}</span>
                  </div>
                </button>
              </div>
            ) : (
              <div className="voice-maker__preview">
                <audio controls src={audioUrl ?? undefined} className="voice-maker__preview-audio" />
                <div className="voice-maker__preview-meta">
                  <span>{audioSource === 'record' ? '麦克风录音' : '上传文件'}</span>
                  <span>{audioFile.name}</span>
                  <span>{formatBytes(audioFile.size)}</span>
                  {audioSource === 'record' && recordDuration > 0 ? (
                    <span>时长 {formatRecordingDuration(recordDuration)}</span>
                  ) : null}
                </div>
                {fileWarning ? <div className="voice-maker__warning">{fileWarning}</div> : null}
                <div className="voice-maker__preview-actions">
                  <button type="button" className="voice-maker__link" onClick={clearAudio}>
                    重新录制 / 上传
                  </button>
                </div>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="audio/mpeg,audio/mp3,audio/mp4,audio/x-m4a,audio/wav,audio/wave,.mp3,.m4a,.wav"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>试听文本</strong>
              <select value={language} onChange={handleLanguageChange} className="voice-maker__lang-select">
                {PREVIEW_LANGUAGES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <textarea
              className="voice-maker__textarea"
              rows={3}
              maxLength={PREVIEW_TEXT_LIMIT}
              value={previewText}
              onChange={(event) => setPreviewText(event.target.value)}
              placeholder="填一段文字，生成时会合成一段试听音频"
            />
            <div className="voice-maker__field-foot">
              <span>
                {previewText.length} / {PREVIEW_TEXT_LIMIT} 字符
              </span>
            </div>
          </section>

          {error ? <div className="voice-maker__error">{error}</div> : null}

          <div className="voice-maker__submit-row">
            <div className="voice-maker__submit-hint">
              建议录制 {VOICE_CLONE_MIN_SECONDS}–{VOICE_CLONE_MAX_SECONDS / 60} 分钟清晰人声样本
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
          <h2>历史克隆</h2>
          <span className="voice-maker__list-count">{history.length} · MiniMax {VOICE_CLONE_INACTIVITY_DAYS} 天未使用会自动清理</span>
        </header>

        {historyError ? <div className="voice-maker__warning">{historyError}</div> : null}

        {historyLoading && history.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">正在加载…</div>
          </div>
        ) : history.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">还没有克隆过音色</div>
            <p>完成左侧录音或上传并点击生成，克隆结果会展示在这里。</p>
          </div>
        ) : (
          <div className="voice-maker__list">
            {history.map((item) => {
              const active = item.voice_id === selectedVoiceId;
              const remaining = daysUntilExpiry(item);
              const warn = remaining <= 2;
              return (
                <button
                  key={item.voice_id}
                  type="button"
                  className={`voice-maker__item ${active ? 'is-active' : ''}`}
                  onClick={() => setSelectedVoiceId(item.voice_id)}
                >
                  <div className="voice-maker__item-head">
                    <code>{item.voice_id}</code>
                    <span className={warn ? 'voice-maker__item-expiry is-warn' : 'voice-maker__item-expiry'}>
                      {expiryLabel(item)}
                    </span>
                  </div>
                  <div className="voice-maker__item-meta">
                    <span>{item.model}</span>
                    {item.source_filename ? <span>· {item.source_filename}</span> : null}
                    <span>· {formatRelative(item.created_at)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {selectedRecord ? (
          <div className="voice-maker__detail">
            <div className="voice-maker__detail-head">
              <code>{selectedRecord.voice_id}</code>
              <span>{selectedRecord.model}</span>
            </div>
            <div className="voice-maker__detail-meta">
              <span>创建 {formatRelative(selectedRecord.created_at)}</span>
              {selectedRecord.last_kept_alive_at ? (
                <span>· 上次保活 {formatRelative(selectedRecord.last_kept_alive_at)}</span>
              ) : null}
              <span>· {expiryLabel(selectedRecord)}</span>
            </div>
            {selectedRecord.preview_text ? (
              <p className="voice-maker__detail-text">{selectedRecord.preview_text}</p>
            ) : null}
            {selectedAudioUrl ? (
              <audio controls src={selectedAudioUrl} className="voice-maker__detail-audio" />
            ) : (
              <div className="voice-maker__detail-empty">本次克隆未生成试听音频</div>
            )}
            <div className="voice-maker__detail-actions">
              <button
                type="button"
                className="voice-maker__ghost-btn"
                onClick={() => void handleKeepAlive(selectedRecord.voice_id)}
                disabled={busyVoiceId === selectedRecord.voice_id}
              >
                {busyVoiceId === selectedRecord.voice_id && busyKind === 'keep-alive'
                  ? '保活中…'
                  : '立即保活'}
              </button>
              <button
                type="button"
                className="voice-maker__ghost-btn is-danger"
                onClick={() => void handleDelete(selectedRecord.voice_id)}
                disabled={busyVoiceId === selectedRecord.voice_id}
              >
                {busyVoiceId === selectedRecord.voice_id && busyKind === 'delete' ? '删除中…' : '删除'}
              </button>
            </div>
          </div>
        ) : null}
      </aside>
    </section>
  );
}

export { VoiceClonePage as VoiceCloneStudio };
