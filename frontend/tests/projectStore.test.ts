import test from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../src/services/api';
import { useChatStore } from '../src/stores/chatStore';

const INITIAL_STATE = useChatStore.getState();

test('openProject keeps the active project payload for project-space titles', async (t) => {
  const originalGetProject = api.getProject;

  useChatStore.setState(INITIAL_STATE, true);

  api.getProject = async () => ({
    project: {
      id: 'proj_1',
      name: 'Project Alpha',
      created_at: '',
      updated_at: '',
      session_count: 0,
    },
    sessions: [],
  });

  t.after(() => {
    api.getProject = originalGetProject;
    useChatStore.setState(INITIAL_STATE, true);
  });

  await useChatStore.getState().openProject('proj_1');

  assert.equal(useChatStore.getState().activeProject?.name, 'Project Alpha');
});

test('setCurrentSession restores project context from a project session', () => {
  useChatStore.setState(
    {
      ...INITIAL_STATE,
      projects: [{ id: 'proj_1', name: 'Project Alpha', created_at: '', updated_at: '', session_count: 1 }],
      activeProjectId: null,
      activeProject: null,
      projectSessions: [{ session_id: 'web:s1', title: 'Planning', message_count: 2, project_id: 'proj_1' }],
    },
    true
  );

  useChatStore.getState().setCurrentSession('web:s1');

  assert.equal(useChatStore.getState().activeProjectId, 'proj_1');
  assert.equal(useChatStore.getState().activeProject?.name, 'Project Alpha');
});

test('queuePendingSessionStarter stores a one-time starter message for the new project chat', () => {
  useChatStore.setState(INITIAL_STATE, true);

  useChatStore.getState().queuePendingSessionStarter('web:new-project-chat', 'Kick off the new project chat');

  assert.deepEqual(useChatStore.getState().pendingSessionStarter, {
    sessionId: 'web:new-project-chat',
    message: 'Kick off the new project chat',
  });

  useChatStore.getState().clearPendingSessionStarter('web:new-project-chat');

  assert.equal(useChatStore.getState().pendingSessionStarter, null);
});

test('deleteProject removes the active project and clears project view state', async (t) => {
  const originalDeleteProject = api.deleteProject;

  useChatStore.setState(
    {
      ...INITIAL_STATE,
      projects: [{ id: 'proj_1', name: 'Project Alpha', created_at: '', updated_at: '', session_count: 1 }],
      activeProjectId: 'proj_1',
      activeProject: { id: 'proj_1', name: 'Project Alpha', created_at: '', updated_at: '', session_count: 1 },
      projectSessions: [{ session_id: 'web:s1', title: 'Kickoff', message_count: 2, project_id: 'proj_1' }],
      currentSession: 'web:s1',
    },
    true
  );

  api.deleteProject = async () => ({
    success: true,
    project_id: 'proj_1',
    deleted_session_count: 1,
  });

  t.after(() => {
    api.deleteProject = originalDeleteProject;
    useChatStore.setState(INITIAL_STATE, true);
  });

  await useChatStore.getState().deleteProject('proj_1');

  assert.equal(useChatStore.getState().projects.length, 0);
  assert.equal(useChatStore.getState().activeProjectId, null);
  assert.equal(useChatStore.getState().activeProject, null);
  assert.equal(useChatStore.getState().projectSessions.length, 0);
  assert.equal(useChatStore.getState().currentSession, null);
});
