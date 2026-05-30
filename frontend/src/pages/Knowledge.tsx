import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../services/api';
import { AddUrlSourceModal } from '../components/Knowledge/AddUrlSourceModal';
import { ConfirmModal } from '../components/Knowledge/ConfirmModal';
import { CreateKnowledgeBaseModal } from '../components/Knowledge/CreateKnowledgeBaseModal';
import { RenameKnowledgeBaseModal } from '../components/Knowledge/RenameKnowledgeBaseModal';
import { WikiKbDetail } from '../components/Knowledge/WikiKbDetail';
import { CardGridSkeleton, ListSkeleton } from '../components/Skeleton/Skeleton';
import { isWikiKb } from '../types/knowledge';
import type { KnowledgeBase, KnowledgeDetailResponse } from '../types/knowledge';
import type { UploadProgress } from '../types';
import './knowledge.css';

function formatDate(value?: string): string {
  if (!value) {
    return '—';
  }
  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function describeProcessingStage(stage?: string): string {
  switch (stage) {
    case 'queued':
      return '已上传，等待处理';
    case 'extracting':
      return '正在提取文本';
    case 'chunking':
      return '正在切分内容';
    case 'embedding':
      return '正在生成向量';
    case 'indexing':
      return '正在写入索引';
    case 'compiling_source':
      return '正在写源页面';
    case 'compiling_with_llm':
      return 'LLM 正在抽取实体与主题（可能 1–3 分钟）';
    case 'ready':
      return '处理完成';
    case 'failed':
      return '处理失败';
    default:
      return '正在处理文档';
  }
}

function buildProcessingSummary(documents: KnowledgeDetailResponse['documents'], targetIds: string[]) {
  const scoped = documents.filter((document) => targetIds.includes(document.id));
  if (!scoped.length) {
    return null;
  }

  const averageProgress = Math.round(
    scoped.reduce((sum, document) => sum + (document.processing_progress ?? 0), 0) / scoped.length
  );
  const readyCount = scoped.filter((document) => document.status === 'ready').length;
  const failedCount = scoped.filter((document) => document.status === 'failed').length;
  const processingDocument =
    scoped.find((document) => document.status === 'processing') ??
    scoped.find((document) => document.status === 'failed') ??
    scoped[scoped.length - 1];

  return {
    averageProgress,
    readyCount,
    failedCount,
    totalCount: scoped.length,
    stageLabel: describeProcessingStage(processingDocument?.processing_stage),
  };
}

interface KnowledgePageProps {
  isActive?: boolean;
}

export const KnowledgePage: React.FC<KnowledgePageProps> = ({ isActive = true }) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadPollRef = useRef(0);
  const progressTickerRef = useRef<number | null>(null);
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showAddUrlFor, setShowAddUrlFor] = useState<string | null>(null);
  const [renameDialog, setRenameDialog] = useState<{ id: string; name: string } | null>(null);
  const [deleteKbDialog, setDeleteKbDialog] = useState<{ id: string; name: string } | null>(null);
  const [deleteDocDialog, setDeleteDocDialog] = useState<{ id: string; name: string } | null>(null);
  const [infoPopoverOpen, setInfoPopoverOpen] = useState(false);
  const [updatingBaseId, setUpdatingBaseId] = useState<string | null>(null);
  const [renamingBaseId, setRenamingBaseId] = useState<string | null>(null);
  const [deletingBaseId, setDeletingBaseId] = useState<string | null>(null);
  const [isUploadingDocuments, setIsUploadingDocuments] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [uploadingCount, setUploadingCount] = useState(0);
  const [uploadPhase, setUploadPhase] = useState<'uploading' | 'processing' | null>(null);
  const [uploadStageLabel, setUploadStageLabel] = useState('');

  const loadOverview = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const payload = await api.getKnowledgeOverview();
      setItems(payload.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载知识库失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (knowledgeBaseId: string) => {
    try {
      setDetailLoading(true);
      setError(null);
      const payload = await api.getKnowledgeDetail(knowledgeBaseId);
      setDetail(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载知识库详情失败');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const refreshDetail = useCallback(async (knowledgeBaseId: string) => {
    const payload = await api.getKnowledgeDetail(knowledgeBaseId);
    setDetail(payload);
    return payload;
  }, []);

  useEffect(() => {
    if (!isActive) return;
    void loadOverview();
  }, [isActive, loadOverview]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedId);
  }, [loadDetail, selectedId]);

  // Stop any running progress ticker AND cancel the processing poll loop on
  // unmount so an unmounted component doesn't keep calling setUploadProgress or
  // polling refreshDetail. Bumping uploadPollRef makes the loop's
  // `while (uploadPollRef.current === runId)` guard fail on its next iteration.
  useEffect(() => {
    return () => {
      uploadPollRef.current += 1;
      if (progressTickerRef.current !== null) {
        window.clearInterval(progressTickerRef.current);
        progressTickerRef.current = null;
      }
    };
  }, []);

  const summary = useMemo(() => {
    const documentCount = items.reduce((sum, item) => sum + item.document_count, 0);
    const enabledCount = items.filter((item) => item.enabled).length;
    const latest = [...items].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    )[0];
    return {
      baseCount: items.length,
      enabledCount,
      documentCount,
      latestUpdatedAt: latest?.updated_at,
    };
  }, [items]);

  const handleCreated = async () => {
    setError(null);
    await loadOverview();
  };

  const submitRenameKnowledgeBase = async (knowledgeBaseId: string, nextName: string) => {
    setRenamingBaseId(knowledgeBaseId);
    setError(null);
    try {
      const payload = await api.updateKnowledgeBase(knowledgeBaseId, { name: nextName });
      setItems((current) =>
        current.map((item) =>
          item.id === knowledgeBaseId ? { ...item, name: payload.knowledge_base.name } : item
        )
      );
      if (detail?.knowledge_base.id === knowledgeBaseId) {
        setDetail({
          ...detail,
          knowledge_base: { ...detail.knowledge_base, name: payload.knowledge_base.name },
        });
      }
    } finally {
      setRenamingBaseId(null);
    }
  };

  const submitDeleteKnowledgeBase = async (knowledgeBaseId: string) => {
    setDeletingBaseId(knowledgeBaseId);
    setError(null);
    try {
      await api.deleteKnowledgeBase(knowledgeBaseId);
      if (selectedId === knowledgeBaseId) {
        setSelectedId(null);
        setDetail(null);
      }
      await loadOverview();
    } finally {
      setDeletingBaseId(null);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || !selectedId) {
      return;
    }
    try {
      setError(null);
      await api.uploadKnowledgeDocuments(selectedId, Array.from(files));
      await Promise.all([loadOverview(), loadDetail(selectedId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传资料失败');
    }
  };

  const handleUploadWithProgress = async (files: FileList | null) => {
    if (!files || !selectedId) {
      return;
    }
    const uploadFiles = Array.from(files);
    try {
      setError(null);
      setIsUploadingDocuments(true);
      setUploadingCount(uploadFiles.length);
      setUploadProgress({
        loaded: 0,
        total: uploadFiles.reduce((sum, file) => sum + file.size, 0),
        percent: 0,
      });
      await api.uploadKnowledgeDocuments(selectedId, uploadFiles, setUploadProgress);
      await Promise.all([loadOverview(), loadDetail(selectedId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传资料失败');
    } finally {
      setIsUploadingDocuments(false);
      setUploadingCount(0);
      setUploadProgress(null);
    }
  };

  void handleUpload;
  void handleUploadWithProgress;
  void uploadPhase;
  void uploadStageLabel;

  const stopProgressTicker = useCallback(() => {
    if (progressTickerRef.current !== null) {
      window.clearInterval(progressTickerRef.current);
      progressTickerRef.current = null;
    }
  }, []);

  const startProgressTicker = useCallback(
    (runId: number) => {
      stopProgressTicker();
      const startedAt = Date.now();
      // Asymptote: visual percent approaches 89% as elapsed time grows.
      // Pacing constant 90s → at 30s ≈ 58%, 60s ≈ 67%, 90s ≈ 73%, 180s ≈ 84%.
      // The bar never hits 100% on time alone — only the actual ready signal
      // from the backend can push to 100%, even if compile takes 10 min.
      const tick = () => {
        if (uploadPollRef.current !== runId) {
          stopProgressTicker();
          return;
        }
        const elapsed = Date.now() - startedAt;
        const fraction = 1 - Math.exp(-elapsed / 90_000);
        const target = Math.min(89, Math.round(45 + 44 * fraction));
        setUploadProgress((prev) => {
          if (!prev) return { loaded: target, total: 100, percent: target };
          if (prev.percent >= 100) return prev; // backend ready already
          if (target <= prev.percent) return prev; // monotonic
          return { ...prev, loaded: target, total: 100, percent: target };
        });
      };
      tick();
      progressTickerRef.current = window.setInterval(tick, 240);
    },
    [stopProgressTicker],
  );

  const trackProcessingProgress = useCallback(
    async (knowledgeBaseId: string, documentIds: string[]) => {
      const runId = ++uploadPollRef.current;
      setUploadPhase('processing');
      setUploadStageLabel('正在准备入库');
      startProgressTicker(runId);

      while (uploadPollRef.current === runId) {
        const payload = await refreshDetail(knowledgeBaseId);
        const summary = buildProcessingSummary(payload.documents, documentIds);
        if (!summary) {
          break;
        }

        setUploadingCount(summary.totalCount);
        setUploadStageLabel(summary.stageLabel);
        // Visual percent is driven by the time-based ticker. Polling here
        // only handles the stage label and detecting the terminal state.

        const allFinished = summary.readyCount + summary.failedCount === summary.totalCount;
        if (allFinished) {
          stopProgressTicker();
          setUploadProgress((prev) =>
            prev ? { ...prev, loaded: 100, total: 100, percent: 100 } : null,
          );
          if (summary.failedCount > 0) {
            setError('部分知识库资料处理失败,请在资料列表中查看详情。');
          }
          break;
        }

        await new Promise((resolve) => window.setTimeout(resolve, 700));
      }
      stopProgressTicker();

      if (uploadPollRef.current === runId) {
        await loadOverview();
        window.setTimeout(() => {
          if (uploadPollRef.current === runId) {
            setIsUploadingDocuments(false);
            setUploadingCount(0);
            setUploadPhase(null);
            setUploadStageLabel('');
            setUploadProgress(null);
          }
        }, 350);
      }
    },
    [loadOverview, refreshDetail, startProgressTicker, stopProgressTicker]
  );

  const runUploadWithPipelineProgress = useCallback(
    async (files: FileList | null) => {
      if (!files || !selectedId) {
        return;
      }
      const uploadFiles = Array.from(files);
      try {
        setError(null);
        setIsUploadingDocuments(true);
        setUploadPhase('uploading');
        setUploadStageLabel('正在上传资料');
        setUploadingCount(uploadFiles.length);
        setUploadProgress({
          loaded: 0,
          total: uploadFiles.reduce((sum, file) => sum + file.size, 0),
          percent: 0,
        });
        const response = await api.uploadKnowledgeDocuments(selectedId, uploadFiles, (progress) => {
          setUploadProgress({
            ...progress,
            percent: Math.max(1, Math.min(45, Math.round(progress.percent * 0.45))),
          });
        });
        await loadOverview();
        await trackProcessingProgress(
          selectedId,
          response.documents.map((document) => document.id)
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : '上传资料失败');
        stopProgressTicker();
        setIsUploadingDocuments(false);
        setUploadingCount(0);
        setUploadPhase(null);
        setUploadStageLabel('');
        setUploadProgress(null);
      }
    },
    [loadOverview, selectedId, stopProgressTicker, trackProcessingProgress]
  );

  const handleUrlSourceAdded = async (knowledgeBaseId: string, documentId: string) => {
    try {
      setError(null);
      // Drive the same progress UI as a file upload. The fetch is already
      // done at this point, so we skip the "uploading" phase and jump
      // straight into "processing" to track the LLM compile.
      setIsUploadingDocuments(true);
      setUploadingCount(1);
      setUploadPhase('processing');
      setUploadStageLabel('正在准备入库');
      setUploadProgress({ loaded: 5, total: 100, percent: 45 });
      await loadDetail(knowledgeBaseId);
      await trackProcessingProgress(knowledgeBaseId, [documentId]);
      await loadOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加 URL 素材失败');
      stopProgressTicker();
      setIsUploadingDocuments(false);
      setUploadingCount(0);
      setUploadPhase(null);
      setUploadStageLabel('');
      setUploadProgress(null);
    }
  };

  const requestDeleteDocument = (documentId: string, documentName: string) => {
    setDeleteDocDialog({ id: documentId, name: documentName });
  };

  const submitDeleteDocument = async (documentId: string) => {
    if (!selectedId) return;
    setError(null);
    await api.deleteKnowledgeDocument(selectedId, documentId);
    await Promise.all([loadOverview(), loadDetail(selectedId)]);
  };

  const handleToggleEnabled = async (knowledgeBaseId: string, enabled: boolean) => {
    try {
      setUpdatingBaseId(knowledgeBaseId);
      setError(null);
      const payload = await api.updateKnowledgeBase(knowledgeBaseId, { enabled });
      setItems((current) =>
        current.map((item) =>
          item.id === knowledgeBaseId ? { ...item, enabled: payload.knowledge_base.enabled } : item
        )
      );
      if (detail?.knowledge_base.id === knowledgeBaseId) {
        setDetail({
          ...detail,
          knowledge_base: { ...detail.knowledge_base, enabled: payload.knowledge_base.enabled },
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新知识库状态失败');
    } finally {
      setUpdatingBaseId(null);
    }
  };

  return (
    <section className={`knowledge-page ${selectedId ? 'knowledge-page--detail' : ''}`}>
      {!selectedId ? (
        <header className="knowledge-page__header">
          <div>
            <div className="knowledge-page__eyebrow">工作区</div>
            <h1>知识库</h1>
            <p>先浏览所有知识库总览,再进入具体知识库管理其中的资料。只有启用中的知识库,才能在对话中被链接使用。</p>
          </div>
        </header>
      ) : null}

      {error ? <div className="knowledge-page__error">{error}</div> : null}

      {!selectedId ? (
        <>
          <section className="knowledge-page__summary">
            <article className="knowledge-page__metric">
              <span>知识库总数</span>
              <strong>{summary.baseCount}</strong>
            </article>
            <article className="knowledge-page__metric">
              <span>已启用知识库</span>
              <strong>{summary.enabledCount}</strong>
            </article>
            <article className="knowledge-page__metric">
              <span>资料总数</span>
              <strong>{summary.documentCount}</strong>
            </article>
            <article className="knowledge-page__metric">
              <span>最近更新</span>
              <strong>{formatDate(summary.latestUpdatedAt)}</strong>
            </article>
          </section>


          <div className="knowledge-page__workspace">
            <section className="knowledge-page__section">
              <div className="knowledge-page__section-head">
                <div>
                  <h2>全部知识库</h2>
                  <p>每个知识库都以卡片展示。启用后才能在聊天输入框下通过“链接知识库”按钮选择它。</p>
                </div>
                <button
                  type="button"
                  className="knowledge-page__button"
                  onClick={() => setShowCreate(true)}
                >
                  + 新建知识库
                </button>
              </div>

              {loading ? (
                <CardGridSkeleton count={6} />
              ) : items.length === 0 ? (
                <div className="knowledge-page__empty">
                  还没有知识库。先创建一个库，再往里面添加 PDF、Word、PPT、Markdown 或文本文档。
                </div>
              ) : (
                <div className="knowledge-page__grid">
                  {items.map((item) => (
                    <article
                      key={item.id}
                      className={`knowledge-card ${item.enabled ? 'is-enabled' : 'is-disabled'}`}
                    >
                      <div className="knowledge-card__head">
                        <div>
                          <strong>{item.name}</strong>
                          <span className={`knowledge-page__type-badge knowledge-page__type-badge--${item.type}`}>
                            {item.type === 'wiki' ? 'Wiki' : 'RAG'}
                          </span>
                          <div className="knowledge-card__pill-row">
                            <span className={`knowledge-card__status is-${item.status}`}>{item.status}</span>
                            <span className={`knowledge-card__enabled ${item.enabled ? 'is-on' : 'is-off'}`}>
                              {item.enabled ? '已启用' : '未启用'}
                            </span>
                          </div>
                        </div>

                        <button
                          type="button"
                          className={`knowledge-card__toggle ${item.enabled ? 'is-on' : ''}`}
                          onClick={() => void handleToggleEnabled(item.id, !item.enabled)}
                          disabled={updatingBaseId === item.id}
                          aria-label={`${item.enabled ? '停用' : '启用'} ${item.name}`}
                        >
                          <span />
                        </button>
                      </div>

                      <p>{item.description || '这个知识库还没有填写简介。'}</p>

                      <div className="knowledge-card__meta">
                        <span>
                          {item.type === 'wiki'
                            ? `${item.source_count} 份素材 · ${item.page_count} 页 · ${item.entity_count + item.topic_count} 概念`
                            : `${item.document_count} 份资料`}
                        </span>
                        <span>{formatDate(item.updated_at)}</span>
                      </div>

                      <div className="knowledge-card__actions">
                        <button
                          type="button"
                          className="knowledge-page__button knowledge-page__button--ghost"
                          onClick={() => setSelectedId(item.id)}
                        >
                          进入知识库
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      ) : (
        <section className="kb-detail">
          {detailLoading && !detail ? (
            <div style={{ padding: '24px' }}>
              <ListSkeleton count={5} />
            </div>
          ) : detail ? (
            (() => {
              const kb = detail.knowledge_base;
              const wiki = isWikiKb(kb);
              return (
                <>
                  <header className="kb-detail__topbar">
                    <button
                      type="button"
                      className="kb-detail__back"
                      onClick={() => {
                        setSelectedId(null);
                        setInfoPopoverOpen(false);
                      }}
                      aria-label="返回总览"
                    >
                      ←
                    </button>
                    <span
                      className={`knowledge-page__type-badge knowledge-page__type-badge--${kb.type}`}
                    >
                      {wiki ? 'Wiki' : 'RAG'}
                    </span>
                    <div className="kb-detail__title-wrap">
                      <h1 className="kb-detail__title">{kb.name}</h1>
                      {kb.description ? (
                        <p className="kb-detail__desc">{kb.description}</p>
                      ) : null}
                    </div>
                    <div className="kb-detail__actions">
                      <button
                        type="button"
                        className="kb-detail__icon-button"
                        onClick={() => setRenameDialog({ id: kb.id, name: kb.name })}
                        disabled={renamingBaseId === kb.id || deletingBaseId === kb.id}
                        title="重命名"
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        className="kb-detail__icon-button is-danger"
                        onClick={() => setDeleteKbDialog({ id: kb.id, name: kb.name })}
                        disabled={deletingBaseId === kb.id || renamingBaseId === kb.id}
                        title="删除知识库"
                      >
                        删除
                      </button>
                      <div className="kb-detail__info-anchor">
                        <button
                          type="button"
                          className={`kb-detail__icon-button ${infoPopoverOpen ? 'is-active' : ''}`}
                          onClick={() => setInfoPopoverOpen((v) => !v)}
                          aria-haspopup="dialog"
                          aria-expanded={infoPopoverOpen}
                          title="知识库状态"
                        >
                          状态 ⓘ
                        </button>
                        {infoPopoverOpen ? (
                          <>
                            <div
                              className="kb-detail__info-veil"
                              onClick={() => setInfoPopoverOpen(false)}
                            />
                            <div
                              className="kb-detail__info-popover"
                              role="dialog"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <div className="kb-detail__info-row">
                                <span>知识库状态</span>
                                <strong>{kb.status}</strong>
                              </div>
                              <div className="kb-detail__info-row">
                                <span>{wiki ? '激活权限' : '链接权限'}</span>
                                <strong>{kb.enabled ? '已启用' : '未启用'}</strong>
                              </div>
                              {wiki ? (
                                <>
                                  <div className="kb-detail__info-row">
                                    <span>素材 / 页面</span>
                                    <strong>
                                      {kb.source_count} / {kb.page_count}
                                    </strong>
                                  </div>
                                  <div className="kb-detail__info-row">
                                    <span>实体 / 主题</span>
                                    <strong>
                                      {kb.entity_count} / {kb.topic_count}
                                    </strong>
                                  </div>
                                  <div className="kb-detail__info-row">
                                    <span>页面链接</span>
                                    <strong>{kb.link_count}</strong>
                                  </div>
                                </>
                              ) : (
                                <div className="kb-detail__info-row">
                                  <span>资料数量</span>
                                  <strong>{detail.documents.length}</strong>
                                </div>
                              )}
                              <div className="kb-detail__info-row">
                                <span>最后更新</span>
                                <strong>{formatDate(kb.updated_at)}</strong>
                              </div>
                              <button
                                type="button"
                                className={`kb-detail__toggle ${kb.enabled ? 'is-on' : ''}`}
                                onClick={() =>
                                  void handleToggleEnabled(kb.id, !kb.enabled)
                                }
                                disabled={updatingBaseId === kb.id}
                              >
                                {kb.enabled ? '停用知识库' : '启用知识库'}
                              </button>
                            </div>
                          </>
                        ) : null}
                      </div>
                    </div>
                  </header>

                  <div className="kb-detail__toolbar">
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="knowledge-panel__file-input"
                      onChange={(event) => {
                        void runUploadWithPipelineProgress(event.target.files);
                        event.target.value = '';
                      }}
                    />
                    <button
                      type="button"
                      className="kb-detail__primary-button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploadingDocuments}
                    >
                      上传资料
                    </button>
                    {wiki ? (
                      <button
                        type="button"
                        className="kb-detail__secondary-button"
                        onClick={() => setShowAddUrlFor(kb.id)}
                        disabled={isUploadingDocuments}
                        title="抓取微信公众号文章"
                      >
                        + 链接抓取
                      </button>
                    ) : null}
                  </div>

                  {isUploadingDocuments && uploadProgress ? (
                    <div className="kb-detail__progress">
                      <div className="kb-detail__progress-meta">
                        <span>
                          {wiki ? '正在编译 ' : '正在上传 '}
                          {uploadingCount} 份资料 · {formatFileSize(uploadProgress.loaded)} /{' '}
                          {formatFileSize(uploadProgress.total)}
                        </span>
                        <strong>{uploadProgress.percent}%</strong>
                      </div>
                      <div className="kb-detail__progress-track">
                        <div
                          className="kb-detail__progress-fill"
                          style={{ width: `${uploadProgress.percent}%` }}
                        />
                      </div>
                    </div>
                  ) : null}

                  <div className="kb-detail__body">
                    {wiki ? (
                      <WikiKbDetail
                        kb={kb}
                        documents={detail.documents}
                        onDeleteDocument={(documentId) => {
                          const doc = detail.documents.find((d) => d.id === documentId);
                          requestDeleteDocument(documentId, doc?.name ?? '该素材');
                        }}
                      />
                    ) : detail.documents.length === 0 ? (
                      <div className="knowledge-page__empty is-inline">
                        这个知识库里还没有资料。先上传几份资料,后面聊天时就能通过"链接知识库"手动调用它。
                      </div>
                    ) : (
                      <div className="knowledge-document-list">
                        {detail.documents.map((document) => (
                          <div key={document.id} className="knowledge-document">
                            <div className="knowledge-document__top">
                              <div className="knowledge-document__main">
                                <strong>{document.name}</strong>
                                <p>{document.path}</p>
                              </div>
                              <button
                                type="button"
                                className="knowledge-document__delete"
                                onClick={() => requestDeleteDocument(document.id, document.name)}
                              >
                                删除
                              </button>
                            </div>
                            <div className="knowledge-document__meta">
                              <span>{document.file_type.toUpperCase() || 'FILE'}</span>
                              <span>{document.chunk_count} chunks</span>
                              <span>{document.status}</span>
                            </div>
                            {document.status === 'failed' && document.error_message ? (
                              <div className="knowledge-document__error" title={document.error_message}>
                                {document.error_message}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              );
            })()
          ) : null}
        </section>
      )}

      {showCreate ? (
        <CreateKnowledgeBaseModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      ) : null}

      {showAddUrlFor ? (
        <AddUrlSourceModal
          knowledgeBaseId={showAddUrlFor}
          onClose={() => setShowAddUrlFor(null)}
          onAdded={(doc) => {
            void handleUrlSourceAdded(showAddUrlFor, doc.id);
          }}
        />
      ) : null}

      {renameDialog ? (
        <RenameKnowledgeBaseModal
          currentName={renameDialog.name}
          onClose={() => setRenameDialog(null)}
          onSubmit={(nextName) => submitRenameKnowledgeBase(renameDialog.id, nextName)}
        />
      ) : null}

      {deleteKbDialog ? (
        <ConfirmModal
          title="删除知识库"
          danger
          confirmLabel="确认删除"
          message={
            <>
              确认删除知识库 <strong>{deleteKbDialog.name}</strong>?
              <br />
              <em>其中所有资料、Wiki 页面和索引都会被一并移除,无法恢复。</em>
            </>
          }
          onClose={() => setDeleteKbDialog(null)}
          onConfirm={() => submitDeleteKnowledgeBase(deleteKbDialog.id)}
        />
      ) : null}

      {deleteDocDialog ? (
        <ConfirmModal
          title="删除资料"
          danger
          confirmLabel="确认删除"
          message={
            <>
              确认从当前知识库中删除 <strong>{deleteDocDialog.name}</strong>?
              <br />
              <em>该素材的源页面、对应实体/主题(若仅此素材引用)将一同清理,无法恢复。</em>
            </>
          }
          onClose={() => setDeleteDocDialog(null)}
          onConfirm={() => submitDeleteDocument(deleteDocDialog.id)}
        />
      ) : null}
    </section>
  );
};
