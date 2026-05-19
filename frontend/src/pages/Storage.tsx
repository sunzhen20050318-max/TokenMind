import React, { useEffect, useMemo, useState } from 'react';
import { BrandMark } from '../components/BrandMark';
import { CloseIcon } from '../components/CloseIcon';
import { api } from '../services/api';
import { CardGridSkeleton, ListSkeleton } from '../components/Skeleton/Skeleton';
import type { StorageFileItem, StorageOverviewResponse } from '../types/storage';
import { useChatStore } from '../stores/chatStore';
import './storage.css';

type FilterMode = 'all' | 'referenced' | 'orphan';
type StorageSection = 'overview' | 'files' | 'cleanup' | 'quota';

interface NoticeState {
  tone: 'success' | 'error';
  text: string;
}

interface StorageModalProps {
  onClose: () => void;
}

const STORAGE_SECTION_META: Array<{
  id: StorageSection;
  title: string;
  copy: string;
}> = [
  { id: 'overview', title: '概览', copy: '查看存储占用、配额和未清理文件的整体状态。' },
  { id: 'files', title: '文件列表', copy: '按引用状态筛选上传文件，并快速跳回引用会话。' },
  { id: 'cleanup', title: '清理策略', copy: '了解保留天数、自动清理周期和手动清理动作。' },
  { id: 'quota', title: '配额说明', copy: '查看单文件上限、总配额和当前可用空间。' },
];

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / 1024 ** exponent;
  return `${value >= 100 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function badgeLabel(file: StorageFileItem): string {
  if (file.category === 'markdown') return 'Markdown';
  if (file.category === 'spreadsheet') return '表格';
  if (file.category === 'presentation') return '演示';
  if (file.category === 'pdf') return 'PDF';
  if (file.category === 'image') return '图片';
  if (file.category === 'text') return '文本';
  return '文件';
}

export const StorageModal: React.FC<StorageModalProps> = ({ onClose }) => {
  const { setCurrentSession } = useChatStore();
  const [overview, setOverview] = useState<StorageOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [query, setQuery] = useState('');
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const [actionPath, setActionPath] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<StorageSection>('overview');

  const loadData = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const response = await api.getStorageOverview();
      setOverview(response);
      if (!silent) {
        setNotice(null);
      }
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '加载文件中心失败',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredFiles = useMemo(() => {
    if (!overview) {
      return [];
    }
    const normalizedQuery = query.trim().toLowerCase();
    return overview.files.filter((file) => {
      if (filterMode === 'referenced' && !file.referenced) {
        return false;
      }
      if (filterMode === 'orphan' && file.referenced) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      const haystack = `${file.name} ${file.path} ${file.category} ${file.referenced_by
        .map((item) => item.title)
        .join(' ')}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [filterMode, overview, query]);

  const usagePercent = useMemo(() => {
    if (!overview || overview.summary.quota_bytes <= 0) {
      return 0;
    }
    return Math.min(100, Math.round((overview.summary.used_bytes / overview.summary.quota_bytes) * 100));
  }, [overview]);

  const currentSectionMeta =
    STORAGE_SECTION_META.find((section) => section.id === selectedSection) || STORAGE_SECTION_META[0];

  const navigateTo = (section: StorageSection) => {
    setSelectedSection(section);
    window.requestAnimationFrame(() => {
      document
        .getElementById(`storage-section-${section}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const handleCleanup = async () => {
    setActionPath('__cleanup__');
    try {
      const result = await api.cleanupStorage();
      await loadData(true);
      setNotice({
        tone: 'success',
        text: `清理完成，删除了 ${result.deleted_files} 个文件和 ${result.deleted_dirs} 个空目录`,
      });
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '清理文件失败',
      });
    } finally {
      setActionPath(null);
    }
  };

  const handleDelete = async (file: StorageFileItem) => {
    setActionPath(file.path);
    try {
      const result = await api.deleteStoredFile(file.path);
      await loadData(true);
      setNotice({
        tone: 'success',
        text: `已删除 ${file.name}，释放 ${formatBytes(result.deleted_bytes)}`,
      });
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '删除文件失败',
      });
    } finally {
      setActionPath(null);
    }
  };

  return (
    <div
      className="storage-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="storage-modal" onClick={(event) => event.stopPropagation()}>
        <aside className="storage-sidebar">
          <div className="storage-profile-card">
            <div className="storage-profile-card__avatar">
              <BrandMark size={18} alt="TokenMind 标志" variant="icon" />
            </div>
            <div className="storage-profile-card__body">
              <div className="storage-profile-card__name">TokenMind</div>
              <div className="storage-profile-card__role">文件中心</div>
            </div>
            <div className="storage-profile-card__chevron" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M5.5 3.5 10 8l-4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div className="storage-sidebar-divider" />

          <div className="storage-sidebar-group-label">文件视图</div>

          <nav className="storage-nav">
            {STORAGE_SECTION_META.map((section) => (
              <button
                key={section.id}
                className={`storage-nav-button ${selectedSection === section.id ? 'is-active' : ''}`}
                onClick={() => navigateTo(section.id)}
                type="button"
              >
                <span className="storage-nav-title">{section.title}</span>
                <span className="storage-nav-copy">{section.copy}</span>
              </button>
            ))}
          </nav>

          <button className="storage-sidebar-help" type="button">
            <span>了解存储规则</span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M6 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10.5 5.5 4.5 11.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </aside>

        <section className="storage-main">
          <header className="storage-header">
            <h2>{currentSectionMeta.title}</h2>
            <div className="storage-header-actions">
              <button className="storage-secondary" onClick={() => void loadData()} type="button">
                刷新
              </button>
              <button aria-label="关闭文件中心" className="storage-close" onClick={onClose} type="button">
                <CloseIcon />
              </button>
            </div>
          </header>

          <div className="storage-content">
          {notice ? <div className={`storage-notice ${notice.tone}`}>{notice.text}</div> : null}

          {loading || !overview ? (
            <div className="storage-loading">
              <CardGridSkeleton count={4} />
              <ListSkeleton count={5} />
            </div>
          ) : (
            <>
              <section className="storage-metrics" id="storage-section-overview">
                <div className="storage-metric-card">
                  <div className="storage-metric-label">已用空间</div>
                  <div className="storage-metric-value">{formatBytes(overview.summary.used_bytes)}</div>
                </div>
                <div className="storage-metric-card">
                  <div className="storage-metric-label">总配额</div>
                  <div className="storage-metric-value">{formatBytes(overview.summary.quota_bytes)}</div>
                </div>
                <div className="storage-metric-card">
                  <div className="storage-metric-label">单文件上限</div>
                  <div className="storage-metric-value">{formatBytes(overview.summary.max_file_bytes)}</div>
                </div>
                <div className="storage-metric-card">
                  <div className="storage-metric-label">待清理孤立文件</div>
                  <div className="storage-metric-value">{overview.summary.stale_unreferenced_file_count} 个</div>
                </div>
              </section>

              <div className="storage-layout">
                <aside className="storage-side">
                  <section className="storage-panel" id="storage-section-quota">
                    <div className="storage-panel-head">
                      <h3>空间占用</h3>
                      <p>当前上传文件会保存在工作区，并按配置策略自动清理。</p>
                    </div>
                    <div className="storage-usage-row">
                      <strong>{usagePercent}%</strong>
                      <span>
                        {formatBytes(overview.summary.used_bytes)} / {formatBytes(overview.summary.quota_bytes)}
                      </span>
                    </div>
                    <div className="storage-usage-bar">
                      <div className="storage-usage-fill" style={{ width: `${usagePercent}%` }} />
                    </div>
                    <div className="storage-usage-note">
                      剩余 {formatBytes(overview.summary.available_bytes)} 可用空间
                    </div>
                  </section>

                  <section className="storage-panel" id="storage-section-cleanup">
                    <div className="storage-panel-head">
                      <h3>清理策略</h3>
                      <p>你可以在设置中心的工具分组里调整上传限制和保留策略。</p>
                    </div>
                    <div className="storage-facts">
                      <div className="storage-fact">
                        <span>保留天数</span>
                        <strong>{overview.summary.retention_days} 天</strong>
                      </div>
                      <div className="storage-fact">
                        <span>检查间隔</span>
                        <strong>{overview.summary.cleanup_interval_hours} 小时</strong>
                      </div>
                      <div className="storage-fact">
                        <span>已引用文件</span>
                        <strong>{overview.summary.referenced_file_count} 个</strong>
                      </div>
                      <div className="storage-fact">
                        <span>未引用文件</span>
                        <strong>{overview.summary.unreferenced_file_count} 个</strong>
                      </div>
                    </div>
                    <div className="storage-actions">
                      <button
                        className="storage-primary"
                        disabled={actionPath === '__cleanup__'}
                        onClick={() => void handleCleanup()}
                        type="button"
                      >
                        {actionPath === '__cleanup__' ? '正在清理' : '立即清理过期文件'}
                      </button>
                    </div>
                  </section>
                </aside>

                <section className="storage-main-panel" id="storage-section-files">
                  <div className="storage-panel-head storage-main-head">
                    <div>
                      <h3>上传文件列表</h3>
                      <p>可以按引用状态筛选，并快速跳转到引用它的会话。</p>
                    </div>
                    <div className="storage-filter-group">
                      {[
                        ['all', '全部'],
                        ['referenced', '已引用'],
                        ['orphan', '未引用'],
                      ].map(([value, label]) => (
                        <button
                          key={value}
                          className={`storage-filter-button ${filterMode === value ? 'active' : ''}`}
                          onClick={() => setFilterMode(value as FilterMode)}
                          type="button"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="storage-search-row">
                    <input
                      className="storage-search"
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="搜索文件名、路径或会话"
                      type="text"
                      value={query}
                    />
                    <div className="storage-list-count">{filteredFiles.length} 个结果</div>
                  </div>

                  {filteredFiles.length === 0 ? (
                    <div className="storage-empty">当前筛选条件下没有文件。</div>
                  ) : (
                    <div className="storage-file-list">
                      {filteredFiles.map((file) => (
                        <article className="storage-file-card" key={file.path}>
                          <div className="storage-file-top">
                            <div>
                              <div className="storage-file-name">{file.name}</div>
                              <div className="storage-file-meta">
                                <span className="storage-badge">{badgeLabel(file)}</span>
                                <span className={`storage-badge ${file.referenced ? 'active' : ''}`}>
                                  {file.referenced ? `已引用 ${file.reference_count} 次` : '未引用'}
                                </span>
                                <span className="storage-badge">{formatBytes(file.size)}</span>
                              </div>
                            </div>

                            <button
                              className={`storage-danger ${actionPath === file.path ? 'is-busy' : ''}`}
                              disabled={!file.can_delete || actionPath === file.path}
                              onClick={() => void handleDelete(file)}
                              type="button"
                              title={
                                actionPath === file.path
                                  ? '正在删除文件'
                                  : file.can_delete
                                    ? '删除文件'
                                    : '该文件仍被会话引用，暂时不能删除'
                              }
                            >
                              {actionPath === file.path ? '删除中' : '删除文件'}
                            </button>
                          </div>

                          <div className="storage-file-path">{file.path}</div>

                          <div className="storage-file-foot">
                            <span>更新于 {formatDate(file.modified_at)}</span>
                            <span>{file.can_delete ? '可直接删除' : '仍被会话引用，需先解除引用'}</span>
                          </div>

                          {file.referenced_by.length > 0 ? (
                            <div className="storage-reference-list">
                              {file.referenced_by.map((reference) => (
                                <button
                                  key={`${file.path}-${reference.session_id}`}
                                  className="storage-reference-pill"
                                  onClick={() => {
                                    setCurrentSession(reference.session_id);
                                    onClose();
                                  }}
                                  type="button"
                                >
                                  {reference.title}
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
        </div>
        </section>
      </div>
    </div>
  );
};
