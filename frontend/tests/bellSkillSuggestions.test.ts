import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getBellItems,
  getUnreadBellCount,
  setPendingSkillSuggestions,
} from '../src/services/updates';
import type { SkillSuggestion } from '../src/types';

// Tests run in node:test which doesn't ship localStorage. Provide a tiny
// in-memory shim so updates.ts's read-tracking helpers don't crash.
function installLocalStorageShim(): void {
  if (typeof globalThis.localStorage !== 'undefined') return;
  const store = new Map<string, string>();
  (globalThis as any).localStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => store.set(k, String(v)),
    removeItem: (k: string) => store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() { return store.size; },
  };
}
installLocalStorageShim();

function makeSug(overrides: Partial<SkillSuggestion> = {}): SkillSuggestion {
  return {
    id: 'sug_001',
    kind: 'create',
    name: 'auto-format-on-save',
    description: 'Run prettier whenever the user saves a TS file.',
    body: '',
    markdown: '',
    target_skill: null,
    previous_markdown: null,
    triggers: ['save typescript file'],
    source_session_id: null,
    source_message: null,
    created_at: '2026-05-18T10:00:00Z',
    path: null,
    preview_markdown: '',
    diff_markdown: '',
    ...overrides,
  };
}

test('getBellItems surfaces a pending skill suggestion when info is null', () => {
  setPendingSkillSuggestions([makeSug()]);

  const items = getBellItems(null);

  // Exactly one bell item, of skill-suggestion type
  const skillItems = items.filter((i) => i.type === 'skill-suggestion');
  assert.equal(skillItems.length, 1);
  assert.equal(skillItems[0].id, 'skill-sug-sug_001');
  assert.match(skillItems[0].title, /新技能待审批/);
  assert.equal(skillItems[0].navTarget, 'skills');
});

test('skill-suggestion item shows up alongside an empty announcement payload', () => {
  setPendingSkillSuggestions([makeSug({ id: 'sug_002' })]);
  const items = getBellItems({ announcements: [] } as any);
  assert.equal(items.length, 1);
  assert.equal(items[0].type, 'skill-suggestion');
});

test('update-kind suggestions get the "技能更新" title prefix', () => {
  setPendingSkillSuggestions([makeSug({ id: 'sug_003', kind: 'update', name: 'web-fetch' })]);
  const items = getBellItems(null);
  assert.match(items[0].title, /技能更新待审批/);
  assert.match(items[0].title, /web-fetch/);
});

test('unread bell count includes pending suggestions', () => {
  setPendingSkillSuggestions([
    makeSug({ id: 'sug_a' }),
    makeSug({ id: 'sug_b' }),
    makeSug({ id: 'sug_c' }),
  ]);

  const count = getUnreadBellCount(null);
  assert.equal(count, 3);
});

test('clearing the suggestions cache removes them from bell items', () => {
  setPendingSkillSuggestions([makeSug({ id: 'sug_x' })]);
  assert.equal(getBellItems(null).length, 1);

  setPendingSkillSuggestions([]);
  assert.equal(getBellItems(null).length, 0);
});

test('suggestion without an id is skipped (defensive)', () => {
  // Cast through `any` because the type forbids missing id; we're testing
  // the runtime guard.
  setPendingSkillSuggestions([{ ...makeSug({ id: '' }) } as SkillSuggestion]);
  assert.equal(getBellItems(null).length, 0);
});
