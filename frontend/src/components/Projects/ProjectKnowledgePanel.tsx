import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import type { KnowledgeDocument } from '../../types/knowledge';
import './projects.css';

interface ProjectKnowledgePanelProps {
  projectId: string;
}

interface UploadProgress {
  phase: 'uploading' | 'processing';
  percent: number;
  label: string;
  count: number;
}

function describeStage(document: KnowledgeDocument): string {
  if (document.status === 'failed') return '编译失败';
  if (document.status === 'ready') return '已编译为 Wiki';
  switch (document.processing_stage) {
    case 'queued':
      return '已上传 · 等待编译';
    case 'extracting':
      return '正在提取文本';
    case 'compiling':
    case 'embedding':
    case 'indexing':
      return '正在生成 Wiki 页面';
    case 'ready':
      return '已编译为 Wiki';
    default:
      return '正在处理';
  }
}

const isPending = (doc: KnowledgeDocument) => doc.status !== 'ready' && doc.status !== 'failed';

function mergeDocs(current: KnowledgeDocument[], incoming: KnowledgeDocument[]): KnowledgeDocument[] {
  const byId = new Map(current.map((d) => [d.id, d]));
  for (const d of incoming) byId.set(d.id, d);
  return Array.from(byId.values());
}

export const ProjectKnowledgePanel: React.FC<ProjectKnowledgePanelProps> = ({ projectId }) => {
  const { activeProject, setActiveProjectInstructions } = useChatStore();
  const [instructions, setInstructions] = useState('');
  const [savedInstructions, setSavedInstructions] = useState('');
  const [instructionsSaving, setInstructionsSaving] = useState(false);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const runIdRef = useRef(0);
  const tickerRef = useRef<number | null>(null);

  // Load instructions + documents whenever the active project changes.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const detail = await api.getProject(projectId);
        if (cancelled) return;
        const text = detail.project.instructions || '';
        setInstructions(text);
        setSavedInstructions(text);
        setDocuments(detail.documents || []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '加载项目知识库失败');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Background poll for compile status when the panel is reopened mid-compile
  // (no active upload run of its own). The active run drives its own polling.
  useEffect(() => {
    if (progress || !documents.some(isPending)) return;
    const tid = window.setInterval(async () => {
      try {
        const { documents: next } = await api.listProjectDocuments(projectId);
        setDocuments(next);
      } catch {
        // transient — keep polling
      }
    }, 3000);
    return () => window.clearInterval(tid);
  }, [documents, progress, projectId]);

  const stopTicker = useCallback(() => {
    if (tickerRef.current !== null) {
      window.clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopTicker(), [stopTicker]);

  // Time-based asymptotic ticker: visual percent approaches 89% during compile
  // (mirrors the global knowledge page). Only the backend ready signal pushes
  // it to 100%, even for long compiles.
  const startTicker = useCallback(
    (runId: number) => {
      stopTicker();
      const startedAt = Date.now();
      const tick = () => {
        if (runIdRef.current !== runId) {
          stopTicker();
          return;
        }
        const elapsed = Date.now() - startedAt;
        const fraction = 1 - Math.exp(-elapsed / 90_000);
        const target = Math.min(89, Math.round(45 + 44 * fraction));
        setProgress((prev) => {
          if (!prev) return prev;
          if (prev.percent >= 100 || target <= prev.percent) return prev;
          return { ...prev, percent: target };
        });
      };
      tick();
      tickerRef.current = window.setInterval(tick, 240);
    },
    [stopTicker],
  );

  const trackProcessing = useCallback(
    async (documentIds: string[]) => {
      const runId = ++runIdRef.current;
      setProgress({ phase: 'processing', percent: 45, label: '正在准备入库', count: documentIds.length });
      startTicker(runId);

      while (runIdRef.current === runId) {
        let docs: KnowledgeDocument[] = [];
        try {
          docs = (await api.listProjectDocuments(projectId)).documents;
          setDocuments(docs);
        } catch {
          // transient — retry next loop
        }
        const scoped = docs.filter((d) => documentIds.includes(d.id));
        if (scoped.length) {
          const processing =
            scoped.find((d) => d.status === 'processing') ??
            scoped.find((d) => d.status === 'failed') ??
            scoped[scoped.length - 1];
          setProgress((prev) => (prev ? { ...prev, label: describeStage(processing), count: scoped.length } : prev));
          const finished = scoped.filter((d) => d.status === 'ready' || d.status === 'failed').length === scoped.length;
          if (finished) {
            stopTicker();
            setProgress((prev) => (prev ? { ...prev, percent: 100 } : prev));
            if (scoped.some((d) => d.status === 'failed')) {
              setError('部分文件处理失败,请查看列表中的状态。');
            }
            break;
          }
        }
        await new Promise((resolve) => window.setTimeout(resolve, 800));
      }
      stopTicker();
      if (runIdRef.current === runId) {
        window.setTimeout(() => {
          if (runIdRef.current === runId) setProgress(null);
        }, 400);
      }
    },
    [projectId, startTicker, stopTicker],
  );

  const saveInstructions = useCallback(async () => {
    if (instructions === savedInstructions || instructionsSaving) return;
    setInstructionsSaving(true);
    setError(null);
    try {
      await api.updateProjectInstructions(projectId, instructions);
      setSavedInstructions(instructions);
      if (activeProject?.id === projectId) {
        setActiveProjectInstructions(instructions);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存项目指令失败');
    } finally {
      setInstructionsSaving(false);
    }
  }, [instructions, savedInstructions, instructionsSaving, projectId, activeProject?.id, setActiveProjectInstructions]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0 || progress) return;
    const arr = Array.from(files);
    setError(null);
    setProgress({ phase: 'uploading', percent: 0, label: '正在上传文件', count: arr.length });
    try {
      const { documents: created } = await api.uploadProjectDocuments(projectId, arr, (p) => {
        setProgress((prev) =>
          prev ? { ...prev, percent: Math.max(1, Math.min(45, Math.round(p.percent * 0.45))) } : prev,
        );
      });
      setDocuments((current) => mergeDocs(current, created));
      await trackProcessing(created.map((d) => d.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传文件失败');
      stopTicker();
      setProgress(null);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleAddUrl = async () => {
    const trimmed = url.trim();
    if (!trimmed || progress) return;
    setError(null);
    setProgress({ phase: 'uploading', percent: 45, label: '正在抓取链接', count: 1 });
    try {
      const { document } = await api.addProjectUrlSource(projectId, trimmed);
      setDocuments((current) => mergeDocs(current, [document]));
      setUrl('');
      await trackProcessing([document.id]);
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加链接失败');
      stopTicker();
      setProgress(null);
    }
  };

  const handleDelete = async (documentId: string) => {
    try {
      await api.deleteProjectDocument(projectId, documentId);
      setDocuments((current) => current.filter((d) => d.id !== documentId));
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除文件失败');
    }
  };

  const handleRecompile = async () => {
    if (progress) return;
    setError(null);
    setProgress({ phase: 'processing', percent: 45, label: '正在重新编译', count: documents.length });
    try {
      await api.recompileProjectWiki(projectId);
      await trackProcessing(documents.map((d) => d.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : '重新编译失败');
      stopTicker();
      setProgress(null);
    }
  };

  const dirty = instructions !== savedInstructions;
  const busy = progress !== null;

  return (
    <aside className="project-knowledge">
      <section className="project-knowledge__section">
        <div className="project-knowledge__section-head">
          <h2>项目指令</h2>
          {dirty ? (
            <button
              type="button"
              className="project-knowledge__save"
              onClick={() => void saveInstructions()}
              disabled={instructionsSaving}
            >
              {instructionsSaving ? '保存中…' : '保存'}
            </button>
          ) : (
            <span className="project-knowledge__hint">自动注入到本项目会话</span>
          )}
        </div>
        <textarea
          className="project-knowledge__instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          onBlur={() => void saveInstructions()}
          placeholder="给本项目下所有会话的自定义指令，例如：始终用中文回答、优先引用项目文件……"
          rows={5}
        />
      </section>

      <section className="project-knowledge__section">
        <div className="project-knowledge__section-head">
          <h2>项目文件</h2>
          <div className="project-knowledge__file-actions">
            {documents.length > 0 ? (
              <button
                type="button"
                className="project-knowledge__ghost"
                onClick={() => void handleRecompile()}
                disabled={busy}
                title="重新编译为 Wiki"
              >
                重新编译
              </button>
            ) : null}
            <button
              type="button"
              className="project-knowledge__save"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              上传文件
            </button>
          </div>
        </div>
        <p className="project-knowledge__desc">
          文件会编译成项目 Wiki。本项目的会话可由助手按需查阅，而不是每次强制塞入上下文。
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => void handleFiles(e.target.files)}
        />

        <div className="project-knowledge__url">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleAddUrl();
            }}
            placeholder="粘贴微信公众号文章链接…"
            disabled={busy}
          />
          <button
            type="button"
            className="project-knowledge__ghost"
            onClick={() => void handleAddUrl()}
            disabled={busy || !url.trim()}
          >
            添加链接
          </button>
        </div>

        {progress ? (
          <div className="project-knowledge__progress">
            <div className="project-knowledge__progress-meta">
              <span>
                {progress.phase === 'uploading' ? '正在上传 ' : '正在编译 '}
                {progress.count} 份 · {progress.label}
              </span>
              <strong>{progress.percent}%</strong>
            </div>
            <div className="project-knowledge__progress-track">
              <div
                className="project-knowledge__progress-fill"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
          </div>
        ) : null}

        {documents.length === 0 ? (
          <div className="project-knowledge__empty">还没有文件。上传后助手即可在本项目内查阅。</div>
        ) : (
          <ul className="project-knowledge__docs">
            {documents.map((doc) => (
              <li key={doc.id} className="project-knowledge__doc">
                <div className="project-knowledge__doc-main">
                  <span className="project-knowledge__doc-name" title={doc.name}>
                    {doc.name}
                  </span>
                  <span
                    className={`project-knowledge__doc-status ${
                      doc.status === 'failed' ? 'is-failed' : isPending(doc) ? 'is-pending' : 'is-ready'
                    }`}
                  >
                    {describeStage(doc)}
                  </span>
                </div>
                <button
                  type="button"
                  className="project-knowledge__doc-delete"
                  title="删除文件"
                  onClick={() => void handleDelete(doc.id)}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {error ? <div className="project-knowledge__error">{error}</div> : null}
    </aside>
  );
};
