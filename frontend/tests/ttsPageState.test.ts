import test from 'node:test';
import assert from 'node:assert/strict';

import {
  appendTtsHistory,
  groupVoiceOptions,
  loadTtsHistory,
  makeHistoryId,
  saveTtsHistory,
  voiceOptionLabel,
} from '../src/pages/voice/ttsPageState';
import type { TtsHistoryItem } from '../src/pages/voice/ttsPageState';
import type { TtsVoiceOption } from '../src/types';

class FakeStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

function makeItem(overrides: Partial<TtsHistoryItem> = {}): TtsHistoryItem {
  return {
    id: overrides.id ?? 'tts_test',
    attachment_id: overrides.attachment_id ?? 'att_xxx',
    voice_id: overrides.voice_id ?? 'clone_abcdefgh',
    voice_label: overrides.voice_label ?? '克隆音色',
    model: overrides.model ?? 'speech-2.8-hd',
    text: overrides.text ?? 'hello',
    usage_characters: overrides.usage_characters ?? 10,
    created_at: overrides.created_at ?? '2026-04-24T10:00:00Z',
    filename: overrides.filename ?? 'tts-abc123.mp3',
    mime_type: overrides.mime_type ?? 'audio/mpeg',
    trace_id: overrides.trace_id ?? null,
  };
}

test('appendTtsHistory deduplicates by id and keeps newest first', () => {
  const base = [makeItem({ id: 'a' })];
  const next = appendTtsHistory(base, makeItem({ id: 'a', voice_label: '更新的' }));
  assert.equal(next.length, 1);
  assert.equal(next[0].voice_label, '更新的');
});

test('appendTtsHistory caps history at 50 entries', () => {
  const base = Array.from({ length: 50 }, (_, index) =>
    makeItem({ id: `item_${index}` }),
  );
  const next = appendTtsHistory(base, makeItem({ id: 'newest' }));
  assert.equal(next.length, 50);
  assert.equal(next[0].id, 'newest');
});

test('loadTtsHistory returns empty array on malformed storage', () => {
  const storage = new FakeStorage();
  storage.setItem('tokenmind:tts-history', 'not json');
  assert.deepEqual(loadTtsHistory(storage), []);
});

test('loadTtsHistory round-trips with saveTtsHistory', () => {
  const storage = new FakeStorage();
  const entry = makeItem({ id: 'round_trip' });
  saveTtsHistory([entry], storage);
  assert.deepEqual(loadTtsHistory(storage), [entry]);
});

test('groupVoiceOptions splits cloned and system voices', () => {
  const options: TtsVoiceOption[] = [
    { kind: 'cloned', voice_id: 'clone_a', label: 'clone A' },
    { kind: 'system', voice_id: 'male-qn-qingse', label: '青涩青年', gender: 'male' },
    { kind: 'cloned', voice_id: 'clone_b', label: 'clone B' },
  ];
  const { cloned, system } = groupVoiceOptions(options);
  assert.deepEqual(
    cloned.map((v) => v.voice_id),
    ['clone_a', 'clone_b'],
  );
  assert.deepEqual(
    system.map((v) => v.voice_id),
    ['male-qn-qingse'],
  );
});

test('voiceOptionLabel hides voice_id and uses friendly names', () => {
  assert.equal(
    voiceOptionLabel({ kind: 'system', voice_id: 'male-qn-qingse', label: '青涩青年' }),
    '青涩青年 · 系统音色',
  );
  assert.equal(
    voiceOptionLabel({
      kind: 'cloned',
      voice_id: 'clone_a',
      label: 'clone A',
      source_filename: 'sample.mp3',
      created_at: '2026-04-24T10:00:00Z',
    }),
    'sample.mp3 · 4/24 克隆',
  );
  assert.equal(
    voiceOptionLabel({ kind: 'cloned', voice_id: 'clone_b', label: 'clone B' }),
    '我的克隆音色',
  );
});

test('makeHistoryId returns unique strings', () => {
  const a = makeHistoryId();
  const b = makeHistoryId();
  assert.ok(a.startsWith('tts_'));
  assert.ok(b.startsWith('tts_'));
  assert.notEqual(a, b);
});
