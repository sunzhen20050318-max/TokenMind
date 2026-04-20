import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { DEFAULT_OVERLAY_HOST_ID, ensureOverlayHost } from './overlayHost';

interface OverlayPortalProps {
  children: ReactNode;
  hostId?: string;
}

export function OverlayPortal({
  children,
  hostId = DEFAULT_OVERLAY_HOST_ID,
}: OverlayPortalProps) {
  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(children, ensureOverlayHost(document, hostId));
}
