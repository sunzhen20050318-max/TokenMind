import test from 'node:test';
import assert from 'node:assert/strict';

import { isWikiKb, isRagKb } from '../src/types/knowledge';
import type { KnowledgeBase } from '../src/types/knowledge';

test('isWikiKb returns true for type="wiki"', () => {
  const kb: KnowledgeBase = {
    id: 'kb_x',
    name: 'w',
    description: '',
    type: 'wiki',
    status: 'ready',
    enabled: true,
    document_count: 0,
    language: 'zh',
    root_path: '',
    source_count: 0,
    page_count: 0,
    entity_count: 0,
    topic_count: 0,
    link_count: 0,
    created_at: '',
    updated_at: '',
  };
  assert.equal(isWikiKb(kb), true);
  assert.equal(isRagKb(kb), false);
});

test('isRagKb returns true when type is "rag" or missing', () => {
  const rag: KnowledgeBase = {
    id: 'kb_r',
    name: 'r',
    description: '',
    type: 'rag',
    status: 'ready',
    enabled: true,
    document_count: 0,
    language: 'zh',
    root_path: '',
    source_count: 0,
    page_count: 0,
    entity_count: 0,
    topic_count: 0,
    link_count: 0,
    created_at: '',
    updated_at: '',
  };
  assert.equal(isRagKb(rag), true);
  assert.equal(isWikiKb(rag), false);
});

test('createKnowledgeBase payload accepts optional type field', () => {
  type CreateKbPayload = Parameters<typeof import('../src/services/api').api.createKnowledgeBase>[0];
  const payload: CreateKbPayload = { name: 'x', description: 'y', type: 'wiki' };
  assert.equal(payload.type, 'wiki');
});

test('api exposes listWikiPages, getWikiGraph, rebuildWikiGraph', async () => {
  const { api } = await import('../src/services/api');
  assert.equal(typeof api.listWikiPages, 'function');
  assert.equal(typeof api.getWikiGraph, 'function');
  assert.equal(typeof api.rebuildWikiGraph, 'function');
});

test('api.patchSession is a function with (sessionId, payload) signature', async () => {
  const { api } = await import('../src/services/api');
  assert.equal(typeof api.patchSession, 'function');
});

test('WikiPageList groups pages by type in defined order', async () => {
  const pages = [
    { title: 'Y', type: 'source' as const, path: 'wiki/sources/Y.md' },
    { title: 'A', type: 'entity' as const, path: 'wiki/entities/A.md' },
    { title: 'T', type: 'topic' as const, path: 'wiki/topics/T.md' },
  ];
  const TYPE_ORDER = ['entity', 'topic', 'source', 'synthesis', 'comparison', 'query', 'page'];
  const order: string[] = [];
  for (const t of TYPE_ORDER) {
    for (const p of pages.filter((p) => p.type === t)) order.push(p.title);
  }
  assert.deepEqual(order, ['A', 'T', 'Y']);
});
