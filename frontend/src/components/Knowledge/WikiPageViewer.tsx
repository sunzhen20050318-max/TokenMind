import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import './wikiPageViewer.css';

interface WikiPageViewerProps {
  knowledgeBaseId: string;
  pagePath: string | null;
  onFollowLink?: (title: string) => void;
}

interface PageResponse {
  title: string;
  type: string;
  path: string;
  content: string;
  frontmatter: Record<string, string>;
  outgoing_links: string[];
}

const WIKILINK_RE = /\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g;

function transformWikilinks(markdown: string): string {
  return markdown.replace(WIKILINK_RE, (_, target) => `**[[${String(target).trim()}]]**`);
}

export const WikiPageViewer: React.FC<WikiPageViewerProps> = ({
  knowledgeBaseId,
  pagePath,
  onFollowLink,
}) => {
  const [page, setPage] = useState<PageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pagePath) {
      setPage(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/knowledge/${encodeURIComponent(knowledgeBaseId)}/pages/raw?path=${encodeURIComponent(pagePath)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as PageResponse;
        if (!cancelled) setPage(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载页面失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pagePath, knowledgeBaseId]);

  if (!pagePath) {
    return (
      <div className="wiki-viewer__placeholder">
        从左侧选择一个页面查看内容。
      </div>
    );
  }

  if (loading) {
    return <div className="wiki-viewer__placeholder">加载中…</div>;
  }

  if (error || !page) {
    return (
      <div className="wiki-viewer__placeholder is-error">
        加载失败：{error ?? '未知错误'}
      </div>
    );
  }

  const confidence = (page.frontmatter?.confidence ?? '').toUpperCase();
  const evidence = page.frontmatter?.evidence ?? '';

  return (
    <article className="wiki-viewer">
      <header className="wiki-viewer__head">
        <div className="wiki-viewer__meta">
          <span className={`wiki-viewer__type wiki-viewer__type--${page.type}`}>{page.type}</span>
          {confidence ? (
            <span
              className={`wiki-viewer__confidence wiki-viewer__confidence--${confidence.toLowerCase()}`}
              title={evidence || undefined}
            >
              {confidence}
            </span>
          ) : null}
          <span className="wiki-viewer__path">{page.path}</span>
        </div>
        <h1 className="wiki-viewer__title">{page.title}</h1>
        {evidence ? (
          <p className="wiki-viewer__evidence">证据:{evidence}</p>
        ) : null}
      </header>
      <div className="wiki-viewer__body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {transformWikilinks(page.content)}
        </ReactMarkdown>
      </div>
      {page.outgoing_links.length > 0 && (
        <aside className="wiki-viewer__sidebar">
          <h3>出链</h3>
          <ul>
            {page.outgoing_links.map((link) => (
              <li key={link}>
                <button type="button" onClick={() => onFollowLink?.(link)}>
                  {link}
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </article>
  );
};
