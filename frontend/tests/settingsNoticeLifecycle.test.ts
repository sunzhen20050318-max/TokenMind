import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);

test('settings notices clear themselves after a short delay', () => {
  assert.match(settingsSource, /window\.setTimeout\(\(\) => \{\s*setNotice\(null\);\s*\}, 2000\)/);
  assert.match(settingsSource, /window\.clearTimeout\(timer\)/);
});

test('settings notices are cleared when switching sections', () => {
  assert.match(settingsSource, /useEffect\(\(\) => \{\s*setNotice\(null\);\s*\}, \[selectedSection\]\)/);
});
