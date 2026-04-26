import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsCss = readFileSync(
  resolve(import.meta.dirname, '../src/pages/settings.css'),
  'utf-8'
);

test('settings select dropdown options use dark readable popup styling', () => {
  assert.match(settingsCss, /\.settings-select option\s*\{/);
  assert.match(settingsCss, /\.settings-select option:checked\s*\{/);
  assert.match(settingsCss, /\.settings-select option:disabled\s*\{/);
  assert.match(settingsCss, /background:\s*var\(--panel-strong\)/);
  assert.match(settingsCss, /color:\s*var\(--text\)/);
});
