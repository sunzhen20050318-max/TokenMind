import test from 'node:test';
import assert from 'node:assert/strict';

import {
  appendClonedVoice,
  daysUntilExpiry,
  expiryLabel,
  extensionForMime,
  formatRecordingDuration,
  getScenePrompt,
  isMiniMaxCompatibleMime,
  isSupportedCloneAudio,
  loadClonedVoiceHistory,
  makeRecordedFilename,
  SCENE_PROMPTS,
  saveClonedVoiceHistory,
  validateVoiceCloneForm,
  validateVoiceId,
  VOICE_CLONE_INACTIVITY_DAYS,
  VOICE_CLONE_MAX_BYTES,
} from '../src/pages/voice/voiceClonePageState';

class FakeFile {
  constructor(
    public readonly name: string,
    public readonly size: number,
    public readonly type: string,
  ) {}
}

function makeFile(overrides: Partial<{ name: string; size: number; type: string }> = {}): File {
  return new FakeFile(
    overrides.name ?? 'sample.mp3',
    overrides.size ?? 1024,
    overrides.type ?? 'audio/mpeg',
  ) as unknown as File;
}

test('isSupportedCloneAudio accepts mp3/m4a/wav by mime or extension', () => {
  assert.equal(isSupportedCloneAudio(makeFile({ type: 'audio/mpeg' })), true);
  assert.equal(isSupportedCloneAudio(makeFile({ type: 'audio/wav' })), true);
  assert.equal(isSupportedCloneAudio(makeFile({ type: 'audio/x-m4a' })), true);
  assert.equal(
    isSupportedCloneAudio(makeFile({ name: 'custom.m4a', type: '' })),
    true,
    'empty mime should fall back to extension',
  );
});

test('isSupportedCloneAudio rejects unsupported formats and oversize files', () => {
  assert.equal(isSupportedCloneAudio(makeFile({ type: 'video/mp4' })), false);
  assert.equal(isSupportedCloneAudio(makeFile({ name: 'a.aac', type: 'audio/aac' })), false);
  assert.equal(isSupportedCloneAudio(makeFile({ size: VOICE_CLONE_MAX_BYTES + 1 })), false);
  assert.equal(isSupportedCloneAudio(null), false);
});

test('validateVoiceId allows empty value (auto-generated)', () => {
  assert.equal(validateVoiceId(''), null);
  assert.equal(validateVoiceId('   '), null);
});

test('validateVoiceId rejects identifiers that violate MiniMax constraints', () => {
  assert.equal(validateVoiceId('1short')?.code, 'voice_id_invalid');
  assert.equal(validateVoiceId('a'.repeat(7))?.code, 'voice_id_invalid');
  assert.equal(validateVoiceId('bad space')?.code, 'voice_id_invalid');
});

test('validateVoiceId accepts well-formed identifiers', () => {
  assert.equal(validateVoiceId('clone_friendlyBot'), null);
  assert.equal(validateVoiceId('A_abc-123'), null);
});

test('validateVoiceCloneForm reports missing file and oversized preview', () => {
  const errors = validateVoiceCloneForm({
    file: null,
    voiceId: '',
    previewText: 'x'.repeat(1001),
    needNoiseReduction: false,
    needVolumeNormalization: false,
    languageBoost: '',
  });
  const codes = errors.map((error) => error.code);
  assert.ok(codes.includes('file_missing'));
  assert.ok(codes.includes('preview_too_long'));
});

test('validateVoiceCloneForm returns no errors for a valid submission', () => {
  const errors = validateVoiceCloneForm({
    file: makeFile({ size: 1_000_000 }),
    voiceId: 'clone_abcdefgh',
    previewText: 'Hello',
    needNoiseReduction: true,
    needVolumeNormalization: false,
    languageBoost: '',
  });
  assert.deepEqual(errors, []);
});

test('appendClonedVoice deduplicates and keeps newest first', () => {
  const base = [
    {
      voice_id: 'clone_a',
      model: 'speech-2.8-hd',
      provider: 'minimax',
      created_at: '2026-04-20T00:00:00Z',
      demo_audio_url: null,
      preview_text: null,
      source_filename: 'a.mp3',
    },
  ];
  const next = appendClonedVoice(base, {
    voice_id: 'clone_a',
    model: 'speech-2.8-hd',
    provider: 'minimax',
    created_at: '2026-04-21T00:00:00Z',
    demo_audio_url: 'https://cdn/demo.mp3',
    preview_text: 'hi',
    source_filename: 'b.mp3',
  });

  assert.equal(next.length, 1);
  assert.equal(next[0].created_at, '2026-04-21T00:00:00Z');
  assert.equal(next[0].demo_audio_url, 'https://cdn/demo.mp3');
});

test('appendClonedVoice caps history at 100 entries', () => {
  const existing = Array.from({ length: 100 }, (_, index) => ({
    voice_id: `clone_${index.toString().padStart(3, '0')}`,
    model: 'speech-2.8-hd',
    provider: 'minimax',
    created_at: `2026-04-${(index % 30) + 1}T00:00:00Z`,
    demo_audio_url: null,
    preview_text: null,
    source_filename: null,
  }));
  const next = appendClonedVoice(existing, {
    voice_id: 'clone_new',
    model: 'speech-2.8-hd',
    provider: 'minimax',
    created_at: '2026-04-22T00:00:00Z',
    demo_audio_url: null,
    preview_text: null,
    source_filename: null,
  });
  assert.equal(next.length, 100);
  assert.equal(next[0].voice_id, 'clone_new');
});

class FakeStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

test('loadClonedVoiceHistory returns empty array on missing or malformed data', () => {
  const missing = new FakeStorage();
  assert.deepEqual(loadClonedVoiceHistory(missing), []);
  const bad = new FakeStorage();
  bad.setItem('tokenmind:voice-clones', '{not json');
  assert.deepEqual(loadClonedVoiceHistory(bad), []);
});

test('extensionForMime maps MiniMax-compatible formats to expected extensions', () => {
  assert.equal(extensionForMime('audio/mp4'), 'm4a');
  assert.equal(extensionForMime('audio/mp4;codecs=mp4a.40.2'), 'm4a');
  assert.equal(extensionForMime('audio/mpeg'), 'mp3');
  assert.equal(extensionForMime('audio/wav'), 'wav');
  assert.equal(extensionForMime('audio/webm'), 'webm');
  assert.equal(extensionForMime('application/octet-stream'), 'bin');
});

test('isMiniMaxCompatibleMime only approves MP3/M4A/WAV', () => {
  assert.equal(isMiniMaxCompatibleMime('audio/mp4'), true);
  assert.equal(isMiniMaxCompatibleMime('audio/mpeg'), true);
  assert.equal(isMiniMaxCompatibleMime('audio/wav'), true);
  assert.equal(isMiniMaxCompatibleMime('audio/webm'), false);
  assert.equal(isMiniMaxCompatibleMime(''), false);
  assert.equal(isMiniMaxCompatibleMime(null), false);
});

test('makeRecordedFilename yields a timestamped name with the right extension', () => {
  const mp4 = makeRecordedFilename('audio/mp4');
  assert.ok(mp4.endsWith('.m4a'));
  const webm = makeRecordedFilename('audio/webm');
  assert.ok(webm.endsWith('.webm'));
  assert.ok(mp4.startsWith('clone-record-'));
});

test('formatRecordingDuration pads minutes and seconds', () => {
  assert.equal(formatRecordingDuration(0), '00:00');
  assert.equal(formatRecordingDuration(9), '00:09');
  assert.equal(formatRecordingDuration(65.9), '01:05');
  assert.equal(formatRecordingDuration(-10), '00:00');
});

test('getScenePrompt returns the random scene for unknown ids', () => {
  assert.equal(getScenePrompt('not-a-scene').id, SCENE_PROMPTS[0].id);
  assert.equal(getScenePrompt('audiobook').id, 'audiobook');
});

test('daysUntilExpiry counts down from created_at by default', () => {
  const created = new Date('2026-04-24T00:00:00Z');
  const now = new Date('2026-04-27T00:00:00Z'); // 3 days later
  assert.equal(
    daysUntilExpiry({ created_at: created.toISOString() }, now),
    VOICE_CLONE_INACTIVITY_DAYS - 3,
  );
});

test('daysUntilExpiry uses last_kept_alive_at when present', () => {
  const anchor = {
    created_at: '2026-04-01T00:00:00Z',
    last_kept_alive_at: '2026-04-24T00:00:00Z',
  };
  const now = new Date('2026-04-26T00:00:00Z');
  assert.equal(daysUntilExpiry(anchor, now), VOICE_CLONE_INACTIVITY_DAYS - 2);
});

test('daysUntilExpiry clamps at zero for expired records', () => {
  const now = new Date('2026-04-30T00:00:00Z');
  assert.equal(
    daysUntilExpiry({ created_at: '2026-04-01T00:00:00Z' }, now),
    0,
  );
});

test('expiryLabel formats days remaining in Chinese', () => {
  const now = new Date('2026-04-26T00:00:00Z');
  assert.equal(
    expiryLabel({ created_at: '2026-04-20T00:00:00Z' }, now),
    '剩 1 天',
  );
  assert.equal(
    expiryLabel({ created_at: '2026-04-24T00:00:00Z' }, now),
    '剩 5 天',
  );
  assert.equal(
    expiryLabel({ created_at: '2026-04-01T00:00:00Z' }, now),
    '可能已过期',
  );
});

test('loadClonedVoiceHistory round-trips with saveClonedVoiceHistory', () => {
  const storage = new FakeStorage();
  const entry = {
    voice_id: 'clone_xyz',
    model: 'speech-2.8-hd',
    provider: 'minimax',
    created_at: '2026-04-24T09:30:00Z',
    demo_audio_url: null,
    preview_text: null,
    source_filename: null,
  };
  saveClonedVoiceHistory([entry], storage);
  assert.deepEqual(loadClonedVoiceHistory(storage), [entry]);
});
