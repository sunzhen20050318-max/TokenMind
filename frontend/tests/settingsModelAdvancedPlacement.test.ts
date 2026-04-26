import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);

const sectionMetaSource = settingsSource.slice(
  settingsSource.indexOf('const SECTION_META = ['),
  settingsSource.indexOf('const NAV_GROUPS')
);

const providerEditorSource = settingsSource.slice(
  settingsSource.indexOf('const renderProviderEditor = () => {'),
  settingsSource.indexOf('const renderToolsCategoryEditor = () => {')
);

test('model advanced settings are configured inside the provider editor instead of a separate nav entry', () => {
  assert.ok(sectionMetaSource.includes("id: 'models'"), 'models section should still exist');
  assert.ok(!sectionMetaSource.includes("id: 'agent'"), 'agent should not be a standalone settings section');
  assert.doesNotMatch(settingsSource, /case 'agent':\s*return renderAgent\(\);/);
  assert.match(settingsSource, /const renderModelAdvancedFields = \(\) => \{/);
  assert.match(providerEditorSource, /renderModelAdvancedFields\(\)/);
});

test('provider editor advanced settings avoid duplicated model controls and extra save actions', () => {
  assert.match(providerEditorSource, /模型高级参数/);
  assert.doesNotMatch(providerEditorSource, /智能体默认参数/);
  assert.doesNotMatch(providerEditorSource, /handleSaveAgent/);
  assert.doesNotMatch(providerEditorSource, /agentDraft\.provider/);
  assert.doesNotMatch(providerEditorSource, /agentDraft\.model/);
  assert.match(providerEditorSource, /保存模型配置/);
  assert.doesNotMatch(providerEditorSource, /保存提供商配置/);
  assert.equal(
    providerEditorSource.match(/handleSaveProvider\(\)/g)?.length,
    1,
    'provider editor should expose one save action'
  );
});
