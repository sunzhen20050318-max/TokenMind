import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { Session } from '../../types';
import type { KnowledgeBase } from '../../types/knowledge';
import { hasModKey, modKey } from '../../utils/platform';
import './commandPalette.css';

export type NavTarget =
  | 'chat'
  | 'knowledge'
  | 'assets'
  | 'music'
  | 'voice-clone'
  | 'tts'
  | 'voice-design'
  | 'video'
  | 'project-home'
  | 'settings'
  | 'tasks'
  | 'usage';

export interface CommandPaletteAction {
  kind: 'open-session' | 'open-kb' | 'open-nav';
  sessionId?: string;
  knowledgeBaseId?: string;
  nav?: NavTarget;
}

interface CommandPaletteProps {
  sessions: Session[];
  knowledgeBases: KnowledgeBase[];
  onAction: (action: CommandPaletteAction) => void;
}

interface PaletteItem {
  id: string;
  group: '会话' | '知识库' | '跳转';
  label: string;
  hint?: string;
  haystack: string;
  action: CommandPaletteAction;
}

const NAV_ITEMS: Array<{ id: NavTarget; label: string; hint?: string }> = [
  { id: 'chat', label: '聊天', hint: '回到对话' },
  { id: 'knowledge', label: '知识库' },
  { id: 'assets', label: '资产库' },
  { id: 'tasks', label: '定时任务' },
  { id: 'usage', label: '用量' },
  { id: 'music', label: '音乐工作室' },
  { id: 'tts', label: '语音合成' },
  { id: 'voice-clone', label: '声音克隆' },
  { id: 'voice-design', label: '声音设计' },
  { id: 'video', label: '视频生成' },
  { id: 'settings', label: '设置中心' },
];

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  sessions,
  knowledgeBases,
  onAction,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Global hotkey: ⌘K (Mac) / Ctrl+K (Win/Linux). Also Esc to close.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'k' && hasModKey(event)) {
        event.preventDefault();
        setOpen((prev) => !prev);
        return;
      }
      if (event.key === 'Escape' && open) {
        event.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      const tid = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(tid);
    }
  }, [open]);

  const allItems = useMemo<PaletteItem[]>(() => {
    const items: PaletteItem[] = [];
    for (const nav of NAV_ITEMS) {
      items.push({
        id: `nav:${nav.id}`,
        group: '跳转',
        label: nav.label,
        hint: nav.hint,
        haystack: `${nav.label} ${nav.hint ?? ''} ${nav.id}`.toLowerCase(),
        action: { kind: 'open-nav', nav: nav.id },
      });
    }
    for (const kb of knowledgeBases) {
      items.push({
        id: `kb:${kb.id}`,
        group: '知识库',
        label: kb.name,
        hint: kb.type === 'wiki' ? 'Wiki' : 'RAG',
        haystack: `${kb.name} ${kb.description ?? ''} ${kb.type}`.toLowerCase(),
        action: { kind: 'open-kb', knowledgeBaseId: kb.id },
      });
    }
    for (const session of sessions.slice(0, 80)) {
      const title = session.title || session.first_message || '新对话';
      items.push({
        id: `session:${session.session_id}`,
        group: '会话',
        label: title,
        haystack: `${title} ${session.first_message ?? ''}`.toLowerCase(),
        action: { kind: 'open-session', sessionId: session.session_id },
      });
    }
    return items;
  }, [sessions, knowledgeBases]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return allItems.slice(0, 50);
    }
    const matches = allItems.filter((item) => item.haystack.includes(q));
    return matches.slice(0, 50);
  }, [query, allItems]);

  // Group items in render order (preserve filtered ordering, but cluster
  // by group for visual coherence). 跳转 first, then 知识库, then 会话.
  const grouped = useMemo(() => {
    const buckets: Record<string, PaletteItem[]> = { 跳转: [], 知识库: [], 会话: [] };
    for (const item of filtered) buckets[item.group].push(item);
    return (['跳转', '知识库', '会话'] as const)
      .map((g) => ({ group: g, items: buckets[g] }))
      .filter((b) => b.items.length > 0);
  }, [filtered]);

  const flatItems = useMemo(() => grouped.flatMap((g) => g.items), [grouped]);

  useEffect(() => {
    if (activeIndex >= flatItems.length) {
      setActiveIndex(Math.max(0, flatItems.length - 1));
    }
  }, [activeIndex, flatItems.length]);

  const runAction = useCallback(
    (item: PaletteItem) => {
      onAction(item.action);
      setOpen(false);
    },
    [onAction],
  );

  const handleKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((idx) => Math.min(flatItems.length - 1, idx + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((idx) => Math.max(0, idx - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const item = flatItems[activeIndex];
      if (item) runAction(item);
    }
  };

  // Scroll the active item into view when keyboard-navigating.
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-row-index="${activeIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  if (!open) return null;

  let cursor = 0;

  return (
    <div className="cmdk__backdrop" onClick={() => setOpen(false)}>
      <div
        className="cmdk"
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="cmdk__input-row">
          <span className="cmdk__icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" strokeLinecap="round" />
            </svg>
          </span>
          <input
            ref={inputRef}
            className="cmdk__input"
            placeholder="搜索会话、知识库、页面…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleKey}
          />
          <kbd className="cmdk__kbd">Esc</kbd>
        </div>

        <div className="cmdk__list" ref={listRef}>
          {flatItems.length === 0 ? (
            <div className="cmdk__empty">没有匹配项</div>
          ) : (
            grouped.map((bucket) => (
              <div key={bucket.group} className="cmdk__group">
                <div className="cmdk__group-label">{bucket.group}</div>
                {bucket.items.map((item) => {
                  const rowIndex = cursor++;
                  const isActive = rowIndex === activeIndex;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      data-row-index={rowIndex}
                      className={`cmdk__row ${isActive ? 'is-active' : ''}`}
                      onMouseEnter={() => setActiveIndex(rowIndex)}
                      onClick={() => runAction(item)}
                    >
                      <span className="cmdk__row-label">{item.label}</span>
                      {item.hint ? <span className="cmdk__row-hint">{item.hint}</span> : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="cmdk__footer">
          <span><kbd className="cmdk__kbd">↑</kbd><kbd className="cmdk__kbd">↓</kbd> 移动</span>
          <span><kbd className="cmdk__kbd">⏎</kbd> 打开</span>
          <span><kbd className="cmdk__kbd">{modKey}</kbd> + <kbd className="cmdk__kbd">K</kbd> 切换</span>
        </div>
      </div>
    </div>
  );
};
