import test from 'node:test';
import assert from 'node:assert/strict';

import { isConnectionStale } from '../src/services/websocket';

// --- isConnectionStale: half-open detection -------------------------------

test('isConnectionStale: fresh activity within a heartbeat window is not stale', () => {
  const now = 100_000;
  // last activity 20s ago, interval 25s + timeout 10s = 35s budget
  assert.equal(isConnectionStale(now - 20_000, now, 25_000, 10_000), false);
});

test('isConnectionStale: no activity past interval+timeout is stale', () => {
  const now = 100_000;
  // 36s of silence exceeds the 35s budget
  assert.equal(isConnectionStale(now - 36_000, now, 25_000, 10_000), true);
});

test('isConnectionStale: exactly at the budget boundary is not stale', () => {
  const now = 100_000;
  assert.equal(isConnectionStale(now - 35_000, now, 25_000, 10_000), false);
});
