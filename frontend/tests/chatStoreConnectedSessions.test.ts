import test from 'node:test';
import assert from 'node:assert/strict';

import { useChatStore } from '../src/stores/chatStore';

// chatStore is a singleton; reset the connection set between tests so each
// case observes a clean slate rather than carrying over from neighbours.
function reset(): void {
  useChatStore.setState({ connectedSessions: new Set<string>() });
}

test('setSessionConnected: empty initially', () => {
  reset();
  assert.equal(useChatStore.getState().connectedSessions.size, 0);
});

test('setSessionConnected(true): adds the session', () => {
  reset();
  useChatStore.getState().setSessionConnected('web:abc', true);
  const set = useChatStore.getState().connectedSessions;
  assert.equal(set.size, 1);
  assert.equal(set.has('web:abc'), true);
});

test('setSessionConnected(true) twice: idempotent — Set reference unchanged', () => {
  reset();
  useChatStore.getState().setSessionConnected('s1', true);
  const refBefore = useChatStore.getState().connectedSessions;
  useChatStore.getState().setSessionConnected('s1', true);
  const refAfter = useChatStore.getState().connectedSessions;
  // Same reference proves no spurious re-render fires for subscribers
  // selecting on connectedSessions.
  assert.equal(refBefore, refAfter);
  assert.equal(refAfter.size, 1);
});

test('setSessionConnected: tracks multiple sessions independently', () => {
  reset();
  const api = useChatStore.getState();
  api.setSessionConnected('s1', true);
  api.setSessionConnected('s2', true);
  api.setSessionConnected('s3', true);

  const set = useChatStore.getState().connectedSessions;
  assert.equal(set.size, 3);
  assert.deepEqual([...set].sort(), ['s1', 's2', 's3']);
});

test('setSessionConnected(false): removes only the named session', () => {
  reset();
  const api = useChatStore.getState();
  api.setSessionConnected('s1', true);
  api.setSessionConnected('s2', true);
  api.setSessionConnected('s1', false);

  const set = useChatStore.getState().connectedSessions;
  assert.equal(set.size, 1);
  assert.equal(set.has('s1'), false);
  assert.equal(set.has('s2'), true);
});

test('setSessionConnected(false) on absent session: no-op, reference unchanged', () => {
  reset();
  const refBefore = useChatStore.getState().connectedSessions;
  useChatStore.getState().setSessionConnected('never-was', false);
  const refAfter = useChatStore.getState().connectedSessions;
  assert.equal(refBefore, refAfter);
});

test('setSessionConnected: each transition produces a NEW Set reference', () => {
  // This is the linchpin for React reactivity. zustand only notifies
  // subscribers when the slice value changes by Object.is — if we mutated
  // the existing Set instead of replacing it, no re-render would fire and
  // we'd recreate the original "input box stuck" bug.
  reset();
  const api = useChatStore.getState();

  api.setSessionConnected('s1', true);
  const ref1 = useChatStore.getState().connectedSessions;

  api.setSessionConnected('s2', true);
  const ref2 = useChatStore.getState().connectedSessions;
  assert.notEqual(ref1, ref2);

  api.setSessionConnected('s1', false);
  const ref3 = useChatStore.getState().connectedSessions;
  assert.notEqual(ref2, ref3);
});
