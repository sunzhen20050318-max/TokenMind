import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureOverlayHost } from '../src/components/Overlay/overlayHost';

function createFakeDocument() {
  const nodes = new Map<string, { id: string }>();
  const appended: { id: string }[] = [];

  return {
    appended,
    document: {
      getElementById(id: string) {
        return nodes.get(id) ?? null;
      },
      createElement() {
        return { id: '' };
      },
      body: {
        appendChild(node: { id: string }) {
          appended.push(node);
          nodes.set(node.id, node);
        },
      },
    },
  };
}

test('ensureOverlayHost creates an overlay host once and reuses it afterwards', () => {
  const fake = createFakeDocument();

  const first = ensureOverlayHost(fake.document as never);
  const second = ensureOverlayHost(fake.document as never);

  assert.equal(first.id, 'tokenmind-overlay-root');
  assert.equal(second, first);
  assert.equal(fake.appended.length, 1);
});

test('ensureOverlayHost honors a custom host id', () => {
  const fake = createFakeDocument();

  const host = ensureOverlayHost(fake.document as never, 'custom-overlay-root');

  assert.equal(host.id, 'custom-overlay-root');
  assert.equal(fake.appended.length, 1);
});
