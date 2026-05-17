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
