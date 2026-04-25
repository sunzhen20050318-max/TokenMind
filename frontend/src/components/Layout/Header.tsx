import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import './header.css';

const CONNECTED = '\u5df2\u8fde\u63a5';
const DISCONNECTED = '\u672a\u8fde\u63a5';
const POLL_INTERVAL_MS = 15000;

export const Header: React.FC = () => {
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);

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

  const online = serverOnline === true;
  return (
    <header className="shell-header">
      <div className="shell-header__status">
        <span className={`shell-header__status-dot ${online ? 'is-online' : 'is-offline'}`} />
        <span>{online ? CONNECTED : DISCONNECTED}</span>
      </div>
    </header>
  );
};
