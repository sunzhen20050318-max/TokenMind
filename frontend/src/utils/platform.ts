/**
 * Cross-platform helpers for keyboard shortcuts and OS-specific affordances.
 * `metaKey` is the Command key on macOS and the Windows key on Windows —
 * the canonical "modifier" for shortcuts on macOS, but on Windows we use
 * `ctrlKey` instead. Handlers should always accept both via `event.metaKey
 * || event.ctrlKey`; only the *display* differs.
 */
export const isMac: boolean = (() => {
  if (typeof navigator === 'undefined') return false;
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } })
      .userAgentData?.platform ||
    navigator.platform ||
    navigator.userAgent ||
    '';
  return /Mac|iPod|iPhone|iPad/i.test(platform);
})();

/** Symbol shown to the user for the modifier: `⌘` on macOS, `Ctrl` elsewhere. */
export const modKey: string = isMac ? '⌘' : 'Ctrl';

/**
 * True if the keyboard event carries the platform-appropriate modifier
 * (Command on macOS, Ctrl elsewhere). Use this in `keydown` handlers.
 */
export function hasModKey(event: KeyboardEvent | React.KeyboardEvent): boolean {
  return isMac ? event.metaKey : event.ctrlKey;
}
