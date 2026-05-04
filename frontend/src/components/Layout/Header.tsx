import React, { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../services/api';
import { AnnouncementPanel } from '../Updates/AnnouncementPanel';
import { getUnreadBellCount } from '../../services/updates';
import type { VersionInfo } from '../../types/updates';
import './header.css';

const CONNECTED = '已连接';
const DISCONNECTED = '未连接';
const POLL_INTERVAL_MS = 15000;

interface HeaderProps {
  versionInfo: VersionInfo | null;
  onUpdatesChange: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  versionInfo,
  onUpdatesChange,
}) => {
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    const ping = async () => {
      try {
        await api.getStatus();
        if (!cancelled) setServerOnline(true);
      } catch {
        if (!cancelled) setServerOnline(false);
      }
    };

    void ping();
    const handle = window.setInterval(() => void ping(), POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

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
    [versionInfo],
  );

  const online = serverOnline === true;
  return (
    <header className="shell-header">
      <div className="shell-header__status">
        <span
          className={`shell-header__status-dot ${
            online ? 'is-online' : 'is-offline'
          }`}
        />
        <span>{online ? CONNECTED : DISCONNECTED}</span>
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
            onChange={onUpdatesChange}
            onClose={() => setPanelOpen(false)}
          />
        ) : null}
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
