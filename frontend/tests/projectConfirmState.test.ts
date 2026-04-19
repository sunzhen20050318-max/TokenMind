import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProjectConfirmContent } from '../src/components/Projects/projectConfirmState';

test('buildProjectConfirmContent returns project deletion copy with the project name', () => {
  const content = buildProjectConfirmContent('delete-project', 'Alpha');

  assert.equal(content.title, '删除项目');
  assert.match(content.message, /Alpha/);
  assert.equal(content.confirmLabel, '删除项目');
});

test('buildProjectConfirmContent returns session deletion copy', () => {
  const content = buildProjectConfirmContent('delete-project-session');

  assert.equal(content.title, '删除项目会话');
  assert.match(content.message, /当前项目/);
  assert.equal(content.confirmLabel, '删除会话');
});
