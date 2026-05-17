import React, { useEffect, useRef, useState } from 'react';

import type { KnowledgeBase } from '../../types/knowledge';
import './activeWikiSelector.css';

interface ActiveWikiSelectorProps {
  availableWikiKbs: KnowledgeBase[];
  activeKbId: string | null;
  onChange: (kbId: string | null) => void;
}

export const ActiveWikiSelector: React.FC<ActiveWikiSelectorProps> = ({
  availableWikiKbs,
  activeKbId,
  onChange,
}) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  const active = availableWikiKbs.find((kb) => kb.id === activeKbId) ?? null;
  const triggerLabel = active ? `Wiki: ${active.name}` : '激活 Wiki KB';

  return (
    <div className="active-wiki" ref={wrapperRef}>
      <button
        type="button"
        className={`active-wiki__trigger ${open ? 'is-open' : ''} ${active ? 'has-active' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        title={active ? `当前 Wiki KB: ${active.name}` : '选择一个 Wiki 知识库供 LLM 浏览'}
      >
        {triggerLabel}
      </button>
      {open && (
        <div className="active-wiki__menu" role="listbox">
          <button
            type="button"
            className={`active-wiki__option ${activeKbId === null ? 'is-active' : ''}`}
            onClick={() => {
              onChange(null);
              setOpen(false);
            }}
          >
            <span className="active-wiki__option-name">不激活</span>
            <span className="active-wiki__option-blurb">LLM 看不到任何 Wiki KB</span>
          </button>
          {availableWikiKbs.length === 0 && (
            <div className="active-wiki__empty">还没有 Wiki 类型的知识库。</div>
          )}
          {availableWikiKbs.map((kb) => (
            <button
              key={kb.id}
              type="button"
              className={`active-wiki__option ${activeKbId === kb.id ? 'is-active' : ''}`}
              onClick={() => {
                onChange(kb.id);
                setOpen(false);
              }}
            >
              <span className="active-wiki__option-name">{kb.name}</span>
              <span className="active-wiki__option-blurb">
                {kb.entity_count} 实体 · {kb.topic_count} 主题 · {kb.source_count} 素材
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
