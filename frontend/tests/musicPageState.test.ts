import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMusicGenerationRequest,
  canSubmitMusicGeneration,
  getMusicCapabilityNotice,
} from '../src/pages/musicPageState';
import { createEmptyCreativeCapabilitySettings } from '../src/types/config';

test('buildMusicGenerationRequest merges prompt and selected tags', () => {
  assert.deepEqual(
    buildMusicGenerationRequest({
      prompt: 'City pop for a night drive',
      lyrics: '[Verse]\nTokenMind',
      selectedTags: ['Pop', 'Drive / Sports'],
      lyricsOptimizer: false,
      instrumental: false,
    }),
    {
      prompt: 'City pop for a night drive\n\nStyle and scene tags: Pop, Drive / Sports',
      lyrics: '[Verse]\nTokenMind',
      lyrics_optimizer: false,
      is_instrumental: false,
    }
  );
});

test('buildMusicGenerationRequest omits lyrics for instrumental generation', () => {
  assert.deepEqual(
    buildMusicGenerationRequest({
      prompt: 'Ambient score',
      lyrics: '[Verse]\nIgnored',
      selectedTags: [],
      lyricsOptimizer: false,
      instrumental: true,
    }),
    {
      prompt: 'Ambient score',
      lyrics: null,
      lyrics_optimizer: false,
      is_instrumental: true,
    }
  );
});

test('canSubmitMusicGeneration requires enabled configured music capability', () => {
  const enabledCapability = {
    ...createEmptyCreativeCapabilitySettings(),
    enabled: true,
    provider: 'minimax',
    model: 'music-2.6',
  };

  assert.equal(
    canSubmitMusicGeneration({
      capability: enabledCapability,
      prompt: 'pop song',
      lyrics: '[Verse]\nhello',
      lyricsOptimizer: false,
      instrumental: false,
      isGenerating: false,
    }),
    true
  );

  assert.equal(
    canSubmitMusicGeneration({
      capability: { ...enabledCapability, enabled: false },
      prompt: 'pop song',
      lyrics: '[Verse]\nhello',
      lyricsOptimizer: false,
      instrumental: false,
      isGenerating: false,
    }),
    false
  );
});

test('canSubmitMusicGeneration allows auto lyrics and instrumental without manual lyrics', () => {
  const capability = {
    ...createEmptyCreativeCapabilitySettings(),
    enabled: true,
    provider: 'minimax',
    model: 'music-2.6',
  };

  assert.equal(
    canSubmitMusicGeneration({
      capability,
      prompt: 'upbeat hook',
      lyrics: '',
      lyricsOptimizer: true,
      instrumental: false,
      isGenerating: false,
    }),
    true
  );
  assert.equal(
    canSubmitMusicGeneration({
      capability,
      prompt: 'game loop',
      lyrics: '',
      lyricsOptimizer: false,
      instrumental: true,
      isGenerating: false,
    }),
    true
  );
});

test('canSubmitMusicGeneration allows reference audio without manual lyrics', () => {
  const capability = {
    ...createEmptyCreativeCapabilitySettings(),
    enabled: true,
    provider: 'minimax',
    model: 'music-2.6',
  };

  assert.equal(
    canSubmitMusicGeneration({
      capability,
      prompt: 'reference-based pop arrangement',
      lyrics: '',
      lyricsOptimizer: false,
      instrumental: false,
      hasReferenceAudio: true,
      isGenerating: false,
    }),
    true
  );
});

test('getMusicCapabilityNotice explains capability state', () => {
  assert.equal(
    getMusicCapabilityNotice(createEmptyCreativeCapabilitySettings()),
    '还没有配置音乐模型，请先到设置中心的创作能力里配置并启用。'
  );
  assert.equal(
    getMusicCapabilityNotice({
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
      model: 'music-2.6',
    }),
    '音乐模型已经配置完成，但当前还没有启用。'
  );
});
