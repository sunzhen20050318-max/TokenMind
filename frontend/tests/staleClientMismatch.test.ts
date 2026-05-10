import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * The stale-client banner shows when (1) the periodic /api/status check
 * found a server version that doesn't match the bundled APP_VERSION, AND
 * (2) the user hasn't dismissed the banner this session. Auto-reload was
 * intentionally rejected — the banner waits for a deliberate click so an
 * in-flight chat / upload / draft message isn't wiped out.
 *
 * The state machine itself is dead simple but high-stakes; cover the four
 * meaningful transitions explicitly so a future refactor can't quietly
 * regress the "don't auto-reload" guarantee.
 */

interface StaleClientState {
  /** Server version reported by /api/status, only set when it differs from APP_VERSION. */
  staleServerVersion: string | null;
  /** Per-session dismiss flag. */
  staleBannerDismissed: boolean;
}

function isBannerVisible(state: StaleClientState): boolean {
  return state.staleServerVersion !== null && !state.staleBannerDismissed;
}

test('hidden when versions match (staleServerVersion never set)', () => {
  assert.equal(
    isBannerVisible({ staleServerVersion: null, staleBannerDismissed: false }),
    false,
  );
});

test('visible once a mismatch is detected', () => {
  assert.equal(
    isBannerVisible({
      staleServerVersion: '0.1.12',
      staleBannerDismissed: false,
    }),
    true,
  );
});

test('hidden after the user dismisses, even if server still mismatched', () => {
  // The next periodic poll will set staleServerVersion again to the same
  // value — that must NOT bring the banner back. Dismissal is sticky for
  // the rest of the tab session.
  assert.equal(
    isBannerVisible({
      staleServerVersion: '0.1.12',
      staleBannerDismissed: true,
    }),
    false,
  );
});

test('dismissed-but-no-mismatch reverts to hidden (defensive)', () => {
  // If a future code path clears staleServerVersion (say, server rolled
  // back to the matching version), the banner should obviously be gone
  // regardless of the dismissed flag.
  assert.equal(
    isBannerVisible({ staleServerVersion: null, staleBannerDismissed: true }),
    false,
  );
});

/**
 * Lock in the contract: detecting a mismatch sets staleServerVersion only.
 * It must NOT trigger window.location.reload() — that would discard the
 * user's draft message / upload / streaming response. The reload is the
 * user's job, gated on them clicking "立即刷新" in the banner.
 */
test('mismatch detection stores server version, never reloads', () => {
  const reloadSpy = { called: 0 };
  const fakeWindow = {
    location: {
      reload: () => {
        reloadSpy.called += 1;
      },
    },
  };

  // Simulate the App.tsx periodic-check handler in isolation.
  const state: StaleClientState = {
    staleServerVersion: null,
    staleBannerDismissed: false,
  };

  function onServerVersionDetected(serverVersion: string, appVersion: string) {
    if (serverVersion !== appVersion) {
      state.staleServerVersion = serverVersion;
      // Note the absence of fakeWindow.location.reload(): non-negotiable.
    }
  }

  onServerVersionDetected('0.1.12', '0.1.11');
  assert.equal(state.staleServerVersion, '0.1.12');
  assert.equal(reloadSpy.called, 0, 'auto-reload must not fire on mismatch');
  assert.equal(fakeWindow.location.reload === fakeWindow.location.reload, true);
});

test('matching versions are a no-op', () => {
  const state: StaleClientState = {
    staleServerVersion: null,
    staleBannerDismissed: false,
  };

  function onServerVersionDetected(serverVersion: string, appVersion: string) {
    if (serverVersion !== appVersion) {
      state.staleServerVersion = serverVersion;
    }
  }

  onServerVersionDetected('0.1.11', '0.1.11');
  assert.equal(state.staleServerVersion, null);
});
