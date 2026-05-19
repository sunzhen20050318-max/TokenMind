import React, { useEffect, useRef, useState } from 'react';

import type { KnowledgeBase } from '../../types/knowledge';
import type { ComposerKnowledgeOption } from './InputArea';
import './knowledgeMenu.css';

interface KnowledgeMenuProps {
  ragOptions: ComposerKnowledgeOption[];
  linkedRagIds: string[];
  onUpdateLinkedRag: (ids: string[]) => void;
  wikiOptions: KnowledgeBase[];
  activeWikiId: string | null;
  onSetActiveWiki: (id: string | null) => void;
  disabled?: boolean;
}

export const KnowledgeMenu: React.FC<KnowledgeMenuProps> = ({
  ragOptions,
  linkedRagIds,
  onUpdateLinkedRag,
  wikiOptions,
  activeWikiId,
  onSetActiveWiki,
  disabled,
}) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', onClickOutside);
    window.addEventListener('keydown', onEsc);
    return () => {
      window.removeEventListener('mousedown', onClickOutside);
      window.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const activeWiki = wikiOptions.find((kb) => kb.id === activeWikiId) ?? null;
  const ragCount = linkedRagIds.length;
  const hasAny = !!activeWiki || ragCount > 0;

  const parts: string[] = [];
  if (activeWiki) parts.push(`Wiki: ${activeWiki.name}`);
  if (ragCount > 0) parts.push(`RAG · ${ragCount}`);
  const label = hasAny ? parts.join(' · ') : '知识库';

  const toggleRag = (id: string) => {
    const next = linkedRagIds.includes(id)
      ? linkedRagIds.filter((x) => x !== id)
      : [...linkedRagIds, id];
    onUpdateLinkedRag(next);
  };

  return (
    <div className="kb-menu" ref={wrapperRef}>
      <button
        type="button"
        className={`kb-menu__trigger ${open ? 'is-open' : ''} ${hasAny ? 'has-active' : ''}`}
        onClick={() => setOpen((s) => !s)}
        disabled={disabled}
        title={hasAny ? label : '链接知识库'}
      >
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
        <span>{label}</span>
      </button>

      {open && (
        <div className="kb-menu__panel" role="dialog">
          <div className="kb-menu__section">
            <div className="kb-menu__section-head">
              <strong>Wiki 知识库</strong>
              <span>单选 · LLM 主动浏览</span>
            </div>
            <button
              type="button"
              className={`kb-menu__row kb-menu__row--radio ${activeWikiId === null ? 'is-active' : ''}`}
              onClick={() => onSetActiveWiki(null)}
            >
              <span className="kb-menu__indicator kb-menu__indicator--radio" aria-hidden="true" />
              <span className="kb-menu__row-text">
                <span className="kb-menu__row-name">不激活</span>
                <span className="kb-menu__row-blurb">LLM 看不到任何 Wiki</span>
              </span>
            </button>
            {wikiOptions.length === 0 ? (
              <div className="kb-menu__empty">还没有启用的 Wiki 知识库</div>
            ) : (
              wikiOptions.map((kb) => (
                <button
                  key={kb.id}
                  type="button"
                  className={`kb-menu__row kb-menu__row--radio ${activeWikiId === kb.id ? 'is-active' : ''}`}
                  onClick={() => onSetActiveWiki(kb.id)}
                >
                  <span className="kb-menu__indicator kb-menu__indicator--radio" aria-hidden="true" />
                  <span className="kb-menu__row-text">
                    <span className="kb-menu__row-name">{kb.name}</span>
                    <span className="kb-menu__row-blurb">
                      {kb.entity_count} 实体 · {kb.topic_count} 主题 · {kb.source_count} 素材
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="kb-menu__divider" />

          <div className="kb-menu__section">
            <div className="kb-menu__section-head">
              <strong>RAG 检索库</strong>
              <span>多选 · 自动注入相关片段</span>
            </div>
            {ragOptions.length === 0 ? (
              <div className="kb-menu__empty">还没有启用的 RAG 知识库</div>
            ) : (
              ragOptions.map((opt) => {
                const selected = linkedRagIds.includes(opt.id);
                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`kb-menu__row kb-menu__row--check ${selected ? 'is-active' : ''}`}
                    onClick={() => toggleRag(opt.id)}
                  >
                    <span className="kb-menu__indicator kb-menu__indicator--check" aria-hidden="true">
                      {selected ? (
                        <svg
                          viewBox="0 0 24 24"
                          width="12"
                          height="12"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="3"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : null}
                    </span>
                    <span className="kb-menu__row-text">
                      <span className="kb-menu__row-name">{opt.name}</span>
                      <span className="kb-menu__row-blurb">{opt.description || '未填写简介'}</span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
