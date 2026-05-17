import React, { useCallback, useEffect, useState } from 'react';

import { api } from '../../services/api';
import type { KnowledgeBase, WikiPageSummary } from '../../types/knowledge';
import { WikiPageList } from './WikiPageList';
import { WikiPageViewer } from './WikiPageViewer';
import './wikiKbDetail.css';

interface WikiKbDetailProps {
  kb: KnowledgeBase;
}

type Tab = 'pages' | 'graph';

export const WikiKbDetail: React.FC<WikiKbDetailProps> = ({ kb }) => {
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('pages');

  const loadPages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await api.listWikiPages(kb.id);
      setPages(body.pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 Wiki 页面失败');
    } finally {
      setLoading(false);
    }
  }, [kb.id]);

  useEffect(() => {
    void loadPages();
  }, [loadPages]);

  const handleFollowLink = useCallback(
    (title: string) => {
      const match = pages.find((p) => p.title === title);
      if (match) setSelectedPath(match.path);
    },
    [pages],
  );

  return (
    <div className="wiki-detail">
      <div className="wiki-detail__tabs">
        <button
          type="button"
          className={`wiki-detail__tab ${tab === 'pages' ? 'is-active' : ''}`}
          onClick={() => setTab('pages')}
        >
          Wiki 页面
          <span className="wiki-detail__tab-count">{pages.length}</span>
        </button>
        <button
          type="button"
          className={`wiki-detail__tab ${tab === 'graph' ? 'is-active' : ''}`}
          onClick={() => setTab('graph')}
        >
          知识图谱
        </button>
      </div>

      {tab === 'pages' && (
        <div className="wiki-detail__body">
          <aside className="wiki-detail__sidebar">
            {loading ? (
              <div className="wiki-detail__loading">加载中…</div>
            ) : error ? (
              <div className="wiki-detail__error">{error}</div>
            ) : (
              <WikiPageList
                pages={pages}
                selectedPath={selectedPath}
                onSelect={setSelectedPath}
              />
            )}
          </aside>
          <main className="wiki-detail__main">
            <WikiPageViewer
              knowledgeBaseId={kb.id}
              pagePath={selectedPath}
              onFollowLink={handleFollowLink}
            />
          </main>
        </div>
      )}

      {tab === 'graph' && (
        <div className="wiki-detail__graph-slot">
          {/* KnowledgeGraph is mounted here in Task F11 */}
          <div className="wiki-detail__loading">图谱组件将在 Task F11 接入</div>
        </div>
      )}
    </div>
  );
};
