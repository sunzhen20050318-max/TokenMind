export const DEFAULT_OVERLAY_HOST_ID = 'tokenmind-overlay-root';

type OverlayHostDocument = Pick<Document, 'getElementById' | 'createElement' | 'body'>;

export function ensureOverlayHost(
  doc: OverlayHostDocument = document,
  hostId = DEFAULT_OVERLAY_HOST_ID
): HTMLElement {
  const existingHost = doc.getElementById(hostId);
  if (existingHost) {
    return existingHost;
  }

  const host = doc.createElement('div');
  host.id = hostId;

  if ('setAttribute' in host && typeof host.setAttribute === 'function') {
    host.setAttribute('data-tokenmind-overlay-root', 'true');
  }

  doc.body.appendChild(host);
  return host;
}
