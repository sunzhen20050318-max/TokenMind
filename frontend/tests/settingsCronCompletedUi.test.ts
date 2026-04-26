import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);
const settingsCss = readFileSync(
  resolve(import.meta.dirname, '../src/pages/settings.css'),
  'utf-8'
);

test('completed cron rows show status text instead of the enable toggle', () => {
  assert.match(settingsSource, /cronTab === 'completed'/);
  assert.match(settingsSource, /settings-cron-status/);
  assert.match(settingsSource, /job\.state\.last_status === 'error'/);
});

test('completed cron menus still expose rerun edit and delete actions', () => {
  assert.doesNotMatch(settingsSource, /\{!isCompleted \? \(/);
  assert.match(settingsSource, /void handleRunCronJob\(job\.id\)/);
  assert.match(settingsSource, /openCronEditor\(job\)/);
  assert.match(settingsSource, /void handleDeleteCronJob\(job\.id\)/);
});

test('cron action menus open sideways instead of covering the next row trigger', () => {
  assert.match(settingsCss, /\.settings-cron-table\s*\{[\s\S]*overflow:\s*visible;/);
  assert.match(settingsCss, /\.settings-cron-row__menu\s*\{[\s\S]*z-index:\s*20;/);
  assert.match(settingsCss, /\.settings-cron-menu\s*\{[\s\S]*top:\s*50%;/);
  assert.match(settingsCss, /\.settings-cron-menu\s*\{[\s\S]*right:\s*calc\(100% \+ 8px\);/);
  assert.match(settingsCss, /\.settings-cron-menu\s*\{[\s\S]*transform:\s*translateY\(-50%\);/);
});
