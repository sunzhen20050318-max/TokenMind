import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../services/api';
import type { CreativeCapabilitySettings } from '../../types/config';
import { isCreativeCapabilityConfigured } from '../../types/config';
import type { TtsVoiceListResponse, TtsVoiceOption } from '../../types';
import type { AssetItem } from '../../types/assets';
import {
  TTS_MODELS,
  TTS_TEXT_LIMIT,
  appendTtsHistory,
  getEmotionOptionsForModel,
  groupVoiceOptions,
  isTtsEmotionSupported,
  loadTtsHistory,
  makeHistoryId,
  saveTtsHistory,
  voiceOptionLabel,
} from './ttsPageState';
import type { TtsHistoryItem } from './ttsPageState';
import './voiceClone.css';

interface TtsPageProps {
  capability: CreativeCapabilitySettings | null | undefined;
}

type SubmitPhase = 'idle' | 'running' | 'success' | 'error';

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
    window.localStorage.setItem('tokenmind:tts-split', fraction.toFixed(3));
  } catch {
    // ignore
  }
}

function loadSplit(): number {
  try {
    const raw = window.localStorage.getItem('tokenmind:tts-split');
    const parsed = raw ? Number.parseFloat(raw) : NaN;
    if (Number.isFinite(parsed) && parsed >= 0.3 && parsed <= 0.8) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return 0.56;
}

function ttsHistoryFromAsset(asset: AssetItem): TtsHistoryItem {
  return {
    id: asset.id,
    attachment_id: asset.id,
    voice_id: 'saved',
    voice_label: '历史语音',
    model: '已保存音频',
    text: asset.preview_text?.trim() || asset.name,
    usage_characters: asset.preview_text?.length ?? null,
    created_at: asset.created_at || new Date().toISOString(),
    filename: asset.name,
    mime_type: asset.mime_type ?? 'audio/mpeg',
    trace_id: null,
  };
}

function mergeTtsHistory(current: TtsHistoryItem[], libraryItems: TtsHistoryItem[]): TtsHistoryItem[] {
  const byAttachment = new Map<string, TtsHistoryItem>();
  for (const item of libraryItems) {
    byAttachment.set(item.attachment_id, item);
  }
  for (const item of current) {
    const fallback = byAttachment.get(item.attachment_id);
    byAttachment.set(item.attachment_id, fallback ? { ...fallback, ...item } : item);
  }
  return Array.from(byAttachment.values())
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
    .slice(0, 50);
}

export function TtsPage({ capability }: TtsPageProps) {
  const [text, setText] = useState<string>('');
  const [voiceId, setVoiceId] = useState<string>('');
  const [model, setModel] = useState<string>(TTS_MODELS[0].value);
  const [speed, setSpeed] = useState<number>(1.0);
  const [volume, setVolume] = useState<number>(1.0);
  const [pitch, setPitch] = useState<number>(0);
  const [emotion, setEmotion] = useState<string>('');
  const [submit, setSubmit] = useState<SubmitPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<TtsVoiceListResponse>({ cloned: [], system: [] });
  const [voicesLoading, setVoicesLoading] = useState<boolean>(true);
  const [voicesError, setVoicesError] = useState<string | null>(null);
  const [history, setHistory] = useState<TtsHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(true);
  const [deletingHistoryId, setDeletingHistoryId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [leftFraction, setLeftFraction] = useState<number>(loadSplit);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setHistory(loadTtsHistory());
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadLibraryHistory() {
      setHistoryLoading(true);
      try {
        const libraryAssets: AssetItem[] = [];
        let cursor: number | null | undefined = 0;
        let pageCount = 0;
        while (cursor !== null && pageCount < 10 && libraryAssets.length < 50) {
          const page = await api.listAssets({
            category: 'tts',
            cursor: cursor ?? 0,
            limit: 100,
          });
          libraryAssets.push(...page.items);
          cursor = page.next_cursor;
          pageCount += 1;
        }
        if (!isMounted) return;
        const libraryHistory = libraryAssets.map(ttsHistoryFromAsset);
        setHistory((current) => {
          const next = mergeTtsHistory(current, libraryHistory);
          saveTtsHistory(next);
          return next;
        });
      } catch {
        // Keep the TTS page usable when the asset index cannot be loaded.
      } finally {
        if (isMounted) {
          setHistoryLoading(false);
        }
      }
    }

    void loadLibraryHistory();

    return () => {
      isMounted = false;
    };
  }, []);

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

  const configured = isCreativeCapabilityConfigured(capability);
  const enabled = Boolean(capability?.enabled);
  const ready = configured && enabled;
  const capabilityNotice = !configured
    ? '还没有配置语音合成模型。请先到设置中心的声音工程里填入 API Key 并启用语音合成。'
    : !enabled
      ? '语音合成模型已经配置完成，但当前还没有启用。请到设置中心启用语音合成能力。'
      : null;

  const refreshVoices = useCallback(async () => {
    setVoicesLoading(true);
    setVoicesError(null);
    try {
      const payload = await api.listTtsVoices();
      setVoices(payload);
      setVoiceId((current) => {
        if (current) return current;
        return payload.cloned[0]?.voice_id ?? payload.system[0]?.voice_id ?? '';
      });
    } catch (err) {
      setVoicesError(err instanceof Error ? err.message : '无法加载音色列表');
    } finally {
      setVoicesLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshVoices();
  }, [refreshVoices]);

  const allVoices = useMemo<TtsVoiceOption[]>(
    () => [...voices.cloned, ...voices.system],
    [voices],
  );
  const { cloned: clonedVoices, system: systemVoices } = useMemo(
    () => groupVoiceOptions(allVoices),
    [allVoices],
  );
  const selectedVoice = useMemo(
    () => allVoices.find((voice) => voice.voice_id === voiceId) ?? null,
    [allVoices, voiceId],
  );
  const emotionOptions = useMemo(() => getEmotionOptionsForModel(model), [model]);

  useEffect(() => {
    if (!isTtsEmotionSupported(model, emotion)) {
      setEmotion('');
    }
  }, [emotion, model]);

  const canSubmit =
    ready && text.trim().length > 0 && voiceId.trim().length > 0 && submit !== 'running';

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmit('running');
    try {
      const response = await api.synthesizeVoice({
        text: text.trim(),
        voice_id: voiceId.trim(),
        model,
        speed,
        volume,
        pitch,
        emotion: emotion || null,
      });
      const entry: TtsHistoryItem = {
        id: makeHistoryId(),
        attachment_id: response.attachment_id,
        voice_id: response.voice_id,
        voice_label: selectedVoice?.label ?? response.voice_id,
        model: response.model,
        text: text.trim().slice(0, 500),
        usage_characters: response.usage_characters ?? null,
        created_at: new Date().toISOString(),
        filename: response.filename,
        mime_type: response.mime_type,
        trace_id: response.trace_id ?? null,
      };
      const next = appendTtsHistory(history, entry);
      setHistory(next);
      saveTtsHistory(next);
      setSelectedId(entry.id);
      setSubmit('success');
    } catch (err) {
      setSubmit('error');
      setError(err instanceof Error ? err.message : '合成失败，请稍后重试。');
    }
  }, [canSubmit, emotion, history, model, pitch, selectedVoice, speed, text, voiceId, volume]);

  const handleDeleteHistoryItem = useCallback(
    async (item: TtsHistoryItem) => {
      if (!window.confirm('确定删除这条语音合成记录吗？音频文件也会从本地资产库移除。')) {
        return;
      }
      setDeletingHistoryId(item.id);
      setError(null);
      try {
        await api.deleteAsset(item.attachment_id);
        const next = history.filter((historyItem) => historyItem.id !== item.id);
        setHistory(next);
        saveTtsHistory(next);
        if (selectedId === item.id) {
          setSelectedId(next[0]?.id ?? null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '删除语音失败，请稍后重试。');
      } finally {
        setDeletingHistoryId(null);
      }
    },
    [history, selectedId],
  );

  const selectedItem = useMemo(
    () => history.find((item) => item.id === selectedId) ?? null,
    [history, selectedId],
  );

  const submitLabel = submit === 'running' ? '合成中…' : '合成语音';

  return (
    <section
      ref={containerRef}
      className={`voice-maker ${isDragging ? 'is-dragging' : ''}`}
      style={{ gridTemplateColumns: `${leftFraction * 100}% 8px 1fr` }}
    >
      <div className="voice-maker__left">
        <header className="voice-maker__topbar">
          <h1>语音合成</h1>
          <p>用系统音色、克隆音色或设计音色把文字转成语音</p>
        </header>

        {capabilityNotice ? <div className="voice-maker__notice">{capabilityNotice}</div> : null}

        <div className="voice-maker__form">
          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>要朗读的文字</strong>
              <span className="voice-maker__field-foot">
                {text.length} / {TTS_TEXT_LIMIT}
              </span>
            </div>
            <textarea
              className="voice-maker__textarea"
              rows={6}
              maxLength={TTS_TEXT_LIMIT}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="在这里粘贴或输入要朗读的内容。支持中文、英文等多语言，最长 10000 字符。"
            />
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>音色</strong>
              {voicesLoading ? <span className="voice-maker__field-foot">加载中…</span> : null}
            </div>

            {voicesError ? <div className="voice-maker__warning">{voicesError}</div> : null}

            <select
              className="voice-maker__lang-select"
              value={voiceId}
              onChange={(event) => setVoiceId(event.target.value)}
              style={{ width: '100%', minWidth: 0 }}
            >
              <option value="">
                {voicesLoading ? '加载中…' : '— 请选择音色 —'}
              </option>
              {clonedVoices.length > 0 ? (
                <optgroup label={`我的音色 (${clonedVoices.length})`}>
                  {clonedVoices.map((voice) => (
                    <option key={voice.voice_id} value={voice.voice_id}>
                      {voiceOptionLabel(voice)}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              <optgroup label={`系统音色 (${systemVoices.length})`}>
                {systemVoices.map((voice) => (
                  <option key={voice.voice_id} value={voice.voice_id}>
                    {voice.label}
                    （{voice.gender === 'male' ? '男' : voice.gender === 'female' ? '女' : '中'}）
                    {voice.description ? ` · ${voice.description}` : ''}
                  </option>
                ))}
              </optgroup>
            </select>

            {selectedVoice ? (
              <div className="voice-maker__field-foot" style={{ marginTop: 8, textAlign: 'left' }}>
                当前：
                <strong style={{ color: 'var(--voice-text)' }}>
                  {selectedVoice.kind === 'cloned'
                    ? selectedVoice.source === 'design'
                      ? selectedVoice.display_name?.trim() || '我的设计音色'
                      : '我的克隆音色'
                    : selectedVoice.label}
                </strong>
                {selectedVoice.kind === 'system' && selectedVoice.description
                  ? ` · ${selectedVoice.description}`
                  : null}
                {selectedVoice.kind === 'cloned' && selectedVoice.source_filename
                  ? ` · ${selectedVoice.source_filename}`
                  : null}
              </div>
            ) : null}

            {clonedVoices.length === 0 ? (
              <div className="voice-maker__field-foot" style={{ marginTop: 8, textAlign: 'left' }}>
                还没克隆过音色？可以直接用下面的系统音色，或先到
                <strong style={{ color: 'var(--voice-text)' }}> 声音克隆 </strong>
                页面生成你自己的声音。
              </div>
            ) : null}
          </section>

          <section className="voice-maker__panel">
            <div className="voice-maker__panel-head">
              <strong>合成参数</strong>
            </div>
            <div className="voice-maker__param-grid">
              <label>
                <span>模型</span>
                <select value={model} onChange={(event) => setModel(event.target.value)}>
                  {TTS_MODELS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>情绪</span>
                <select value={emotion} onChange={(event) => setEmotion(event.target.value)}>
                  {emotionOptions.map((item) => (
                    <option key={item.value || 'default'} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>语速 · {speed.toFixed(2)}×</span>
                <input
                  type="range"
                  min={0.5}
                  max={2.0}
                  step={0.05}
                  value={speed}
                  onChange={(event) => setSpeed(Number(event.target.value))}
                />
              </label>
              <label>
                <span>音量 · {volume.toFixed(2)}</span>
                <input
                  type="range"
                  min={0.1}
                  max={5.0}
                  step={0.1}
                  value={volume}
                  onChange={(event) => setVolume(Number(event.target.value))}
                />
              </label>
              <label>
                <span>音高 · {pitch > 0 ? `+${pitch}` : pitch}</span>
                <input
                  type="range"
                  min={-12}
                  max={12}
                  step={1}
                  value={pitch}
                  onChange={(event) => setPitch(Number(event.target.value))}
                />
              </label>
            </div>
          </section>

          {error ? <div className="voice-maker__error">{error}</div> : null}

          <div className="voice-maker__submit-row">
            <div className="voice-maker__submit-hint">
              Speech 2.8 按字符计费，合成后会消耗你的 Token Plan 配额
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
          <h2>合成历史</h2>
          <span className="voice-maker__list-count">{history.length} / 50 · 本地保存</span>
        </header>

        {historyLoading && history.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">正在加载历史语音</div>
            <p>正在从本地资产库恢复之前合成的语音。</p>
          </div>
        ) : history.length === 0 ? (
          <div className="voice-maker__empty">
            <div className="voice-maker__empty-title">还没有合成记录</div>
            <p>在左侧填入文字并选择音色，点击合成后结果会展示在这里。</p>
          </div>
        ) : (
          <div className="voice-maker__list">
            {history.map((item) => {
              const active = item.id === selectedId;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`voice-maker__item ${active ? 'is-active' : ''}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="voice-maker__item-head">
                    <code>{item.voice_label}</code>
                    <span className="voice-maker__item-expiry">
                      {item.usage_characters != null ? `${item.usage_characters} 字符` : ''}
                    </span>
                  </div>
                  <div className="voice-maker__item-meta">
                    <span>{item.model}</span>
                    <span>· {formatRelative(item.created_at)}</span>
                  </div>
                  <div className="voice-maker__tts-preview" title={item.text}>
                    {item.text}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {selectedItem ? (
          <div className="voice-maker__detail">
            <div className="voice-maker__detail-head">
              <code>{selectedItem.voice_label}</code>
              <span>{selectedItem.model}</span>
            </div>
            <div className="voice-maker__detail-meta">
              <span>{formatRelative(selectedItem.created_at)}</span>
              {selectedItem.usage_characters != null ? (
                <span>· 消耗 {selectedItem.usage_characters} 字符</span>
              ) : null}
              {selectedItem.trace_id ? <span>· trace {selectedItem.trace_id}</span> : null}
            </div>
            <p className="voice-maker__detail-text">{selectedItem.text}</p>
            <audio
              controls
              src={api.getAttachmentUrl(selectedItem.attachment_id)}
              className="voice-maker__detail-audio"
            />
            <div className="voice-maker__detail-actions">
              <a
                className="voice-maker__ghost-btn"
                href={api.getAttachmentUrl(selectedItem.attachment_id)}
                download={selectedItem.filename}
              >
                下载 MP3
              </a>
              <button
                type="button"
                className="voice-maker__ghost-btn is-danger"
                disabled={deletingHistoryId === selectedItem.id}
                onClick={() => void handleDeleteHistoryItem(selectedItem)}
              >
                {deletingHistoryId === selectedItem.id ? '删除中...' : '删除'}
              </button>
            </div>
          </div>
        ) : null}
      </aside>
    </section>
  );
}
