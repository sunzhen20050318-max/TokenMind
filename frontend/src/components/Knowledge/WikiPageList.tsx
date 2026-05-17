import React, { useMemo } from 'react';

import type { WikiPageSummary } from '../../types/knowledge';
import './wikiPageList.css';

interface WikiPageListProps {
  pages: WikiPageSummary[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

const TYPE_ORDER: WikiPageSummary['type'][] = [
  'entity',
  'topic',
  'source',
  'synthesis',
  'comparison',
  'query',
  'page',
];

const TYPE_LABELS: Record<WikiPageSummary['type'], string> = {
  entity: '实体',
  topic: '主题',
  source: '素材',
  synthesis: '综合',
  comparison: '对比',
  query: '查询',
  page: '其他',
};

export const WikiPageList: React.FC<WikiPageListProps> = ({ pages, selectedPath, onSelect }) => {
  const grouped = useMemo(() => {
    const map = new Map<WikiPageSummary['type'], WikiPageSummary[]>();
    for (const page of pages) {
      const bucket = map.get(page.type) ?? [];
      bucket.push(page);
      map.set(page.type, bucket);
    }
    return TYPE_ORDER.filter((t) => map.has(t)).map((t) => ({
      type: t,
      pages: [...(map.get(t) ?? [])].sort((a, b) => a.title.localeCompare(b.title, 'zh-CN')),
    }));
  }, [pages]);

  if (!pages.length) {
    return (
      <div className="wiki-pagelist__empty">
        还没有任何 Wiki 页面。上传素材后，LLM 会自动编译出 source / entity / topic 页面。
      </div>
    );
  }

  return (
    <div className="wiki-pagelist">
      {grouped.map((group) => (
        <section key={group.type} className="wiki-pagelist__group">
          <header className="wiki-pagelist__group-head">
            <span className="wiki-pagelist__group-label">{TYPE_LABELS[group.type]}</span>
            <span className="wiki-pagelist__group-count">{group.pages.length}</span>
          </header>
          <ul className="wiki-pagelist__items">
            {group.pages.map((page) => (
              <li
                key={page.path}
                className={`wiki-pagelist__item ${selectedPath === page.path ? 'is-active' : ''}`}
              >
                <button type="button" onClick={() => onSelect(page.path)}>
                  {page.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
};
