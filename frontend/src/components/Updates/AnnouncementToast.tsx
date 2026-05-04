import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  getNewToastAnnouncements,
  markAnnouncementSeenInToast,
} from '../../services/updates';
import type { Announcement, VersionInfo } from '../../types/updates';
import './announcementToast.css';

interface AnnouncementToastProps {
  /**
   * Latest fetched version info. The toast only pops up for announcements that
   * have *never* been shown in a toast before — closing the toast does not
   * mark the item as read; users can still revisit it via the bell panel.
   */
  info: VersionInfo | null;
}

const LEVEL_ICON: Record<string, string> = {
  info: 'ℹ️',
  warning: '⚠️',
  critical: '🚨',
};

export function AnnouncementToast({ info }: AnnouncementToastProps) {
  // Snapshot the "new" announcements once when info arrives, then mark them
  // as seen-in-toast so they never reappear in toast form. Subsequent renders
  // (caused by user dismissing one of them) don't re-evaluate the source list.
  const newAnnouncements = useMemo(
    () => getNewToastAnnouncements(info),
    [info],
  );

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (newAnnouncements.length === 0) return;
    for (const ann of newAnnouncements) {
      markAnnouncementSeenInToast(ann.id);
    }
  }, [newAnnouncements]);

  const visible = newAnnouncements.filter((ann) => !dismissed.has(ann.id));
  if (visible.length === 0) return null;

  return (
    <div className="announcement-toast-stack" role="region" aria-label="新公告">
      {visible.map((ann) => (
        <Card
          key={ann.id}
          announcement={ann}
          onDismiss={() =>
            setDismissed((prev) => {
              const next = new Set(prev);
              next.add(ann.id);
              return next;
            })
          }
        />
      ))}
    </div>
  );
}

function Card({
  announcement,
  onDismiss,
}: {
  announcement: Announcement;
  onDismiss: () => void;
}) {
  const level = announcement.level ?? 'info';
  const icon = LEVEL_ICON[level] ?? LEVEL_ICON.info;
  const handleLinkClick = (event: React.MouseEvent) => {
    if (!announcement.link) return;
    event.preventDefault();
    window.open(announcement.link, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className={`announcement-toast announcement-toast--${level}`}>
      <header className="announcement-toast__head">
        <span className="announcement-toast__icon">{icon}</span>
        <span className="announcement-toast__title">{announcement.title}</span>
        <button
          type="button"
          className="announcement-toast__close"
          onClick={onDismiss}
          aria-label="关闭"
          title="关闭(在铃铛中仍可查看)"
        >
          ×
        </button>
      </header>
      <div className="announcement-toast__body" translate="no">
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
          {announcement.message}
        </ReactMarkdown>
      </div>
      {announcement.link ? (
        <footer className="announcement-toast__footer">
          <button
            type="button"
            className="announcement-toast__link"
            onClick={handleLinkClick}
          >
            查看详情 →
          </button>
        </footer>
      ) : null}
    </div>
  );
}
