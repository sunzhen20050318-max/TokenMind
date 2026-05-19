import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  getBellItems,
  markAllBellItemsRead,
  markBellItemRead,
} from '../../services/updates';
import type { BellItem, VersionInfo } from '../../types/updates';
import './announcementPanel.css';

interface AnnouncementPanelProps {
  info: VersionInfo | null;
  onChange: () => void;
  onClose: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  /** Click handler for skill-suggestion items. Receives the bell item id;
   * the consumer is expected to navigate to Settings → Skills. */
  onNavigateToSkills?: () => void;
}

const ICONS: Record<string, string> = {
  // Per-level icons for announcements
  info: 'ℹ️',
  warning: '⚠️',
  critical: '🚨',
  // Version updates get a distinct icon regardless of level
  version: '🎉',
  // Pending skill suggestions
  'skill-suggestion': '✨',
};

export function AnnouncementPanel({
  info,
  onChange,
  onClose,
  onRefresh,
  refreshing,
  onNavigateToSkills,
}: AnnouncementPanelProps) {
  const items = getBellItems(info);
  const unread = items.filter((item) => !item.isRead);

  const handleMarkAll = () => {
    markAllBellItemsRead(info);
    onChange();
  };

  return (
    <div
      className="announcement-panel"
      role="dialog"
      aria-label="消息中心"
      onClick={(e) => e.stopPropagation()}
    >
      <header className="announcement-panel__head">
        <span className="announcement-panel__title">
          消息中心
          {unread.length > 0 ? (
            <span className="announcement-panel__count">{unread.length}</span>
          ) : null}
        </span>
        <div className="announcement-panel__head-actions">
          <button
            type="button"
            className={`announcement-panel__refresh ${refreshing ? 'is-loading' : ''}`}
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="刷新"
            title="检查最新公告与版本"
          >
            <RefreshIcon />
          </button>
          {unread.length > 0 ? (
            <button
              type="button"
              className="announcement-panel__mark-all"
              onClick={handleMarkAll}
            >
              全部已读
            </button>
          ) : null}
          <button
            type="button"
            className="announcement-panel__close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
      </header>

      {items.length === 0 ? (
        <div className="announcement-panel__empty">暂无消息</div>
      ) : (
        <div className="announcement-panel__list">
          {items.map((item) => (
            <Item
              key={item.id}
              item={item}
              onMarkRead={() => {
                markBellItemRead(item.id);
                onChange();
              }}
              onNavigateToSkills={
                item.type === 'skill-suggestion'
                  ? () => {
                      markBellItemRead(item.id);
                      onChange();
                      onClose();
                      onNavigateToSkills?.();
                    }
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Item({
  item,
  onMarkRead,
  onNavigateToSkills,
}: {
  item: BellItem;
  onMarkRead: () => void;
  onNavigateToSkills?: () => void;
}) {
  const icon =
    item.type === 'version'
      ? ICONS.version
      : item.type === 'skill-suggestion'
        ? ICONS['skill-suggestion']
        : ICONS[item.level] ?? ICONS.info;
  const handleDownload = (event: React.MouseEvent) => {
    event.preventDefault();
    if (item.downloadUrl) {
      window.open(item.downloadUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const className = [
    'announcement-panel__item',
    `announcement-panel__item--${item.level}`,
    item.type === 'version' ? 'announcement-panel__item--version' : '',
    item.type === 'skill-suggestion' ? 'announcement-panel__item--skill' : '',
    item.isRead ? 'is-read' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <article className={className}>
      <header className="announcement-panel__item-head">
        <span className="announcement-panel__item-icon">{icon}</span>
        <span className="announcement-panel__item-title">{item.title}</span>
        <span className="announcement-panel__item-date">
          {formatRelativeDate(item.receivedAt)}
        </span>
      </header>
      {/* translate="no" prevents Chrome translation / Grammarly / similar
          browser extensions from injecting child nodes into our markdown
          tree, which collides with React reconciliation and crashes with
          "Failed to execute insertBefore on Node". */}
      <div
        className="announcement-panel__item-body"
        translate="no"
        suppressHydrationWarning
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                {children}
              </a>
            ),
          }}
        >
          {item.message}
        </ReactMarkdown>
      </div>
      <footer className="announcement-panel__item-footer">
        <span className="announcement-panel__item-actions-left">
          {item.type === 'version' && item.downloadUrl ? (
            <button
              type="button"
              className="announcement-panel__item-primary"
              onClick={handleDownload}
            >
              立即下载 ↓
            </button>
          ) : item.type === 'skill-suggestion' && onNavigateToSkills ? (
            <button
              type="button"
              className="announcement-panel__item-primary"
              onClick={onNavigateToSkills}
            >
              去审批 →
            </button>
          ) : item.link ? (
            <a
              href={item.link}
              target="_blank"
              rel="noopener noreferrer"
              className="announcement-panel__item-link"
            >
              查看详情 →
            </a>
          ) : (
            <span />
          )}
        </span>
        {item.isRead ? (
          <span className="announcement-panel__item-read-tag">已读</span>
        ) : (
          <button
            type="button"
            className="announcement-panel__item-dismiss"
            onClick={onMarkRead}
          >
            标记已读
          </button>
        )}
      </footer>
    </article>
  );
}

function RefreshIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}

function formatRelativeDate(timestamp: number): string {
  const now = Date.now();
  const diffMs = now - timestamp;
  const dayMs = 86_400_000;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfReceived = new Date(timestamp);
  startOfReceived.setHours(0, 0, 0, 0);
  const dayDiff = Math.round(
    (startOfToday.getTime() - startOfReceived.getTime()) / dayMs,
  );

  if (diffMs < 60_000) return '刚刚';
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)} 分钟前`;
  if (dayDiff === 0) return '今天';
  if (dayDiff === 1) return '昨天';
  if (dayDiff < 7) return `${dayDiff} 天前`;
  const date = new Date(timestamp);
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}
