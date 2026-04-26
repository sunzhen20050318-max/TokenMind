import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);

const providerMeta = settingsSource.match(/const PROVIDER_META:[\s\S]*?= \{([\s\S]*?)\};/);

if (!providerMeta) {
  throw new Error('Could not locate PROVIDER_META in Settings.tsx');
}

const providerMetaBlock = providerMeta[1];

const supportedProviderPresets = [
  'openai',
  'anthropic',
  'gemini',
  'deepseek',
  'moonshot',
  'minimax',
  'zhipu',
  'dashscope',
  'openrouter',
  'siliconflow',
  'ollama',
  'custom',
];

const removedProviderPresets = [
  'azure_openai',
  'groq',
  'vllm',
  'aihubmix',
  'volcengine',
  'volcengine_coding_plan',
  'byteplus',
  'byteplus_coding_plan',
  'openai_codex',
  'github_copilot',
];

test('settings provider cards include only supported presets', () => {
  for (const provider of supportedProviderPresets) {
    assert.match(providerMetaBlock, new RegExp(`\\b${provider}:`));
  }

  for (const provider of removedProviderPresets) {
    assert.doesNotMatch(providerMetaBlock, new RegExp(`\\b${provider}:`));
  }
});
