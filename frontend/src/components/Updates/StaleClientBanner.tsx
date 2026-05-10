import './staleClientBanner.css';

interface StaleClientBannerProps {
  /** Server-reported version that doesn't match what this tab was built with. */
  serverVersion: string;
  onRefresh: () => void;
  onDismiss: () => void;
}

/**
 * Thin banner shown when a periodic /api/status check finds the running
 * server is on a different version than this tab's bundled APP_VERSION.
 *
 * Deliberately does NOT auto-reload — that would discard whatever the user
 * is in the middle of typing/uploading/streaming. The user clicks 立即刷新
 * when they're ready; until then the banner just sits there as a hint.
 */
export function StaleClientBanner({
  serverVersion,
  onRefresh,
  onDismiss,
}: StaleClientBannerProps) {
  return (
    <div className="stale-client-banner" role="status">
      <span className="stale-client-banner__icon" aria-hidden>
        ⚡
      </span>
      <span className="stale-client-banner__text">
        已有新版本 <strong>v{serverVersion}</strong> 可用,刷新页面即可生效。
      </span>
      <button
        type="button"
        className="stale-client-banner__primary"
        onClick={onRefresh}
      >
        立即刷新
      </button>
      <button
        type="button"
        className="stale-client-banner__close"
        onClick={onDismiss}
        aria-label="关闭"
        title="本会话不再提示"
      >
        ×
      </button>
    </div>
  );
}
