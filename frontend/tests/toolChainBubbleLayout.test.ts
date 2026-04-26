import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const chatWindowSource = readFileSync(
  resolve(import.meta.dirname, '../src/components/Chat/ChatWindow.tsx'),
  'utf-8'
);

function extractStandaloneToolChainBuilder(source: string): string {
  const start = source.indexOf('const buildStandaloneChain =');
  const end = source.indexOf('const flushPendingStandalone =');
  assert.notEqual(start, -1, 'buildStandaloneChain should exist');
  assert.notEqual(end, -1, 'flushPendingStandalone should follow buildStandaloneChain');
  return source.slice(start, end);
}

test('standalone tool chains render inside the same assistant bubble shell as final replies', () => {
  const builder = extractStandaloneToolChainBuilder(chatWindowSource);

  assert.match(builder, /<MessageBubble\b/);
  assert.match(builder, /embeddedToolChain=/);
  assert.match(builder, /variant="embedded"/);
  assert.doesNotMatch(builder, /className="message-row is-assistant"/);
});
