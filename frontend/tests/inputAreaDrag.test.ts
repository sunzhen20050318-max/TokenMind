import test from 'node:test';
import assert from 'node:assert/strict';

import { hasFileTransfer } from '../src/components/Chat/inputAreaDrag';

test('hasFileTransfer detects file drags', () => {
  assert.equal(hasFileTransfer(['text/plain', 'Files']), true);
});

test('hasFileTransfer ignores non-file drags', () => {
  assert.equal(hasFileTransfer(['text/plain']), false);
  assert.equal(hasFileTransfer(null), false);
});
