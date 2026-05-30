// Pure helper for the channel runtime-status badge in Settings.
//
// The channel manager runs inside the web process, so /api/config/channels
// reports each channel's live ``running`` state. We only badge enabled
// channels — a disabled channel being "offline" is expected, not news.

export type ChannelTone = 'online' | 'offline';

export interface ChannelBadge {
  label: string;
  tone: ChannelTone;
}

export function channelRuntimeBadge(
  enabled: boolean,
  running: boolean,
): ChannelBadge | null {
  if (!enabled) return null;
  return running
    ? { label: '在线', tone: 'online' }
    : { label: '离线', tone: 'offline' };
}
