import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);

test('automation settings quietly refresh cron jobs while the section is open', () => {
  assert.match(settingsSource, /window\.setInterval\(\(\) => \{/);
  assert.match(settingsSource, /void loadAutomationData\(true\)/);
  assert.match(settingsSource, /window\.clearInterval\(timer\)/);
});
