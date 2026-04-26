import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const settingsSource = readFileSync(
  resolve(import.meta.dirname, '../src/pages/Settings.tsx'),
  'utf-8'
);

test('provider cards reserve active styling for the default provider', () => {
  assert.match(
    settingsSource,
    /provider\.active\s*\?\s*'active'/,
    'the active card style should follow the enabled/default provider'
  );
  assert.match(
    settingsSource,
    /selectedProviderId\s*===\s*provider\.id\s*\?\s*'is-selected'/,
    'the clicked provider should use a separate selected/editing class'
  );
  assert.doesNotMatch(
    settingsSource,
    /selectedProviderId\s*===\s*provider\.id\s*\?\s*'active'/,
    'clicking a provider must not make it look like the enabled/default provider'
  );
});

test('creative capability cards reserve active styling for enabled capabilities', () => {
  assert.match(
    settingsSource,
    /className=\{`settings-provider-card \$\{capability\.enabled\s*\?\s*'active'\s*:\s*''\} \$\{/,
    'creative capability card active styling should follow enabled state'
  );
  assert.match(
    settingsSource,
    /selectedCreativeId\s*===\s*capability\.id\s*\?\s*'is-selected'/,
    'the clicked creative capability should use a separate selected/editing class'
  );
  assert.doesNotMatch(
    settingsSource,
    /selectedCreativeId\s*===\s*capability\.id\s*\?\s*'active'/,
    'clicking a creative capability must not make it look enabled'
  );
});
