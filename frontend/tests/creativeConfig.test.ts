import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CREATIVE_CAPABILITY_KEYS,
  createEmptyCreativeCapabilitySettings,
  isCreativeCapabilityConfigured,
  type CreativeSettings,
} from '../src/types/config';

test('creative capability helpers expose all supported capability keys', () => {
  assert.deepEqual(CREATIVE_CAPABILITY_KEYS, [
    'image',
    'music',
    'music_cover',
    'voice_clone',
    'tts',
    'voice_design',
    'video',
  ]);
});

test('createEmptyCreativeCapabilitySettings returns the expected disabled shape', () => {
  assert.deepEqual(createEmptyCreativeCapabilitySettings(), {
    enabled: false,
    provider: '',
    api_key: '',
    api_base: null,
    model: '',
    extra_headers: null,
  });
});

test('isCreativeCapabilityConfigured only returns true when provider and model are both present', () => {
  const creative: CreativeSettings = {
    image: {
      enabled: true,
      provider: 'minimax',
      api_key: '****1234',
      api_base: 'https://api.minimax.io/v1',
      model: 'image-01',
      extra_headers: null,
    },
    music: createEmptyCreativeCapabilitySettings(),
    music_cover: {
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
      model: 'music-cover',
    },
    voice_clone: {
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
    },
    tts: {
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
      model: 'speech-2.8',
    },
    voice_design: createEmptyCreativeCapabilitySettings(),
    video: {
      ...createEmptyCreativeCapabilitySettings(),
      model: 'video-01',
    },
  };

  assert.equal(isCreativeCapabilityConfigured(creative.image), true);
  assert.equal(isCreativeCapabilityConfigured(creative.music), false);
  assert.equal(isCreativeCapabilityConfigured(creative.music_cover), true);
  assert.equal(isCreativeCapabilityConfigured(creative.voice_clone), false);
  assert.equal(isCreativeCapabilityConfigured(creative.tts), true);
  assert.equal(isCreativeCapabilityConfigured(creative.voice_design), false);
  assert.equal(isCreativeCapabilityConfigured(creative.video), false);
});
