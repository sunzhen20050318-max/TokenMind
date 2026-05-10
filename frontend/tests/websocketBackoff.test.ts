import test from 'node:test';
import assert from 'node:assert/strict';

import { backoffDelay } from '../src/services/websocket';

test('backoffDelay: first attempt waits the base delay (1s)', () => {
  assert.equal(backoffDelay(1), 1000);
});

test('backoffDelay: doubles each attempt — 1s, 2s, 4s, 8s, 16s', () => {
  assert.equal(backoffDelay(1), 1_000);
  assert.equal(backoffDelay(2), 2_000);
  assert.equal(backoffDelay(3), 4_000);
  assert.equal(backoffDelay(4), 8_000);
  assert.equal(backoffDelay(5), 16_000);
});

test('backoffDelay: caps at 30s and never exceeds it', () => {
  // 2^5 * 1000 = 32_000, already over the cap
  assert.equal(backoffDelay(6), 30_000);
  assert.equal(backoffDelay(7), 30_000);
  assert.equal(backoffDelay(20), 30_000);
  // Pathological values must still return a sane number, not Infinity
  assert.equal(backoffDelay(10_000), 30_000);
});

test('backoffDelay: defends against zero / negative attempts', () => {
  // attempt 0 falls back to base (clamped exponent 0 → 2^0 = 1)
  assert.equal(backoffDelay(0), 1_000);
  assert.equal(backoffDelay(-3), 1_000);
});
