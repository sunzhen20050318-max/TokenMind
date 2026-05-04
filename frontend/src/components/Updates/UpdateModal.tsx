import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  dismissUpdate,
  isUpdateAvailable,
  isUpdateDismissed,
  pickDownloadUrl,
} from '../../services/updates';
import type { VersionInfo } from '../../types/updates';
import { APP_VERSION } from '../../version';
import './updateModal.css';

interface UpdateModalProps {
  info: VersionInfo | null;
  onDismiss: () => void;
}

/**
 * Centered modal that announces a newer version. Replaces the top banner
 * because users were ignoring the banner. The modal still has three escape
 * hatches so it doesn't feel hostile:
 *   - 立即下载: triggers the download (per-OS URL from versions.json)
 *   - 稍后再说: hides for the current session only (next launch shows again)
 *   - 跳过此版本: persists the version to localStorage; never shown again
 *     until a newer version is published.
 *   - ESC / backdrop click: same as 稍后再说.
 */
export function UpdateModal({ info, onDismiss }: UpdateModalProps) {
  // Per-session "later" decision. Tracks the version string so that a brand
  // new release on the next poll re-opens the modal even within the same
  // tab session.
  const sessionDismissedRef = useRef<string | null>(null);

  const visible =
    !!info &&
    isUpdateAvailable(info) &&
    !isUpdateDismissed(info.latest.version) &&
    sessionDismissedRef.current !== info.latest.version;

  // ESC closes the modal as "later".
  useEffect(() => {
    if (!visible || !info) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        sessionDismissedRef.current = info.latest.version;
        onDismiss();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [visible, info, onDismiss]);

  if (!visible || !info) return null;

  const targetUrl = pickDownloadUrl(info);

  const handleLater = () => {
    sessionDismissedRef.current = info.latest.version;
    onDismiss();
  };

  const handleSkip = () => {
    dismissUpdate(info.latest.version);
    onDismiss();
  };

  const handleDownload = () => {
    if (!targetUrl) return;
    // Use a synthetic <a download> click rather than window.open so the
    // browser triggers a real download for binary URLs (.dmg/.exe) instead
    // of opening a momentary new tab that closes itself.
    const link = document.createElement('a');
    link.href = targetUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.download = '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    sessionDismissedRef.current = info.latest.version;
    onDismiss();
  };

  return (
    <div className="update-modal-backdrop" onClick={handleLater}>
      <div
        className="update-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="update-modal__close"
          onClick={handleLater}
          aria-label="关闭"
        >
          ×
        </button>
        <div className="update-modal__icon" aria-hidden="true">
          🎉
        </div>
        <h2 id="update-modal-title" className="update-modal__title">
          TokenMind v{info.latest.version} 已发布
        </h2>
        <p className="update-modal__current">
          当前版本 v{APP_VERSION}
        </p>
        {info.latest.release_notes ? (
          <div className="update-modal__notes" translate="no">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {info.latest.release_notes}
            </ReactMarkdown>
          </div>
        ) : null}
        <div className="update-modal__actions">
          <button
            type="button"
            className="update-modal__skip"
            onClick={handleSkip}
          >
            跳过此版本
          </button>
          <button
            type="button"
            className="update-modal__later"
            onClick={handleLater}
          >
            稍后再说
          </button>
          {targetUrl ? (
            <button
              type="button"
              className="update-modal__primary"
              onClick={handleDownload}
            >
              立即下载 ↓
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
