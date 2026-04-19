import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProjectSidebarTree } from '../src/components/Projects/projectSidebarState';

test('buildProjectSidebarTree nests sessions only under the active project', () => {
  const tree = buildProjectSidebarTree({
    projects: [
      { id: 'proj_1', name: 'Project One', created_at: '', updated_at: '', session_count: 2 },
      { id: 'proj_2', name: 'Project Two', created_at: '', updated_at: '', session_count: 1 },
    ],
    activeProjectId: 'proj_1',
    expandedProjectIds: ['proj_1'],
    projectSessions: [
      { session_id: 'web:s1', title: 'Kickoff', message_count: 2, project_id: 'proj_1' },
      { session_id: 'web:s2', title: 'Timeline', message_count: 4, project_id: 'proj_1' },
    ],
  });

  assert.equal(tree.length, 2);
  assert.equal(tree[0].project.id, 'proj_1');
  assert.equal(tree[0].isExpanded, true);
  assert.equal(tree[0].sessions.length, 2);
  assert.equal(tree[1].project.id, 'proj_2');
  assert.equal(tree[1].isExpanded, false);
  assert.equal(tree[1].sessions.length, 0);
});

test('buildProjectSidebarTree exposes active-project sessions as third-level items', () => {
  const tree = buildProjectSidebarTree({
    projects: [{ id: 'proj_1', name: 'Project One', created_at: '', updated_at: '', session_count: 2 }],
    activeProjectId: 'proj_1',
    expandedProjectIds: ['proj_1'],
    projectSessions: [{ session_id: 'web:s1', title: 'Kickoff', message_count: 2, project_id: 'proj_1' }],
  });

  assert.equal(tree[0].sessions[0].title, 'Kickoff');
});

test('buildProjectSidebarTree hides project sessions when the active project is collapsed', () => {
  const tree = buildProjectSidebarTree({
    projects: [{ id: 'proj_1', name: 'Project One', created_at: '', updated_at: '', session_count: 2 }],
    activeProjectId: 'proj_1',
    expandedProjectIds: [],
    projectSessions: [{ session_id: 'web:s1', title: 'Kickoff', message_count: 2, project_id: 'proj_1' }],
  });

  assert.equal(tree[0].isExpanded, false);
  assert.equal(tree[0].sessions.length, 0);
});
