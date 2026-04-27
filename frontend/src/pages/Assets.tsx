import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AttachmentIcon } from '../components/Chat/AttachmentIcon';
import { api } from '../services/api';
import type { AssetCategory, AssetItem } from '../types/assets';
import './assets.css';

interface AssetsPageProps {
  onNavigateToSession?: (sessionId: string, projectId: string | null) => void;
}

const PAGE_SIZE = 60;

const CATEGORY_TABS: Array<{ id: AssetCategory; label: string; emptyHint: string }> = [
  { id: 'image', label: '图片', emptyHint: '还没有生成或上传过图片。' },
  { id: 'video', label: '视频', emptyHint: '还没有视频资产。' },
  { id: 'file', label: '文件', emptyHint: '还没有可展示的文件。' },
];

type FavoriteFilter = 'all' | 'favorite';

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exp = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / 1024 ** exp;
  return `${value >= 100 || exp === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exp]}`;
}

function dateGroupKey(iso: string): string {
  if (!iso) return '未知日期';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '未知日期';
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

interface AssetGroup {
  date: string;
  items: AssetItem[];
}

function groupByDate(items: AssetItem[]): AssetGroup[] {
  const map = new Map<string, AssetGroup>();
  for (const item of items) {
    const key = dateGroupKey(item.created_at);
    let bucket = map.get(key);
    if (!bucket) {
      bucket = { date: key, items: [] };
      map.set(key, bucket);
    }
    bucket.items.push(item);
  }
  return Array.from(map.values());
}

export const AssetsPage: React.FC<AssetsPageProps> = ({ onNavigateToSession }) => {
  const [category, setCategory] = useState<AssetCategory>('image');
  const [favoriteFilter, setFavoriteFilter] = useState<FavoriteFilter>('all');
  const [items, setItems] = useState<AssetItem[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const requestSeqRef = useRef(0);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const loadPage = useCallback(
    async (mode: 'reset' | 'append') => {
      const seq = ++requestSeqRef.current;
      setLoading(true);
      setError(null);
      try {
        const nextCursor = mode === 'reset' ? 0 : cursor ?? 0;
        const data = await api.listAssets({
          category,
          favorite: favoriteFilter === 'favorite' ? true : undefined,
          cursor: nextCursor,
          limit: PAGE_SIZE,
        });
        if (seq !== requestSeqRef.current) return;
        setTotal(data.total);
        setCursor(data.next_cursor);
        setItems((prev) => (mode === 'reset' ? data.items : [...prev, ...data.items]));
      } catch (err) {
        if (seq !== requestSeqRef.current) return;
        setError(err instanceof Error ? err.message : '加载资产失败');
      } finally {
        if (seq === requestSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [category, favoriteFilter, cursor],
  );

  // Reset and load whenever the active tab or sub-tab changes.
  useEffect(() => {
    setItems([]);
    setCursor(0);
    setTotal(0);
    void loadPage('reset');
    // loadPage's identity changes when the same deps change, so omit it from deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, favoriteFilter]);

  // Infinite scroll via IntersectionObserver on the sentinel below the grid.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || cursor === null || loading) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadPage('append');
        }
      },
      { rootMargin: '320px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadPage, cursor, loading]);

  const handleFavorite = async (asset: AssetItem) => {
    setBusyId(asset.id);
    try {
      const updated = await api.setAssetFavorite(asset.id, !asset.favorite);
      setItems((prev) => prev.map((item) => (item.id === asset.id ? updated : item)));
      // If we're in the favorite-only filter and just unfavorited, drop it locally.
      if (favoriteFilter === 'favorite' && !updated.favorite) {
        setItems((prev) => prev.filter((item) => item.id !== asset.id));
        setTotal((value) => Math.max(0, value - 1));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新收藏失败');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (asset: AssetItem) => {
    if (!window.confirm(`确认删除 “${asset.name}” 吗？此操作不可撤销。`)) return;
    setBusyId(asset.id);
    try {
      await api.deleteAsset(asset.id);
      setItems((prev) => prev.filter((item) => item.id !== asset.id));
      setTotal((value) => Math.max(0, value - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除资产失败');
    } finally {
      setBusyId(null);
    }
  };

  const groups = useMemo(() => groupByDate(items), [items]);
  const activeTabMeta = CATEGORY_TABS.find((tab) => tab.id === category) ?? CATEGORY_TABS[0];
  const showEmpty = !loading && items.length === 0;
  const showEndOfFeed = cursor === null && items.length > 0;

  return (
    <div className="assets-page">
      <header className="assets-page__header">
        <h1>资产库</h1>
        <p>统一管理 AI 生成与你上传的图片、视频、文件，支持收藏与回到来源会话。</p>
      </header>

      <div className="assets-page__tabs">
        {CATEGORY_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`assets-page__tab ${category === tab.id ? 'is-active' : ''}`}
            onClick={() => setCategory(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="assets-page__subtabs">
        <button
          className={`assets-page__subtab ${favoriteFilter === 'all' ? 'is-active' : ''}`}
          onClick={() => setFavoriteFilter('all')}
          type="button"
        >
          所有{activeTabMeta.label}
          {total > 0 && favoriteFilter === 'all' ? (
            <span className="assets-page__subtab-count">{total}</span>
          ) : null}
        </button>
        <button
          className={`assets-page__subtab ${favoriteFilter === 'favorite' ? 'is-active' : ''}`}
          onClick={() => setFavoriteFilter('favorite')}
          type="button"
        >
          我的收藏
          {total > 0 && favoriteFilter === 'favorite' ? (
            <span className="assets-page__subtab-count">{total}</span>
          ) : null}
        </button>
      </div>

      {error ? <div className="assets-page__error">{error}</div> : null}

      {showEmpty ? (
        <div className="assets-page__empty">
          <div className="assets-page__empty-title">
            {favoriteFilter === 'favorite' ? '还没有收藏' : activeTabMeta.emptyHint}
          </div>
          <div className="assets-page__empty-hint">
            {favoriteFilter === 'favorite'
              ? '在卡片上点击 ⭐ 即可加入「我的收藏」。'
              : '在聊天里生成或上传后会自动出现在这里。'}
          </div>
        </div>
      ) : null}

      {groups.map((group) => (
        <section key={group.date} className="assets-group">
          <div className="assets-group__head">
            <span className="assets-group__date">{group.date}</span>
          </div>
          <div className={`assets-grid assets-grid--${category}`}>
            {group.items.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                category={category}
                busy={busyId === asset.id}
                onFavorite={() => void handleFavorite(asset)}
                onDelete={() => void handleDelete(asset)}
                onJumpToSession={
                  onNavigateToSession && asset.session_id
                    ? () => onNavigateToSession(asset.session_id, asset.project_id ?? null)
                    : undefined
                }
              />
            ))}
          </div>
        </section>
      ))}

      {loading ? <div className="assets-page__loading">加载中…</div> : null}
      {showEndOfFeed ? <div className="assets-page__end">已经到底了</div> : null}
      <div ref={sentinelRef} />
    </div>
  );
};

interface AssetCardProps {
  asset: AssetItem;
  category: AssetCategory;
  busy: boolean;
  onFavorite: () => void;
  onDelete: () => void;
  onJumpToSession?: () => void;
}

const AssetCard: React.FC<AssetCardProps> = ({
  asset,
  category,
  busy,
  onFavorite,
  onDelete,
  onJumpToSession,
}) => {
  const previewUrl = `${api.getAttachmentUrl(asset.id)}?disposition=inline`;
  const attachmentForIcon = useMemo(
    () => ({
      id: asset.id,
      name: asset.name,
      category: asset.category,
      is_image: asset.is_image,
      mime_type: asset.mime_type ?? undefined,
    }),
    [asset.id, asset.name, asset.category, asset.is_image, asset.mime_type],
  );

  return (
    <div className={`asset-card asset-card--${category} ${asset.favorite ? 'is-favorite' : ''}`}>
      <div className="asset-card__media">
        {category === 'image' && asset.is_image ? (
          <img src={previewUrl} alt={asset.name} loading="lazy" />
        ) : category === 'video' ? (
          <video
            src={previewUrl}
            muted
            preload="metadata"
            playsInline
            className="asset-card__video"
          />
        ) : (
          <div className="asset-card__file-icon-wrap">
            <AttachmentIcon attachment={attachmentForIcon} size={42} />
          </div>
        )}

        <div className="asset-card__overlay">
          <button
            className="asset-card__action"
            disabled={busy}
            onClick={onFavorite}
            type="button"
            title={asset.favorite ? '取消收藏' : '加入收藏'}
            aria-label={asset.favorite ? '取消收藏' : '加入收藏'}
          >
            {asset.favorite ? '★' : '☆'}
          </button>
          {onJumpToSession ? (
            <button
              className="asset-card__action"
              disabled={busy}
              onClick={onJumpToSession}
              type="button"
              title="回到生成此文件的对话"
              aria-label="回到对话"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14" strokeLinecap="round" />
                <path d="M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          ) : null}
          <button
            className="asset-card__action asset-card__action--danger"
            disabled={busy}
            onClick={onDelete}
            type="button"
            title="删除"
            aria-label="删除"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18" strokeLinecap="round" />
              <path d="M8 6V4h8v2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M6 6v14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
      <div className="asset-card__meta">
        <div className="asset-card__name" title={asset.name}>
          {asset.name || '未命名'}
        </div>
        <div className="asset-card__sub">{formatBytes(asset.size)}</div>
      </div>
    </div>
  );
};
