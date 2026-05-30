import test from 'node:test';
import assert from 'node:assert/strict';

import { channelRuntimeBadge } from '../src/pages/channelStatusBadge';

// Runtime badge only makes sense for enabled channels: a disabled channel
// isn't expected to be connected, so showing "离线" there would be noise.

test('channelRuntimeBadge: enabled and running is online', () => {
  assert.deepEqual(channelRuntimeBadge(true, true), { label: '在线', tone: 'online' });
});

test('channelRuntimeBadge: enabled but not running is offline', () => {
  assert.deepEqual(channelRuntimeBadge(true, false), { label: '离线', tone: 'offline' });
});

test('channelRuntimeBadge: disabled channel shows no runtime badge', () => {
  assert.equal(channelRuntimeBadge(false, false), null);
  assert.equal(channelRuntimeBadge(false, true), null);
});
