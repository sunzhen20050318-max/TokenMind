import test from 'node:test';
import assert from 'node:assert/strict';

import { createEmptyCreativeCapabilitySettings } from '../src/types/config';
import { deriveCreativeCapabilityState } from '../src/pages/creativePageState';

test('deriveCreativeCapabilityState returns unconfigured when provider or model is missing', () => {
  assert.equal(
    deriveCreativeCapabilityState(createEmptyCreativeCapabilitySettings()),
    'unconfigured'
  );

  assert.equal(
    deriveCreativeCapabilityState({
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
    }),
    'unconfigured'
  );
});

test('deriveCreativeCapabilityState returns configured-disabled when configured but not enabled', () => {
  assert.equal(
    deriveCreativeCapabilityState({
      ...createEmptyCreativeCapabilitySettings(),
      provider: 'minimax',
      model: 'music-01',
    }),
    'configured-disabled'
  );
});

test('deriveCreativeCapabilityState returns enabled when configured and enabled', () => {
  assert.equal(
    deriveCreativeCapabilityState({
      ...createEmptyCreativeCapabilitySettings(),
      enabled: true,
      provider: 'minimax',
      model: 'music-01',
    }),
    'enabled'
  );
});
