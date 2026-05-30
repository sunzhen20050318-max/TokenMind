import test from 'node:test';
import assert from 'node:assert/strict';

import { computeContextGauge } from '../src/components/Chat/contextGauge';

// The chat-window ring reuses the same data the /status card shows:
// the most recent prompt-token count vs the compaction threshold.

test('computeContextGauge: unavailable without threshold or prompt tokens', () => {
  assert.equal(computeContextGauge(null, 65536).available, false);
  assert.equal(computeContextGauge(1000, null).available, false);
  assert.equal(computeContextGauge(0, 65536).available, false);
});

test('computeContextGauge: low usage is a calm/normal gray ring', () => {
  const g = computeContextGauge(6553, 65536); // ~10% used
  assert.equal(g.available, true);
  assert.equal(g.usedPct, 10);
  assert.equal(g.remainingPct, 90);
  assert.equal(g.level, 'normal');
  assert.equal(g.color, '#cfcfcf');
});

test('computeContextGauge: mid usage warns in orange', () => {
  const g = computeContextGauge(Math.round(65536 * 0.6), 65536);
  assert.equal(g.usedPct, 60);
  assert.equal(g.level, 'warn');
  assert.equal(g.color, '#d9a366');
});

test('computeContextGauge: high usage is critical red with little remaining', () => {
  const g = computeContextGauge(Math.round(65536 * 0.9), 65536);
  assert.equal(g.usedPct, 90);
  assert.equal(g.remainingPct, 10);
  assert.equal(g.level, 'critical');
  assert.equal(g.color, '#d96c6c');
});

test('computeContextGauge: over threshold clamps to full / zero remaining', () => {
  const g = computeContextGauge(80000, 65536);
  assert.equal(g.usedPct, 100);
  assert.equal(g.remainingPct, 0);
  assert.equal(g.remainingTokens, 0);
});

test('computeContextGauge: exposes total and a remaining/total tooltip', () => {
  const g = computeContextGauge(6553, 65536); // remaining 58983
  assert.equal(g.totalTokens, 65536);
  // Tooltip shows remaining and total, plus the click-to-compact hint.
  assert.match(g.title, /剩余/);
  assert.match(g.title, /总/);
  assert.ok(g.title.includes('59.0k'), `remaining in title: ${g.title}`);
  assert.ok(g.title.includes('65.5k'), `total in title: ${g.title}`);
  assert.match(g.title, /压缩/);
});
