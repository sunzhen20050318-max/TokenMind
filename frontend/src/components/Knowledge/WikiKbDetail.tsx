import React, { useCallback, useEffect, useState } from 'react';

import { api } from '../../services/api';
import type {
  KnowledgeBase,
  KnowledgeDocument,
  WikiPageSummary,
} from '../../types/knowledge';
import { KnowledgeGraph } from './KnowledgeGraph';
import { WikiPageList } from './WikiPageList';
import { WikiPageViewer } from './WikiPageViewer';
import './wikiKbDetail.css';

interface WikiKbDetailProps {
  kb: KnowledgeBase;
  documents: KnowledgeDocument[];
  onDeleteDocument: (documentId: string) => void;
}

type Tab = 'sources' | 'pages' | 'graph';

export const WikiKbDetail: React.FC<WikiKbDetailProps> = ({
  kb,
  documents,
  onDeleteDocument,
}) => {
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('sources');
  const [recompiling, setRecompiling] = useState(false);
  const [recompileMessage, setRecompileMessage] = useState<string | null>(null);

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

  const handleRecompile = useCallback(async () => {
    if (recompiling || documents.length === 0) return;
    setRecompiling(true);
    setRecompileMessage('正在重新编译,LLM 正在抽取实体与主题…');
    try {
      const result = await api.recompileWikiSources(kb.id);
      const failed = result.results.filter((r) => r.status !== 'ok').length;
      setRecompileMessage(
        failed === 0
          ? `已重新编译 ${result.processed} 份素材,刷新页面后即可看到新内容。`
          : `重新编译完成,${failed} 份失败,请查看控制台日志。`,
      );
      await loadPages();
    } catch (err) {
      setRecompileMessage(err instanceof Error ? `重新编译失败:${err.message}` : '重新编译失败');
    } finally {
      setRecompiling(false);
    }
  }, [documents.length, kb.id, loadPages, recompiling]);

  const handleFollowLink = useCallback(
    (title: string) => {
      const match = pages.find((p) => p.title === title);
      if (match) setSelectedPath(match.path);
    },
    [pages],
  );

  return (
    <div className="wiki-detail">
      <div className="wiki-detail__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          className={`wiki-detail__tab ${tab === 'sources' ? 'is-active' : ''}`}
          onClick={() => setTab('sources')}
        >
          原始素材
          <span className="wiki-detail__tab-count">{documents.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          className={`wiki-detail__tab ${tab === 'pages' ? 'is-active' : ''}`}
          onClick={() => setTab('pages')}
        >
          Wiki 页面
          <span className="wiki-detail__tab-count">{pages.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          className={`wiki-detail__tab ${tab === 'graph' ? 'is-active' : ''}`}
          onClick={() => setTab('graph')}
        >
          知识图谱
        </button>
      </div>

      {tab === 'sources' && (
        <div className="wiki-detail__panel">
          {documents.length > 0 ? (
            <div className="wiki-detail__actions">
              <button
                type="button"
                className="wiki-detail__action-button"
                onClick={() => void handleRecompile()}
                disabled={recompiling}
                title="重新让 LLM 抽取实体/主题。素材没变时也可以触发,用来覆盖之前失败或不完整的编译。"
              >
                {recompiling ? '正在重新编译…' : '重新编译 Wiki'}
              </button>
              {recompileMessage ? (
                <span className="wiki-detail__action-hint">{recompileMessage}</span>
              ) : null}
            </div>
          ) : null}

          {documents.length === 0 ? (
            <div className="knowledge-page__empty is-inline">
              还没有任何素材。上传 PDF、Markdown、文本等资料后,LLM 会把它们编译成相互链接的 Wiki 页面。
            </div>
          ) : (
            <div className="knowledge-document-list">
              {documents.map((document) => (
                <div key={document.id} className="knowledge-document">
                  <div className="knowledge-document__top">
                    <div className="knowledge-document__main">
                      <strong>{document.name}</strong>
                      <p>{document.path}</p>
                    </div>
                    <button
                      type="button"
                      className="knowledge-document__delete"
                      onClick={() => onDeleteDocument(document.id)}
                    >
                      删除
                    </button>
                  </div>
                  <div className="knowledge-document__meta">
                    <span>{document.file_type.toUpperCase() || 'FILE'}</span>
                    <span>{describeWikiStage(document)}</span>
                    <span>{document.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'pages' && (
        <div className="wiki-detail__split">
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
          <KnowledgeGraph
            knowledgeBaseId={kb.id}
            onSelectNode={(path) => {
              setSelectedPath(path);
              setTab('pages');
            }}
          />
        </div>
      )}
    </div>
  );
};

function describeWikiStage(document: KnowledgeDocument): string {
  if (document.status === 'failed') return '编译失败';
  if (document.status === 'ready') return '已编译为 Wiki';
  switch (document.processing_stage) {
    case 'queued':
      return '已上传 · 等待编译';
    case 'extracting':
      return '正在提取文本';
    case 'compiling':
    case 'embedding':
    case 'indexing':
      return '正在生成 Wiki 页面';
    case 'ready':
      return '已编译为 Wiki';
    default:
      return '正在处理';
  }
}
