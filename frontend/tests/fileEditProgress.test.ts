/**
 * Tests for chatStore.applySessionFileEditProgress — the WebSocket handler
 * that converts a stream of file_edit_progress frames into a single
 * timeline row per call_id, updated in place as new deltas arrive.
 *
 * The shape of the events here mirrors what the Python FileEditTracker
 * emits (see tests/test_file_edit_tracker.py and
 * tokenmind/agent/file_edit_tracker.py).
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { useChatStore } from '../src/stores/chatStore';
import type { FileEditEvent } from '../src/stores/chatStore';

const SID = 'web:test';

const EMPTY_SLICE = {
  messages: [],
  toolCalls: [],
  timelineEvents: [],
  activeTool: null,
  isLoading: false,
  currentTurnId: 'turn-1',
  linkedKnowledgeBaseIds: [],
  activeWikiKbId: null,
  pendingApproval: null,
  pendingMessages: [],
  sessionExecTrusted: false,
};

function reset(): void {
  // The store routes updates to top-level fields when ``currentSession``
  // matches; otherwise to ``sessionsState[id]``. We pin currentSession to
  // a different value so our writes land in the per-session slice, which
  // is what the WebSocket handler does in production for non-foreground
  // sessions.
  useChatStore.setState({
    currentSession: 'other-session',
    sessionsState: { [SID]: { ...EMPTY_SLICE } },
  });
}

function sliceEvents() {
  return useChatStore.getState().sessionsState[SID]?.timelineEvents ?? [];
}

function ev(over: Partial<FileEditEvent> = {}): FileEditEvent {
  return {
    version: 1,
    call_id: 'call_1',
    tool: 'edit_file',
    path: 'src/foo.py',
    phase: 'start',
    added: 0,
    deleted: 0,
    approximate: true,
    status: 'editing',
    ...over,
  };
}

test('first file_edit_progress event adds a new timeline row', () => {
  reset();
  useChatStore.getState().applySessionFileEditProgress(SID, ev({ added: 3, deleted: 1 }));
  const events = sliceEvents();
  assert.equal(events.length, 1);
  assert.equal(events[0].type, 'file_edit_progress');
  assert.equal(events[0].fileEdit?.added, 3);
  assert.equal(events[0].fileEdit?.deleted, 1);
  assert.equal(events[0].toolName, 'edit_file');
  assert.equal(events[0].content, 'src/foo.py');
});

test('subsequent events for the same call_id update in place', () => {
  reset();
  const api = useChatStore.getState();
  api.applySessionFileEditProgress(SID, ev({ added: 1, deleted: 0 }));
  api.applySessionFileEditProgress(SID, ev({ added: 10, deleted: 2 }));
  api.applySessionFileEditProgress(SID, ev({ added: 22, deleted: 4 }));

  const events = sliceEvents();
  assert.equal(events.length, 1, 'should still be a single timeline row');
  assert.equal(events[0].fileEdit?.added, 22);
  assert.equal(events[0].fileEdit?.deleted, 4);
});

test('different call_ids get separate rows', () => {
  reset();
  const api = useChatStore.getState();
  api.applySessionFileEditProgress(SID, ev({ call_id: 'a', path: 'x.txt', added: 1 }));
  api.applySessionFileEditProgress(SID, ev({ call_id: 'b', path: 'y.txt', added: 2 }));

  const events = sliceEvents();
  assert.equal(events.length, 2);
  const paths = events.map((e) => e.fileEdit?.path).sort();
  assert.deepEqual(paths, ['x.txt', 'y.txt']);
});

test('end-phase event updates status without adding a new row', () => {
  reset();
  const api = useChatStore.getState();
  api.applySessionFileEditProgress(SID, ev({ added: 5, deleted: 1, status: 'editing', approximate: true }));
  api.applySessionFileEditProgress(
    SID,
    ev({ phase: 'end', added: 7, deleted: 2, status: 'done', approximate: false }),
  );

  const events = sliceEvents();
  assert.equal(events.length, 1);
  assert.equal(events[0].fileEdit?.phase, 'end');
  assert.equal(events[0].fileEdit?.status, 'done');
  assert.equal(events[0].fileEdit?.added, 7);
  assert.equal(events[0].fileEdit?.approximate, false);
});

test('error-phase event carries the error message through to detail', () => {
  reset();
  const api = useChatStore.getState();
  api.applySessionFileEditProgress(
    SID,
    ev({
      phase: 'error',
      status: 'error',
      error: 'Error: read_file required first',
    }),
  );

  const events = sliceEvents();
  assert.equal(events.length, 1);
  assert.equal(events[0].fileEdit?.phase, 'error');
  assert.ok((events[0].detail || '').includes('read_file'));
});
