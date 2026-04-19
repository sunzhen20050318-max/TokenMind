import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldRestoreLastSession } from '../src/app/sessionRestoreState';

test('shouldRestoreLastSession blocks global session restore inside project views', () => {
  assert.equal(
    shouldRestoreLastSession({
      appReady: true,
      currentSession: null,
      sessionCount: 3,
      mainView: 'project-home',
      activeProjectId: 'proj_1',
    }),
    false
  );
});

test('shouldRestoreLastSession allows restore on the global chat surface', () => {
  assert.equal(
    shouldRestoreLastSession({
      appReady: true,
      currentSession: null,
      sessionCount: 3,
      mainView: 'chat',
      activeProjectId: null,
    }),
    true
  );
});
