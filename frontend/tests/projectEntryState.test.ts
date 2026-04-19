import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProjectEntryState } from '../src/components/Projects/projectEntryState';

test('buildProjectEntryState returns an inline empty hint for empty projects', () => {
  const state = buildProjectEntryState({
    projectName: '测试项目',
    sessions: [],
  });

  assert.equal(state.title, '测试项目');
  assert.equal(state.showEmptyHint, true);
  assert.match(state.emptyHint, /还没有项目聊天/);
});

test('buildProjectEntryState disables the empty hint when project sessions exist', () => {
  const state = buildProjectEntryState({
    projectName: '测试项目',
    sessions: [{ session_id: 'web:s1', title: '问候交流', message_count: 2 }],
  });

  assert.equal(state.showEmptyHint, false);
});
