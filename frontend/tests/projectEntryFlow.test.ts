import test from 'node:test';
import assert from 'node:assert/strict';
import { createProjectConversation } from '../src/components/Projects/projectEntryFlow';

test('createProjectConversation creates a project session, queues the first message, and returns the session id', async () => {
  const calls: string[] = [];

  const sessionId = await createProjectConversation({
    projectId: 'proj_1',
    message: 'seed the project conversation',
    generateSessionId: () => 'web:test-project-session',
    createProjectSession: async (projectId, nextSessionId) => {
      calls.push(`create:${projectId}:${nextSessionId}`);
    },
    queueSessionStarter: (content, nextSessionId) => {
      calls.push(`queue:${nextSessionId}:${content}`);
    },
  });

  assert.equal(sessionId, 'web:test-project-session');
  assert.deepEqual(calls, [
    'create:proj_1:web:test-project-session',
    'queue:web:test-project-session:seed the project conversation',
  ]);
});

test('createProjectConversation rejects blank messages', async () => {
  await assert.rejects(
    () =>
      createProjectConversation({
        projectId: 'proj_1',
        message: '   ',
        generateSessionId: () => 'web:test-project-session',
        createProjectSession: async () => undefined,
        queueSessionStarter: () => undefined,
      }),
    /message cannot be empty/i
  );
});

test('createProjectConversation uses the generated session id for the queued starter message', async () => {
  let queuedToSessionId = '';

  await createProjectConversation({
    projectId: 'proj_1',
    message: 'create project conversation',
    generateSessionId: () => 'web:project-seeded',
    createProjectSession: async () => undefined,
    queueSessionStarter: (_message, sessionId) => {
      queuedToSessionId = sessionId;
    },
  });

  assert.equal(queuedToSessionId, 'web:project-seeded');
});
