import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../services/api';
import { CreateKnowledgeBaseModal } from '../components/Knowledge/CreateKnowledgeBaseModal';
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
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
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

  const handleRenameKnowledgeBase = async (knowledgeBaseId: string, currentName: string) => {
    const nextName = window.prompt('重命名知识库', currentName)?.trim();
    if (!nextName || nextName === currentName.trim()) {
      return;
    }

    try {
      setRenamingBaseId(knowledgeBaseId);
      setError(null);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : '重命名知识库失败');
    } finally {
      setRenamingBaseId(null);
    }
  };

  const handleDeleteKnowledgeBase = async (knowledgeBaseId: string, name: string) => {
    const confirmed = window.confirm(`确定删除知识库“${name}”吗？其中所有资料和索引都会被移除。`);
    if (!confirmed) {
      return;
    }

    try {
      setDeletingBaseId(knowledgeBaseId);
      setError(null);
      await api.deleteKnowledgeBase(knowledgeBaseId);
      if (selectedId === knowledgeBaseId) {
        setSelectedId(null);
        setDetail(null);
      }
      await loadOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除知识库失败');
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

  const trackProcessingProgress = useCallback(
    async (knowledgeBaseId: string, documentIds: string[]) => {
      const runId = ++uploadPollRef.current;
      setUploadPhase('processing');
      setUploadStageLabel('正在准备入库');

      while (uploadPollRef.current === runId) {
        const payload = await refreshDetail(knowledgeBaseId);
        const summary = buildProcessingSummary(payload.documents, documentIds);
        if (!summary) {
          break;
        }

        setUploadingCount(summary.totalCount);
        setUploadStageLabel(summary.stageLabel);
        setUploadProgress({
          loaded: summary.averageProgress,
          total: 100,
          percent: Math.max(45, Math.min(100, 45 + Math.round(summary.averageProgress * 0.55))),
        });

        const allFinished = summary.readyCount + summary.failedCount === summary.totalCount;
        if (allFinished) {
          if (summary.failedCount > 0) {
            setError('部分知识库资料处理失败，请在资料列表中查看详情。');
          }
          break;
        }

        await new Promise((resolve) => window.setTimeout(resolve, 700));
      }

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
    [loadOverview, refreshDetail]
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
        setError(err instanceof Error ? err.message : '涓婁紶璧勬枡澶辫触');
        setIsUploadingDocuments(false);
        setUploadingCount(0);
        setUploadPhase(null);
        setUploadStageLabel('');
        setUploadProgress(null);
      }
    },
    [loadOverview, selectedId, trackProcessingProgress]
  );

  const handleDeleteDocument = async (documentId: string) => {
    if (!selectedId) {
      return;
    }
    try {
      setError(null);
      await api.deleteKnowledgeDocument(selectedId, documentId);
      await Promise.all([loadOverview(), loadDetail(selectedId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除资料失败');
    }
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
    <section className="knowledge-page">
      <header className="knowledge-page__header">
        <div>
          <div className="knowledge-page__eyebrow">工作区</div>
          <h1>知识库</h1>
          <p>先浏览所有知识库总览，再进入具体知识库管理其中的资料。只有启用中的知识库，才能在对话中被链接使用。</p>
        </div>

        <div className="knowledge-page__header-actions">
          {selectedId ? (
            <button
              type="button"
              className="knowledge-page__button knowledge-page__button--ghost"
              onClick={() => setSelectedId(null)}
            >
              返回总览
            </button>
          ) : null}
          <button
            type="button"
            className="knowledge-page__button"
            onClick={() => setShowCreate(true)}
          >
            + 新建知识库
          </button>
        </div>
      </header>

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
                <div className="knowledge-page__empty">正在加载知识库…</div>
              ) : items.length === 0 ? (
                <div className="knowledge-page__empty">
                  还没有知识库。先创建一个库，再往里面添加 PDF、Markdown、表格、图片或演示文档。
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
                        <span>{item.document_count} 份资料</span>
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
        <section className="knowledge-page__detail">
          {detailLoading && !detail ? (
            <div className="knowledge-page__empty">正在加载知识库详情…</div>
          ) : detail ? (
            <>
              <div className="knowledge-page__detail-head">
                <div>
                  <div className="knowledge-page__eyebrow">知识库详情</div>
                  <h2>{detail.knowledge_base.name}</h2>
                  <p>{detail.knowledge_base.description || '这个知识库还没有简介。'}</p>
                </div>
                <div className="knowledge-page__detail-meta">
                  <span>{detail.documents.length} 份资料</span>
                  <span>{formatDate(detail.knowledge_base.updated_at)}</span>
                </div>
              </div>

              <div className="knowledge-page__header-actions knowledge-page__header-actions--detail">
                <button
                  type="button"
                  className="knowledge-page__button knowledge-page__button--ghost"
                  onClick={() =>
                    void handleRenameKnowledgeBase(detail.knowledge_base.id, detail.knowledge_base.name)
                  }
                  disabled={
                    renamingBaseId === detail.knowledge_base.id || deletingBaseId === detail.knowledge_base.id
                  }
                >
                  重命名
                </button>
                <button
                  type="button"
                  className="knowledge-page__button knowledge-page__button--ghost is-danger"
                  onClick={() =>
                    void handleDeleteKnowledgeBase(detail.knowledge_base.id, detail.knowledge_base.name)
                  }
                  disabled={
                    deletingBaseId === detail.knowledge_base.id || renamingBaseId === detail.knowledge_base.id
                  }
                >
                  删除知识库
                </button>
              </div>

              <div className="knowledge-page__detail-layout">
                <article className="knowledge-panel">
                  <div className="knowledge-panel__head">
                    <div>
                      <h3>资料列表</h3>
                      <p>一个知识库里可以放不同格式的资料，启用后会统一参与当前会话的检索参考。</p>
                    </div>
                    <div className="knowledge-panel__actions">
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
                        className="knowledge-page__button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploadingDocuments}
                      >
                        上传资料
                      </button>
                    </div>
                  </div>

                  {isUploadingDocuments && uploadProgress ? (
                    <div className="knowledge-upload-progress">
                      <div className="knowledge-upload-progress__meta">
                        <span>
                          正在上传 {uploadingCount} 份资料 · {formatFileSize(uploadProgress.loaded)} /{' '}
                          {formatFileSize(uploadProgress.total)}
                        </span>
                        <strong>{uploadProgress.percent}%</strong>
                      </div>
                      <div className="knowledge-upload-progress__track">
                        <div
                          className="knowledge-upload-progress__fill"
                          style={{ width: `${uploadProgress.percent}%` }}
                        />
                      </div>
                    </div>
                  ) : null}

                  {detail.documents.length === 0 ? (
                    <div className="knowledge-page__empty is-inline">
                      这个知识库里还没有资料。先上传几份资料，后面聊天时就能通过“链接知识库”手动调用它。
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
                              onClick={() => {
                                void handleDeleteDocument(document.id);
                              }}
                            >
                              删除
                            </button>
                          </div>
                          <div className="knowledge-document__meta">
                            <span>{document.file_type.toUpperCase() || 'FILE'}</span>
                            <span>{document.chunk_count} chunks</span>
                            <span>{document.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </article>

                <div className="knowledge-page__sidebar">
                  <aside className="knowledge-panel knowledge-panel--side">
                    <div className="knowledge-panel__head">
                      <div>
                        <h3>当前状态</h3>
                        <p>这里帮助你快速判断这个知识库是否已经准备好被聊天会话链接使用。</p>
                      </div>
                    </div>

                    <div className="knowledge-state-list">
                      <div className="knowledge-state-list__row">
                        <span>知识库状态</span>
                        <strong>{detail.knowledge_base.status}</strong>
                      </div>
                      <div className="knowledge-state-list__row">
                        <span>链接权限</span>
                        <strong>{detail.knowledge_base.enabled ? '已启用' : '未启用'}</strong>
                      </div>
                      <div className="knowledge-state-list__row">
                        <span>资料数量</span>
                        <strong>{detail.documents.length}</strong>
                      </div>
                      <div className="knowledge-state-list__row">
                        <span>最后更新</span>
                        <strong>{formatDate(detail.knowledge_base.updated_at)}</strong>
                      </div>
                    </div>

                    <button
                      type="button"
                      className={`knowledge-page__button knowledge-page__button--toggle ${detail.knowledge_base.enabled ? 'is-on' : ''}`}
                      onClick={() =>
                        void handleToggleEnabled(detail.knowledge_base.id, !detail.knowledge_base.enabled)
                      }
                      disabled={updatingBaseId === detail.knowledge_base.id}
                    >
                      {detail.knowledge_base.enabled ? '停用当前知识库' : '启用当前知识库'}
                    </button>
                  </aside>
                </div>
              </div>
            </>
          ) : null}
        </section>
      )}

      {showCreate ? (
        <CreateKnowledgeBaseModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      ) : null}
    </section>
  );
};
