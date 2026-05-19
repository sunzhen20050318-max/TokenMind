import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BrandMark } from '../components/BrandMark';
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
  copy: string;
}> = [
  {
    id: 'long-term',
    title: '长期记忆',
    copy: '编辑跨会话保留的稳定事实、偏好和工作背景。',
  },
  {
    id: 'current-context',
    title: '当前上下文',
    copy: '查看当前会话里仍在参与推理的近期内容。',
  },
  {
    id: 'archive',
    title: '近期归档',
    copy: '浏览已经从主上下文移出的历史片段，并支持快速搜索。',
  },
  {
    id: 'settings',
    title: '记忆设置',
    copy: '了解当前记忆系统的工作方式和核心状态。',
  },
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

function countWords(content: string): number {
  return content
    .trim()
    .split(/\s+/)
    .filter(Boolean).length;
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

  const longTermMeta = useMemo(() => {
    return {
      characters: draft.length,
      words: countWords(draft),
    };
  }, [draft]);

  const currentSectionMeta =
    SECTION_META.find((section) => section.id === selectedSection) || SECTION_META[0];

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
        current
          ? {
              ...current,
              long_term: updated,
            }
          : current
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
    if (!overview) {
      return null;
    }

    return (
      <div className="memory-section">
        <section className="memory-card memory-card--editor">
          <div className="memory-card__head memory-card__head--spaced">
            <div>
              <h3>长期记忆文档</h3>
              <p>这里保存会跨会话沿用的稳定事实、偏好和上下文。你可以直接编辑并保存。</p>
            </div>
            <div className="memory-actions">
              <button className="memory-secondary" onClick={() => void loadOverview()} type="button">
                刷新
              </button>
              <button
                className="memory-primary"
                disabled={!dirty || saving || !overview.long_term.editable}
                onClick={() => void handleSave()}
                type="button"
              >
                {saving ? '保存中' : '保存长期记忆'}
              </button>
            </div>
          </div>

          <textarea
            className="memory-editor"
            onChange={(event) => setDraft(event.target.value)}
            placeholder="还没有长期记忆。你可以在这里记录长期偏好、固定背景和重要事实。"
            spellCheck={false}
            value={draft}
          />
        </section>

        <section className="memory-grid">
          <div className="memory-card">
            <div className="memory-card__head">
              <h3>编辑状态</h3>
              <p>随时查看当前草稿和已保存内容之间的状态差异。</p>
            </div>
            <div className="memory-facts">
              <div className="memory-fact">
                <span>保存状态</span>
                <strong>{dirty ? '有未保存修改' : '已同步'}</strong>
              </div>
              <div className="memory-fact">
                <span>可编辑</span>
                <strong>{overview.long_term.editable ? '是' : '否'}</strong>
              </div>
              <div className="memory-fact">
                <span>字符数</span>
                <strong>{longTermMeta.characters}</strong>
              </div>
              <div className="memory-fact">
                <span>词数</span>
                <strong>{longTermMeta.words}</strong>
              </div>
            </div>
          </div>

          <div className="memory-card">
            <div className="memory-card__head">
              <h3>最近更新时间</h3>
              <p>这里显示当前长期记忆文档最近一次落盘时间。</p>
            </div>
            <div className="memory-highlight">{formatTimestamp(overview.long_term.updated_at)}</div>
            <div className="memory-inline-note">
              如果你修改了内容但还没点击保存，这里的时间不会更新。
            </div>
          </div>
        </section>
      </div>
    );
  };

  const renderCurrentContext = () => {
    if (!overview) {
      return null;
    }

    const hasItems = overview.current_context.items.length > 0;

    return (
      <div className="memory-section">
        <section className="memory-card">
          <div className="memory-card__head">
            <h3>当前会话上下文</h3>
            <p className="memory-context-copy">
              这里展示的是当前会话中尚未归档、仍会参与推理的消息。
              <br />
              在默认配置下，它通常会接近整个当前会话，而不只是最后一两轮。
            </p>
            <p>
              {hasItems
                ? `当前正在查看的会话是 ${overview.current_context.session_label || overview.current_context.session_id}。`
                : '还没有活动会话内容进入当前上下文。开始一段对话后，这里会显示仍在参与推理的近期消息。'}
            </p>
          </div>

          {!hasItems ? (
            <div className="memory-empty">
              还没有活动会话。
              <br />
              等你发起一段对话后，这里会显示模型当前真正保留着的短期上下文。
            </div>
          ) : (
            <div className="memory-context-list">
              {overview.current_context.items.map((item, index) => (
                <article className="memory-context-item" key={`${item.timestamp || index}-${index}`}>
                  <div className="memory-context-item__top">
                    <span className="memory-badge active">{roleLabel(item.role)}</span>
                    <span className="memory-context-time">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <div className="memory-context-content">
                    <MemoryMarkdown content={item.content} />
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  };

  const renderArchive = () => {
    if (!overview) {
      return null;
    }

    return (
      <div className="memory-section">
        <section className="memory-card">
          <div className="memory-card__head memory-card__head--spaced">
            <div>
              <h3>近期归档</h3>
              <p>这里显示已经从主上下文挪出的历史片段，便于搜索和回顾。</p>
            </div>
            <div className="memory-badges">
              <span className="memory-badge">{overview.archive.total} 条结果</span>
              <span className="memory-badge">只读</span>
            </div>
          </div>

          <div className="memory-search-row">
            <input
              className="memory-search"
              onChange={(event) => setArchiveQuery(event.target.value)}
              placeholder="搜索归档内容"
              type="text"
              value={archiveQuery}
            />
          </div>

          {overview.archive.items.length === 0 ? (
            <div className="memory-empty">
              {archiveQuery.trim()
                ? '没有匹配当前关键词的归档内容。'
                : '还没有近期归档内容。等对话足够长并被整理后，这里会出现归档片段。'}
            </div>
          ) : (
            <div className="memory-archive-list">
              {overview.archive.items.map((item) => (
                <article className="memory-archive-item" key={item.id}>
                  <div className="memory-archive-item__head">
                    <span className="memory-badge active">归档片段</span>
                    <span className="memory-context-time">{formatTimestamp(item.timestamp)}</span>
                  </div>
                  <div className="memory-archive-content">
                    <MemoryMarkdown content={item.content} />
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  };

  const renderSettings = () => {
    if (!overview) {
      return null;
    }

    return (
      <div className="memory-section">
        <section className="memory-grid">
          <div className="memory-card">
            <div className="memory-card__head">
              <h3>记忆模式</h3>
              <p>这里展示记忆系统当前的关键运行状态，而不是全部配置项。</p>
            </div>
            <div className="memory-facts">
              <div className="memory-fact">
                <span>自动归档</span>
                <strong>{overview.settings.auto_consolidation ? '已启用' : '未启用'}</strong>
              </div>
              <div className="memory-fact">
                <span>模板状态</span>
                <strong>{overview.settings.template_enabled ? '已启用模板' : '默认模板'}</strong>
              </div>
              <div className="memory-fact">
                <span>长期记忆可编辑</span>
                <strong>{overview.settings.editable_long_term ? '是' : '否'}</strong>
              </div>
            </div>
          </div>

          <div className="memory-card">
            <div className="memory-card__head">
              <h3>系统说明</h3>
              <p>帮助你理解长期记忆、当前上下文和近期归档之间的关系。</p>
            </div>
            <div className="memory-summary">{overview.settings.summary}</div>
          </div>
        </section>
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
        <aside className="memory-sidebar">
          <div className="memory-profile-card">
            <div className="memory-profile-card__avatar">
              <BrandMark size={18} alt="TokenMind 标志" variant="icon" />
            </div>
            <div className="memory-profile-card__body">
              <div className="memory-profile-card__name">TokenMind</div>
              <div className="memory-profile-card__role">记忆中心</div>
            </div>
            <div className="memory-profile-card__chevron" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M5.5 3.5 10 8l-4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div className="memory-sidebar-divider" />

          <div className="memory-sidebar-group-label">记忆视图</div>

          <nav className="memory-nav">
            {SECTION_META.map((section) => (
              <button
                className={`memory-nav-button ${selectedSection === section.id ? 'is-active' : ''}`}
                key={section.id}
                onClick={() => navigateTo(section.id)}
                type="button"
              >
                <span className="memory-nav-title">{section.title}</span>
                <span className="memory-nav-copy">{section.copy}</span>
              </button>
            ))}
          </nav>

          <button className="memory-sidebar-help" type="button">
            <span>了解记忆规则</span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M6 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10.5 5.5 4.5 11.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </aside>

        <section className="memory-main">
          <header className="memory-header">
            <h1>{currentSectionMeta.title}</h1>
            <button aria-label="关闭记忆中心" className="memory-close" onClick={handleClose} type="button">
              <CloseIcon />
            </button>
          </header>

          <div className="memory-content">
            {notice ? <div className={`memory-notice ${notice.tone}`}>{notice.text}</div> : null}
            {renderSection()}
          </div>
        </section>
      </div>
    </div>
  );
};
