/**
 * Copy text to clipboard with a non-secure-context fallback.
 *
 * `navigator.clipboard` is only available in secure contexts (HTTPS or
 * localhost). When TokenMind is opened over LAN HTTP — common when a user
 * accesses the desktop from their phone on the same Wi-Fi — the clipboard
 * API is undefined and a naive call crashes the component. We fall back to
 * the legacy hidden-textarea + `document.execCommand('copy')` path, which
 * still works in plain HTTP.
 *
 * Resolves to `true` on success, `false` when neither path worked.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the legacy path — some sandboxed iframes throw even
      // when the API exists.
    }
  }
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}
