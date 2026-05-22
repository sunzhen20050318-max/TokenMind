/**
 * Guards around update-pitching behavior:
 *
 * 1. pickDownloadUrl must reject placeholder strings like "TODO" that we
 *    leave in versions.json before the real binary is uploaded — otherwise
 *    the browser would silently try to GET /TODO and serve back index.html
 *    as the "download".
 *
 * 2. isUpdateAvailable must suppress the "new version available!" modal
 *    when the current platform has no valid download URL, so users don't
 *    see a notification they can't act on.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isUpdateAvailable,
  pickDownloadUrl,
} from '../src/services/updates';
import type { VersionInfo } from '../src/types/updates';

const HIGHER_VERSION = '999.0.0'; // always newer than APP_VERSION

function buildInfo(overrides: Partial<VersionInfo['latest']> = {}): VersionInfo {
  return {
    schema_version: 1,
    latest: {
      version: HIGHER_VERSION,
      released_at: '2026-05-22',
      release_notes: '',
      downloads: { windows: '', macos: '' },
      ...overrides,
    },
    announcements: [],
  };
}

// pickDownloadUrl ───────────────────────────────────────────────────────

test('pickDownloadUrl rejects "TODO" placeholder', () => {
  const info = buildInfo({
    downloads: {
      windows: 'TODO',
      macos: 'TODO',
    },
  });
  assert.equal(pickDownloadUrl(info), null);
});

test('pickDownloadUrl rejects empty string', () => {
  const info = buildInfo({ downloads: { windows: '', macos: '' } });
  assert.equal(pickDownloadUrl(info), null);
});

test('pickDownloadUrl rejects "REPLACE_ME" / "TBD" / "N/A" sentinels', () => {
  for (const sentinel of ['REPLACE_ME', 'replace-me', 'TBD', 'tbd', 'N/A', 'none']) {
    const info = buildInfo({
      downloads: { windows: sentinel, macos: sentinel },
    });
    assert.equal(pickDownloadUrl(info), null, `sentinel ${sentinel!} should be rejected`);
  }
});

test('pickDownloadUrl rejects relative-looking strings', () => {
  const info = buildInfo({
    downloads: {
      windows: '/files/setup.exe',
      macos: 'tokenmind.dmg',
    },
  });
  // Only absolute http(s) URLs allowed — otherwise the browser would
  // resolve relative to the running TokenMind origin.
  assert.equal(pickDownloadUrl(info), null);
});

test('pickDownloadUrl falls back to download_page when platform url invalid', () => {
  const info = buildInfo({
    downloads: { windows: 'TODO', macos: 'TODO' },
    download_page: 'https://example.com/download',
  });
  assert.equal(pickDownloadUrl(info), 'https://example.com/download');
});

test('pickDownloadUrl rejects placeholder download_page too', () => {
  const info = buildInfo({
    downloads: { windows: 'TODO', macos: 'TODO' },
    download_page: 'TODO',
  });
  assert.equal(pickDownloadUrl(info), null);
});

// isUpdateAvailable ────────────────────────────────────────────────────

test('isUpdateAvailable returns false when there is no valid download URL', () => {
  // Newer version on the server, but no actual binary uploaded yet — we
  // shouldn't pitch the user on something they can't get.
  const info = buildInfo({
    downloads: { windows: 'TODO', macos: 'TODO' },
  });
  assert.equal(isUpdateAvailable(info), false);
});

test('isUpdateAvailable returns false when version is null', () => {
  assert.equal(isUpdateAvailable(null), false);
});
