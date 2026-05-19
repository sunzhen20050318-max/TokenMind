import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { AnnouncementPanel } from '../Updates/AnnouncementPanel';
import { getUnreadBellCount } from '../../services/updates';
import type { VersionInfo } from '../../types/updates';
import './header.css';

// Connection status used to render a "已连接 / 未连接" badge in the header.
// Removed at the user's request — the bell + ? buttons now occupy the header
// alone. The /api/status ping was only for that badge; App.tsx keeps its own
// poll going for the version-mismatch reload, so dropping this here is safe.

interface HeaderProps {
  versionInfo: VersionInfo | null;
  onUpdatesChange: () => void;
  onRefreshUpdates: () => void;
  updatesRefreshing: boolean;
  /** Wired up by App so clicking a skill-suggestion bell item jumps the
   * user into Settings → Skills where they can approve / reject. */
  onNavigateToSkills?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  versionInfo,
  onUpdatesChange,
  onRefreshUpdates,
  updatesRefreshing,
  onNavigateToSkills,
}) => {
  const [panelOpen, setPanelOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  // Bumped whenever the panel reports a read-state change. Without this the
  // unreadCount useMemo would stay cached on [versionInfo] alone — read state
  // lives in localStorage, not in versionInfo, so memoization wouldn't notice.
  const [bellRefreshKey, setBellRefreshKey] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contactRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!contactOpen) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!contactRef.current?.contains(event.target as Node)) {
        setContactOpen(false);
      }
    };
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setContactOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onEsc);
    };
  }, [contactOpen]);

  const handleBellChange = useCallback(() => {
    setBellRefreshKey((k) => k + 1);
    onUpdatesChange();
  }, [onUpdatesChange]);

  // Close panel on outside click or Escape.
  useEffect(() => {
    if (!panelOpen) return;
    const onClick = (event: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        setPanelOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPanelOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [panelOpen]);

  const unreadCount = useMemo(
    () => getUnreadBellCount(versionInfo),
    [versionInfo, bellRefreshKey],
  );

  return (
    <header className="shell-header">
      <div className="shell-header__actions">
        <div className="shell-header__contact-wrapper" ref={contactRef}>
          <button
            type="button"
            className={`shell-header__contact ${contactOpen ? 'is-open' : ''}`}
            onClick={() => setContactOpen((prev) => !prev)}
            aria-label="联系作者"
            aria-expanded={contactOpen}
            title="联系作者"
          >
            ?
          </button>
          {contactOpen ? (
            <div className="shell-header__contact-popover" role="dialog">
              <div className="shell-header__contact-label">联系我</div>
              <a
                className="shell-header__contact-email"
                href="mailto:sunzhen20050318@gmail.com?subject=TokenMind%20反馈"
                onClick={() => setContactOpen(false)}
              >
                sunzhen20050318@gmail.com
              </a>
            </div>
          ) : null}
        </div>

        <div className="shell-header__bell-wrapper" ref={wrapperRef}>
        <button
          type="button"
          className={`shell-header__bell ${panelOpen ? 'is-open' : ''}`}
          onClick={() => setPanelOpen((value) => !value)}
          aria-label={
            unreadCount > 0 ? `${unreadCount} 条未读消息` : '消息中心'
          }
          aria-expanded={panelOpen}
        >
          <BellIcon />
          {unreadCount > 0 ? (
            <span className="shell-header__bell-badge">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          ) : null}
        </button>

          {panelOpen ? (
            <AnnouncementPanel
              info={versionInfo}
              onChange={handleBellChange}
              onClose={() => setPanelOpen(false)}
              onRefresh={onRefreshUpdates}
              refreshing={updatesRefreshing}
              onNavigateToSkills={onNavigateToSkills}
            />
          ) : null}
        </div>
      </div>
    </header>
  );
};

function BellIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}
