import { useMemo } from 'react';

import {
  dismissUpdate,
  isUpdateAvailable,
  isUpdateDismissed,
  pickDownloadUrl,
} from '../../services/updates';
import type { VersionInfo } from '../../types/updates';
import { APP_VERSION } from '../../version';
import './updateBanner.css';

interface UpdateBannerProps {
  info: VersionInfo | null;
  onDismiss: () => void;
}

export function UpdateBanner({ info, onDismiss }: UpdateBannerProps) {
  const visible = useMemo(() => {
    if (!info) return false;
    if (!isUpdateAvailable(info)) return false;
    if (isUpdateDismissed(info.latest.version)) return false;
    return true;
  }, [info]);

  if (!visible || !info) return null;

  const targetUrl = pickDownloadUrl(info);
  const handleDownload = () => {
    if (targetUrl) {
      window.open(targetUrl, '_blank', 'noopener,noreferrer');
    }
  };
  const handleDismiss = () => {
    dismissUpdate(info.latest.version);
    onDismiss();
  };

  return (
    <div className="update-banner" role="alert">
      <span className="update-banner__icon">🎉</span>
      <div className="update-banner__body">
        <span className="update-banner__title">
          TokenMind v{info.latest.version} 已发布
          <span className="update-banner__version-current">
            (当前 v{APP_VERSION})
          </span>
        </span>
        {info.latest.release_notes ? (
          <span className="update-banner__notes">
            {info.latest.release_notes}
          </span>
        ) : null}
      </div>
      <div className="update-banner__actions">
        {targetUrl ? (
          <button
            type="button"
            className="update-banner__primary"
            onClick={handleDownload}
          >
            立即下载
          </button>
        ) : null}
        <button
          type="button"
          className="update-banner__secondary"
          onClick={handleDismiss}
        >
          跳过此版本
        </button>
      </div>
    </div>
  );
}
