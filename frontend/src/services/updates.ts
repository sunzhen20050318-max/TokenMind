/**
 * Update-channel client.
 *
 * Pulls a static `versions.json` from a public CDN-style URL on app start
 * and every 6 hours. Compares against the bundled `APP_VERSION` to surface
 * a "new version" banner, and surfaces fresh announcements as toasts.
 *
 * Everything is best-effort: network failures, malformed JSON, or missing
 * fields silently degrade to "no update info" rather than breaking the app.
 */

import { APP_VERSION } from '../version';
import type {
  Announcement,
  BellItem,
  VersionInfo,
} from '../types/updates';

const VERSIONS_URL =
  'https://gitee.com/sun124578963_0/TokenMind/raw/main/versions.json';

const CACHE_KEY = 'tokenmind:updates:cache';
const CACHE_TIME_KEY = 'tokenmind:updates:cached_at';
const DISMISSED_VERSIONS_KEY = 'tokenmind:updates:dismissed_versions';
const READ_ANNOUNCEMENTS_KEY = 'tokenmind:updates:read_announcements';
const SEEN_IN_TOAST_KEY = 'tokenmind:updates:seen_in_toast';
const RECEIVED_AT_KEY = 'tokenmind:updates:received_at';

export const POLL_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6 hours
export const BELL_TTL_MS = 15 * 24 * 60 * 60 * 1000; // 15 days

export async function fetchVersionInfo(
  options: { forceRefresh?: boolean } = {},
): Promise<VersionInfo | null> {
  if (!options.forceRefresh) {
    const cached = readCachedInfo();
    if (cached) return cached;
  }

  try {
    const res = await fetch(VERSIONS_URL, { cache: 'no-cache' });
    if (!res.ok) return readCachedInfo();
    const raw = (await res.json()) as VersionInfo;
    if (!raw || typeof raw !== 'object' || !raw.latest?.version) {
      return readCachedInfo();
    }
    writeCache(raw);
    return raw;
  } catch {
    return readCachedInfo();
  }
}

function readCachedInfo(): VersionInfo | null {
  try {
    const cachedAt = Number(localStorage.getItem(CACHE_TIME_KEY) || 0);
    if (Date.now() - cachedAt > POLL_INTERVAL_MS) return null;
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as VersionInfo) : null;
  } catch {
    return null;
  }
}

function writeCache(info: VersionInfo): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(info));
    localStorage.setItem(CACHE_TIME_KEY, String(Date.now()));
  } catch {
    // localStorage might be disabled or full; not fatal
  }
}

/**
 * Compare two semver-like version strings.
 * Returns negative if a < b, zero if equal, positive if a > b.
 * Tolerant: non-numeric segments compare lexicographically.
 */
export function compareVersions(a: string, b: string): number {
  const partsA = a.split(/[.+-]/);
  const partsB = b.split(/[.+-]/);
  const len = Math.max(partsA.length, partsB.length);
  for (let i = 0; i < len; i++) {
    const x = partsA[i] ?? '0';
    const y = partsB[i] ?? '0';
    const nx = Number(x);
    const ny = Number(y);
    if (Number.isFinite(nx) && Number.isFinite(ny)) {
      if (nx !== ny) return nx - ny;
    } else if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}

export function isUpdateAvailable(info: VersionInfo | null): boolean {
  if (!info?.latest?.version) return false;
  return compareVersions(APP_VERSION, info.latest.version) < 0;
}

export function isUpdateDismissed(version: string): boolean {
  const set = readDismissedVersions();
  return set.has(version);
}

export function dismissUpdate(version: string): void {
  const set = readDismissedVersions();
  set.add(version);
  try {
    localStorage.setItem(DISMISSED_VERSIONS_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

function readDismissedVersions(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_VERSIONS_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function getActiveAnnouncements(
  info: VersionInfo | null,
): Announcement[] {
  if (!info?.announcements?.length) return [];
  const now = Date.now();
  const read = readReadAnnouncements();
  return info.announcements.filter((ann) => {
    if (!ann.id || !ann.title) return false;
    if (read.has(ann.id)) return false;
    if (ann.starts_at && Date.parse(ann.starts_at) > now) return false;
    if (ann.expires_at && Date.parse(ann.expires_at) < now) return false;
    if (ann.min_version && compareVersions(APP_VERSION, ann.min_version) < 0) {
      return false;
    }
    if (ann.max_version && compareVersions(APP_VERSION, ann.max_version) > 0) {
      return false;
    }
    return true;
  });
}

export function markAnnouncementRead(id: string): void {
  const set = readReadAnnouncements();
  set.add(id);
  try {
    localStorage.setItem(READ_ANNOUNCEMENTS_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

function readReadAnnouncements(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_ANNOUNCEMENTS_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

/**
 * Toast-only filter: announcements that are still active *and* never shown
 * in a toast before. The bell panel uses {@link getActiveAnnouncements} which
 * is keyed on `read` instead, so closing a toast does not silently remove the
 * item from the bell.
 */
export function getNewToastAnnouncements(
  info: VersionInfo | null,
): Announcement[] {
  const active = getActiveAnnouncements(info);
  const seen = readSeenInToast();
  return active.filter((ann) => !seen.has(ann.id));
}

export function markAnnouncementSeenInToast(id: string): void {
  const set = readSeenInToast();
  set.add(id);
  try {
    localStorage.setItem(SEEN_IN_TOAST_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

function readSeenInToast(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_IN_TOAST_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

/**
 * Best-effort browser OS detection. Returns the key used in
 * `LatestRelease.downloads`, defaulting to download_page when unknown.
 */
export function detectOS(): 'macos' | 'windows' | 'linux' | 'unknown' {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  if (/Mac|iPhone|iPad|iPod/i.test(ua)) return 'macos';
  if (/Windows|Win64|Win32/i.test(ua)) return 'windows';
  if (/Linux/i.test(ua)) return 'linux';
  return 'unknown';
}

export function pickDownloadUrl(info: VersionInfo): string | null {
  const os = detectOS();
  const downloads = info.latest.downloads;
  if (downloads) {
    const url =
      os !== 'unknown' ? downloads[os] : undefined;
    if (url) return url;
  }
  return info.latest.download_page ?? null;
}

/* ===================================================================== *
 * Bell-panel inbox: unified announcements + version-update items, with
 * a 15-day TTL keyed off the client's first-seen timestamp. Read items
 * stay visible (greyed) until the TTL elapses; the badge counts unread.
 * ===================================================================== */

function readReceivedMap(): Record<string, number> {
  try {
    const raw = localStorage.getItem(RECEIVED_AT_KEY);
    return raw ? (JSON.parse(raw) as Record<string, number>) : {};
  } catch {
    return {};
  }
}

function writeReceivedMap(map: Record<string, number>): void {
  try {
    localStorage.setItem(RECEIVED_AT_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

/** Stamp first-sighting timestamps for any unseen items, drop entries
 * past the TTL, and persist. Called once at the top of getBellItems. */
function reconcileReceived(ids: string[]): Record<string, number> {
  const map = readReceivedMap();
  const now = Date.now();
  let dirty = false;
  for (const id of ids) {
    if (!map[id]) {
      map[id] = now;
      dirty = true;
    }
  }
  // GC entries outside the TTL window so the map doesn't grow forever.
  for (const id of Object.keys(map)) {
    if (now - map[id] > BELL_TTL_MS) {
      delete map[id];
      dirty = true;
    }
  }
  if (dirty) writeReceivedMap(map);
  return map;
}

/** Build the bell-panel item list. Includes:
 *  - active announcements (within their date/version window)
 *  - the latest version when newer than the running APP_VERSION
 * Each item is filtered by the 15-day TTL and sorted newest-first. */
export function getBellItems(info: VersionInfo | null): BellItem[] {
  if (!info) return [];

  const now = Date.now();
  const cutoff = now - BELL_TTL_MS;
  const readSet = readReadAnnouncements();

  const candidateIds: string[] = [];
  const candidates: BellItem[] = [];

  // -------- announcements --------
  if (Array.isArray(info.announcements)) {
    for (const ann of info.announcements) {
      if (!ann.id || !ann.title) continue;
      if (ann.starts_at && Date.parse(ann.starts_at) > now) continue;
      if (ann.expires_at && Date.parse(ann.expires_at) < now) continue;
      if (ann.min_version && compareVersions(APP_VERSION, ann.min_version) < 0) continue;
      if (ann.max_version && compareVersions(APP_VERSION, ann.max_version) > 0) continue;
      candidateIds.push(ann.id);
      candidates.push({
        id: ann.id,
        type: 'announcement',
        title: ann.title,
        message: ann.message,
        level: ann.level ?? 'info',
        receivedAt: 0,
        isRead: readSet.has(ann.id),
        link: ann.link,
      });
    }
  }

  // -------- version update --------
  if (
    info.latest?.version &&
    compareVersions(APP_VERSION, info.latest.version) < 0
  ) {
    const versionId = `version-${info.latest.version}`;
    candidateIds.push(versionId);
    candidates.push({
      id: versionId,
      type: 'version',
      title: `新版本 v${info.latest.version} 已发布`,
      message: info.latest.release_notes ?? '点击查看更新内容并下载最新版本。',
      level: 'info',
      receivedAt: 0,
      isRead: readSet.has(versionId),
      downloadUrl: pickDownloadUrl(info) ?? undefined,
    });
  }

  // Stamp/refresh first-seen timestamps now that we know the candidate set.
  const receivedMap = reconcileReceived(candidateIds);

  return candidates
    .map((item) => ({ ...item, receivedAt: receivedMap[item.id] ?? now }))
    .filter((item) => item.receivedAt >= cutoff)
    .sort((a, b) => b.receivedAt - a.receivedAt);
}

export function getUnreadBellCount(info: VersionInfo | null): number {
  return getBellItems(info).filter((item) => !item.isRead).length;
}

export function markBellItemRead(id: string): void {
  // Reuse the announcements read-set; version IDs (`version-x.y.z`) are
  // namespaced so they can't collide with announcement IDs.
  markAnnouncementRead(id);
}

export function markAllBellItemsRead(info: VersionInfo | null): void {
  const items = getBellItems(info);
  if (items.length === 0) return;
  const set = readReadAnnouncements();
  for (const item of items) set.add(item.id);
  try {
    localStorage.setItem(READ_ANNOUNCEMENTS_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}
