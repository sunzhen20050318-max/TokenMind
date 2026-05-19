import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CloseIcon } from '../components/CloseIcon';
import { api } from '../services/api';
import { ListSkeleton } from '../components/Skeleton/Skeleton';
import type { MemoryOverviewResponse } from '../types/memory';
import './memory.css';

type MemorySection = 'long-term' | 'current-context' | 'archive' | 'settings';

interface NoticeState {
  tone: 'success' | 'error';
  text: string;
}

interface MemoryModalProps {
  onClose: () => void;
  currentSessionId: string | null;
}

const SECTION_META: Array<{
  id: MemorySection;
  title: string;
}> = [
  { id: 'long-term', title: '长期记忆' },
  { id: 'current-context', title: '当前上下文' },
  { id: 'archive', title: '近期归档' },
  { id: 'settings', title: '说明' },
];

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return '--';
  }
  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function relativeTime(value?: string | null): string {
  if (!value) return '从未保存';
  const ts = new Date(value).getTime();
  if (Number.isNaN(ts)) return '--';
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60) return '刚刚保存';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return formatTimestamp(value);
}

function roleLabel(role: string): string {
  if (role === 'user') return '用户';
  if (role === 'assistant') return 'TokenMind';
  if (role === 'tool') return '工具';
  return role;
}

function MemoryMarkdown({ content }: { content: string }) {
  return (
    <div className="memory-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} rel="noreferrer" target="_blank">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export const MemoryModal: React.FC<MemoryModalProps> = ({ onClose, currentSessionId }) => {
  const [selectedSection, setSelectedSection] = useState<MemorySection>('long-term');
  const [overview, setOverview] = useState<MemoryOverviewResponse | null>(null);
  const [draft, setDraft] = useState('');
  const [archiveQuery, setArchiveQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);

  const dirty = overview ? draft !== overview.long_term.content : false;

  const loadOverview = async (query = archiveQuery, syncDraft = false) => {
    setLoading(true);
    try {
      const response = await api.getMemoryOverview(currentSessionId, query);
      setOverview(response);
      if (syncDraft || !dirty) {
        setDraft(response.long_term.content);
      }
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '加载记忆中心失败',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadOverview(archiveQuery, !overview);
    }, overview ? 180 : 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archiveQuery, currentSessionId]);

  const longTermMeta = useMemo(
    () => ({
      characters: draft.length,
      lines: draft.split('\n').length,
    }),
    [draft],
  );

  const navigateTo = (section: MemorySection) => {
    if (section === selectedSection) {
      return;
    }
    if (dirty && !window.confirm('长期记忆还有未保存的修改，确定切换分区吗？')) {
      return;
    }
    setSelectedSection(section);
  };

  const handleClose = () => {
    if (dirty && !window.confirm('长期记忆还有未保存的修改，确定直接关闭吗？')) {
      return;
    }
    onClose();
  };

  const handleSave = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await api.updateLongTermMemory(draft);
      setOverview((current) =>
        current ? { ...current, long_term: updated } : current,
      );
      setDraft(updated.content);
      setNotice({ tone: 'success', text: '长期记忆已保存' });
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof Error ? error.message : '保存长期记忆失败',
      });
    } finally {
      setSaving(false);
    }
  };

  const renderLongTerm = () => {
    if (!overview) return null;
    return (
      <div className="memory-editor-wrap">
        <textarea
          className="memory-editor"
          onChange={(event) => setDraft(event.target.value)}
          placeholder="还没有长期记忆。可以在这里记录长期偏好、固定背景和重要事实。"
          spellCheck={false}
          value={draft}
        />
        <div className="memory-statusbar">
          <span className={`memory-statusbar__dot ${dirty ? 'is-dirty' : 'is-clean'}`} aria-hidden />
          <span className="memory-statusbar__label">
            {dirty ? '有未保存修改' : '已同步'}
          </span>
          <span className="memory-statusbar__sep">·</span>
          <span>{relativeTime(overview.long_term.updated_at)}</span>
          <span className="memory-statusbar__sep">·</span>
          <span>{longTermMeta.characters} 字 · {longTermMeta.lines} 行</span>
          {!overview.long_term.editable ? (
            <>
              <span className="memory-statusbar__sep">·</span>
              <span className="memory-statusbar__readonly">只读</span>
            </>
          ) : null}
          <div className="memory-statusbar__spacer" />
          <button
            className="memory-secondary"
            onClick={() => void loadOverview()}
            type="button"
          >
            刷新
          </button>
          <button
            className="memory-primary"
            disabled={!dirty || saving || !overview.long_term.editable}
            onClick={() => void handleSave()}
            type="button"
          >
            {saving ? '保存中' : '保存'}
          </button>
        </div>
      </div>
    );
  };

  const renderCurrentContext = () => {
    if (!overview) return null;
    const hasItems = overview.current_context.items.length > 0;
    return (
      <div className="memory-list-wrap">
        <div className="memory-list-head">
          <h3>当前会话上下文</h3>
          <p>
            {hasItems
              ? `当前查看的会话：${overview.current_context.session_label || overview.current_context.session_id}`
              : '还没有活动会话内容。开始一段对话后，这里会显示模型当前真正保留的近期消息。'}
          </p>
        </div>
        {hasItems ? (
          <div className="memory-list">
            {overview.current_context.items.map((item, index) => (
              <article className="memory-list-item" key={`${item.timestamp || index}-${index}`}>
                <div className="memory-list-item__meta">
                  <span className={`memory-tag memory-tag--${item.role}`}>{roleLabel(item.role)}</span>
                  <span className="memory-list-item__time">{formatTimestamp(item.timestamp)}</span>
                </div>
                <div className="memory-list-item__body">
                  <MemoryMarkdown content={item.content} />
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const renderArchive = () => {
    if (!overview) return null;
    const hasItems = overview.archive.items.length > 0;
    return (
      <div className="memory-list-wrap">
        <div className="memory-list-head memory-list-head--with-search">
          <div>
            <h3>近期归档</h3>
            <p>{overview.archive.total} 条已从主上下文挪出的片段，便于搜索和回顾。</p>
          </div>
          <input
            className="memory-search"
            onChange={(event) => setArchiveQuery(event.target.value)}
            placeholder="搜索归档内容"
            type="search"
            value={archiveQuery}
          />
        </div>
        {hasItems ? (
          <div className="memory-list">
            {overview.archive.items.map((item) => (
              <article className="memory-list-item" key={item.id}>
                <div className="memory-list-item__meta">
                  <span className="memory-tag">归档</span>
                  <span className="memory-list-item__time">{formatTimestamp(item.timestamp)}</span>
                </div>
                <div className="memory-list-item__body">
                  <MemoryMarkdown content={item.content} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="memory-empty">
            {archiveQuery.trim()
              ? '没有匹配当前关键词的归档内容。'
              : '还没有近期归档。等对话足够长被整理后，这里会出现归档片段。'}
          </div>
        )}
      </div>
    );
  };

  const renderSettings = () => {
    if (!overview) return null;
    return (
      <div className="memory-info-wrap">
        <div className="memory-info-row">
          <span className="memory-info-label">自动归档</span>
          <strong>{overview.settings.auto_consolidation ? '已启用' : '未启用'}</strong>
        </div>
        <div className="memory-info-row">
          <span className="memory-info-label">提示词模板</span>
          <strong>{overview.settings.template_enabled ? '已启用自定义' : '默认模板'}</strong>
        </div>
        <div className="memory-info-row">
          <span className="memory-info-label">长期记忆可编辑</span>
          <strong>{overview.settings.editable_long_term ? '是' : '否'}</strong>
        </div>
        <div className="memory-info-block">
          <h4>系统说明</h4>
          <p>{overview.settings.summary}</p>
        </div>
      </div>
    );
  };

  const renderSection = () => {
    if (loading || !overview) {
      return (
        <div className="memory-loading">
          <ListSkeleton count={4} />
        </div>
      );
    }
    switch (selectedSection) {
      case 'long-term':
        return renderLongTerm();
      case 'current-context':
        return renderCurrentContext();
      case 'archive':
        return renderArchive();
      case 'settings':
        return renderSettings();
      default:
        return null;
    }
  };

  return (
    <div
      className="memory-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          handleClose();
        }
      }}
    >
      <div className="memory-modal" onClick={(event) => event.stopPropagation()}>
        <header className="memory-header">
          <div className="memory-header__title">
            <h1>记忆中心</h1>
            <nav className="memory-tabs">
              {SECTION_META.map((section) => (
                <button
                  className={`memory-tab ${selectedSection === section.id ? 'is-active' : ''}`}
                  key={section.id}
                  onClick={() => navigateTo(section.id)}
                  type="button"
                >
                  {section.title}
                </button>
              ))}
            </nav>
          </div>
          <button
            aria-label="关闭记忆中心"
            className="memory-close"
            onClick={handleClose}
            type="button"
          >
            <CloseIcon />
          </button>
        </header>

        <main className="memory-content">
          {notice ? <div className={`memory-notice ${notice.tone}`}>{notice.text}</div> : null}
          {renderSection()}
        </main>
      </div>
    </div>
  );
};
