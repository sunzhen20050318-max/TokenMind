/**
 * Regression guard: a freshly-created session that doesn't yet exist on
 * the backend gets an optimistic placeholder in ``sessions``. That
 * placeholder MUST stamp ``created_at`` / ``updated_at`` with "now",
 * otherwise the sidebar's time-bucket grouping (sessionBucket in
 * Sidebar.tsx) falls back to the ``更早`` (earlier) bucket because both
 * fields are undefined.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { useChatStore } from '../src/stores/chatStore';

function reset(): void {
  useChatStore.setState({
    sessions: [],
    projectSessions: [],
    currentSession: null,
    activeProjectId: null,
    activeProject: null,
    projects: [],
  });
}

test('setCurrentSession stamps a new session with now-ish timestamps', () => {
  reset();
  const newId = 'web:new-session-test';
  const before = Date.now();
  useChatStore.getState().setCurrentSession(newId);
  const after = Date.now();

  const created = useChatStore.getState().sessions.find((s) => s.session_id === newId);
  assert.ok(created, 'session should be inserted into the sessions array');
  assert.ok(created!.created_at, 'created_at should be set');
  assert.ok(created!.updated_at, 'updated_at should be set');

  const createdAtMs = new Date(created!.created_at!).getTime();
  const updatedAtMs = new Date(created!.updated_at!).getTime();
  assert.ok(
    createdAtMs >= before && createdAtMs <= after,
    `created_at (${createdAtMs}) should be within [${before}, ${after}]`,
  );
  assert.ok(
    updatedAtMs >= before && updatedAtMs <= after,
    `updated_at (${updatedAtMs}) should be within [${before}, ${after}]`,
  );
});

test('setCurrentSession on an existing session does not stamp timestamps', () => {
  reset();
  // Pre-populate sessions with an existing entry that has its own
  // (older) timestamps from the backend.
  useChatStore.setState({
    sessions: [{
      session_id: 'web:existing',
      message_count: 5,
      created_at: '2026-01-01T10:00:00.000Z',
      updated_at: '2026-01-01T11:00:00.000Z',
    }],
  });

  useChatStore.getState().setCurrentSession('web:existing');

  // The existing session must still be there with its original timestamps,
  // not a duplicate with "now" timestamps.
  const matches = useChatStore.getState().sessions.filter(
    (s) => s.session_id === 'web:existing',
  );
  assert.equal(matches.length, 1, 'no duplicates allowed');
  assert.equal(matches[0].created_at, '2026-01-01T10:00:00.000Z');
});
