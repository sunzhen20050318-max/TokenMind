import React, { useEffect, useMemo, useState } from 'react';
import { CloseIcon } from '../components/CloseIcon';
import { api } from '../services/api';
import { CardGridSkeleton, ListSkeleton } from '../components/Skeleton/Skeleton';
import type { StorageFileItem, StorageOverviewResponse } from '../types/storage';
import { useChatStore } from '../stores/chatStore';
import './storage.css';

type FilterMode = 'all' | 'referenced' | 'orphan';

interface NoticeState {
  tone: 'success' | 'error';
  text: string;
}

interface StorageModalProps {
  onClose: () => void;
}

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
  const [detailsOpen, setDetailsOpen] = useState(false);

  const loadData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await api.getStorageOverview();
      setOverview(response);
      if (!silent) setNotice(null);
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
    if (!overview) return [];
    const normalizedQuery = query.trim().toLowerCase();
    return overview.files.filter((file) => {
      if (filterMode === 'referenced' && !file.referenced) return false;
      if (filterMode === 'orphan' && file.referenced) return false;
      if (!normalizedQuery) return true;
      const haystack = `${file.name} ${file.path} ${file.category} ${file.referenced_by
        .map((item) => item.title)
        .join(' ')}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [filterMode, overview, query]);

  const usagePercent = useMemo(() => {
    if (!overview || overview.summary.quota_bytes <= 0) return 0;
    return Math.min(
      100,
      Math.round((overview.summary.used_bytes / overview.summary.quota_bytes) * 100),
    );
  }, [overview]);

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

  const renderBody = () => {
    if (loading || !overview) {
      return (
        <div className="storage-loading">
          <CardGridSkeleton count={4} />
          <ListSkeleton count={5} />
        </div>
      );
    }

    const cleanupBusy = actionPath === '__cleanup__';

    return (
      <>
        {/* Top status bar — one chip-style row with usage + cleanup */}
        <section className="storage-statusbar">
          <div className="storage-statusbar__usage">
            <div className="storage-statusbar__usage-line">
              <strong>{formatBytes(overview.summary.used_bytes)}</strong>
              <span className="storage-statusbar__usage-quota">
                / {formatBytes(overview.summary.quota_bytes)}
              </span>
              <span className="storage-statusbar__usage-percent">{usagePercent}%</span>
            </div>
            <div className="storage-statusbar__usage-bar">
              <div
                className="storage-statusbar__usage-fill"
                style={{ width: `${usagePercent}%` }}
              />
            </div>
          </div>

          <div className="storage-statusbar__facts">
            <div className="storage-statusbar__fact">
              <span>{overview.files.length}</span>
              <small>个文件</small>
            </div>
            <div className="storage-statusbar__fact">
              <span>{overview.summary.unreferenced_file_count}</span>
              <small>未引用</small>
            </div>
            <div className="storage-statusbar__fact">
              <span>{overview.summary.retention_days}</span>
              <small>天保留</small>
            </div>
          </div>

          <div className="storage-statusbar__actions">
            <button
              className="storage-secondary"
              onClick={() => setDetailsOpen((v) => !v)}
              type="button"
            >
              {detailsOpen ? '收起详情' : '更多详情'}
            </button>
            <button
              className="storage-primary"
              disabled={cleanupBusy}
              onClick={() => void handleCleanup()}
              type="button"
            >
              {cleanupBusy ? '正在清理' : '清理过期'}
            </button>
          </div>
        </section>

        {detailsOpen ? (
          <section className="storage-details">
            <div className="storage-details__row">
              <span>单文件上限</span>
              <strong>{formatBytes(overview.summary.max_file_bytes)}</strong>
            </div>
            <div className="storage-details__row">
              <span>检查间隔</span>
              <strong>每 {overview.summary.cleanup_interval_hours} 小时</strong>
            </div>
            <div className="storage-details__row">
              <span>已引用文件</span>
              <strong>{overview.summary.referenced_file_count} 个</strong>
            </div>
            <div className="storage-details__row">
              <span>待清理孤立</span>
              <strong>{overview.summary.stale_unreferenced_file_count} 个</strong>
            </div>
            <div className="storage-details__row">
              <span>剩余可用</span>
              <strong>{formatBytes(overview.summary.available_bytes)}</strong>
            </div>
          </section>
        ) : null}

        {/* Filter + search row */}
        <div className="storage-toolbar">
          <div className="storage-filters">
            {(
              [
                ['all', '全部'],
                ['referenced', '已引用'],
                ['orphan', '未引用'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={`storage-filter ${filterMode === value ? 'is-active' : ''}`}
                onClick={() => setFilterMode(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <input
            className="storage-search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索文件名 / 路径 / 会话"
            type="search"
            value={query}
          />
          <span className="storage-toolbar__count">{filteredFiles.length} 个结果</span>
        </div>

        {/* File list */}
        {filteredFiles.length === 0 ? (
          <div className="storage-empty">
            {query.trim() || filterMode !== 'all'
              ? '没有匹配当前筛选条件的文件。'
              : '工作区还没有上传文件。'}
          </div>
        ) : (
          <div className="storage-list">
            {filteredFiles.map((file) => (
              <article className="storage-row" key={file.path}>
                <div className="storage-row__main">
                  <div className="storage-row__name">{file.name}</div>
                  <div className="storage-row__path">{file.path}</div>
                  <div className="storage-row__chips">
                    <span className="storage-chip">{badgeLabel(file)}</span>
                    <span className={`storage-chip ${file.referenced ? 'is-referenced' : 'is-orphan'}`}>
                      {file.referenced ? `已引用 ${file.reference_count}` : '未引用'}
                    </span>
                    <span className="storage-chip">{formatBytes(file.size)}</span>
                    <span className="storage-chip">{formatDate(file.modified_at)}</span>
                  </div>
                  {file.referenced_by.length > 0 ? (
                    <div className="storage-row__refs">
                      {file.referenced_by.map((reference) => (
                        <button
                          key={`${file.path}-${reference.session_id}`}
                          className="storage-ref"
                          onClick={() => {
                            setCurrentSession(reference.session_id);
                            onClose();
                          }}
                          type="button"
                          title={`跳转到会话 ${reference.title}`}
                        >
                          {reference.title}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="storage-row__actions">
                  <button
                    className="storage-danger"
                    disabled={!file.can_delete || actionPath === file.path}
                    onClick={() => void handleDelete(file)}
                    type="button"
                    title={
                      file.can_delete
                        ? '删除文件'
                        : '该文件仍被会话引用，需先解除引用'
                    }
                  >
                    {actionPath === file.path ? '删除中' : '删除'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </>
    );
  };

  return (
    <div
      className="storage-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="storage-modal" onClick={(event) => event.stopPropagation()}>
        <header className="storage-header">
          <h1>文件中心</h1>
          <div className="storage-header__actions">
            <button className="storage-secondary" onClick={() => void loadData()} type="button">
              刷新
            </button>
            <button
              aria-label="关闭文件中心"
              className="storage-close"
              onClick={onClose}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
        </header>

        <main className="storage-content">
          {notice ? <div className={`storage-notice ${notice.tone}`}>{notice.text}</div> : null}
          {renderBody()}
        </main>
      </div>
    </div>
  );
};
