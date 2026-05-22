/**
 * LAN auth secret plumbing.
 *
 * The backend gates non-localhost requests via an ``X-TokenMind-Secret``
 * header (HTTP) or ``?secret=...`` query (WebSocket). When the user opens
 * TokenMind from another device on the same Wi-Fi, the AuthGate prompts
 * them to paste the secret once; we keep it in localStorage and inject it
 * on every subsequent call.
 *
 * Localhost users never see this UI — the middleware bypasses them — so
 * the helpers here are safe no-ops when no secret has ever been stored.
 */

const STORAGE_KEY = 'tokenmind.auth_secret';
const AUTH_HEADER = 'X-TokenMind-Secret';

let cached: string = '';

/** Read once from localStorage and cache. Subsequent calls are O(1). */
export function getAuthSecret(): string {
  if (cached) return cached;
  try {
    cached = window.localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    cached = '';
  }
  return cached;
}

/** Persist the secret. Pass empty string to clear it. */
export function setAuthSecret(value: string): void {
  cached = value || '';
  try {
    if (cached) {
      window.localStorage.setItem(STORAGE_KEY, cached);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Private mode / iframe — keep the in-memory copy at least.
  }
}

/** Append the secret as a query parameter (used by WebSocket URLs). */
export function withSecretQuery(url: string): string {
  const secret = getAuthSecret();
  if (!secret) return url;
  const joiner = url.includes('?') ? '&' : '?';
  return `${url}${joiner}secret=${encodeURIComponent(secret)}`;
}

let installed = false;

/**
 * Monkey-patch ``window.fetch`` so every request to our own backend (any URL
 * starting with ``/api`` or pointing to our backend host) carries the auth
 * header. Idempotent — calling install() multiple times is a no-op.
 */
export function installFetchAuthInterceptor(): void {
  if (installed) return;
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const secret = getAuthSecret();
    if (!secret) return originalFetch(input, init);

    let url: string;
    if (typeof input === 'string') url = input;
    else if (input instanceof URL) url = input.toString();
    else url = input.url;

    // Only inject for our own API surface. Skip cross-origin requests so we
    // don't leak the secret to third parties.
    const isOurApi =
      url.startsWith('/api') ||
      url.startsWith('/ws') ||
      url.startsWith(`${window.location.origin}/api`) ||
      url.startsWith(`${window.location.origin}/ws`);
    if (!isOurApi) return originalFetch(input, init);

    const headers = new Headers(init?.headers);
    if (!headers.has(AUTH_HEADER)) {
      headers.set(AUTH_HEADER, secret);
    }
    return originalFetch(input, { ...init, headers });
  };
}
