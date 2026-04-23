import { isCreativeCapabilityConfigured, type CreativeCapabilitySettings } from '../types/config';

export type CreativeCapabilityState = 'unconfigured' | 'configured-disabled' | 'enabled';

export function deriveCreativeCapabilityState(
  capability: CreativeCapabilitySettings | null | undefined
): CreativeCapabilityState {
  if (!isCreativeCapabilityConfigured(capability)) {
    return 'unconfigured';
  }

  return capability?.enabled ? 'enabled' : 'configured-disabled';
}
