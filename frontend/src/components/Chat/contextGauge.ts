// Pure helper behind the chat-window context-remaining ring.
//
// It mirrors the /status card's token math (lastPromptTokens vs the
// compaction threshold) so both surfaces agree, and keeps the math out of
// the React component so it can be unit-tested without a DOM.

export type ContextLevel = 'normal' | 'warn' | 'critical';

export interface ContextGauge {
  /** Whether there's enough data (a threshold and a real prompt count) to show. */
  available: boolean;
  /** 0–100, clamped. */
  usedPct: number;
  /** 0–100, clamped. The ring's colored arc tracks this (remaining capacity). */
  remainingPct: number;
  /** Tokens left before the compaction threshold. */
  remainingTokens: number;
  /** The compaction threshold itself (total capacity). */
  totalTokens: number;
  /** Arc color, keyed by how full the context is. */
  color: string;
  level: ContextLevel;
  /** Hover tooltip: remaining / total, plus the click-to-compact hint. */
  title: string;
}

// Match StatusCard's thresholds and palette so the two never disagree.
const COLOR: Record<ContextLevel, string> = {
  normal: '#cfcfcf',
  warn: '#d9a366',
  critical: '#d96c6c',
};

export function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 100_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1000).toFixed(0)}k`;
}

export function computeContextGauge(
  lastPromptTokens: number | null,
  threshold: number | null,
): ContextGauge {
  const hasThreshold = !!(threshold && threshold > 0);
  const hasPrompt = lastPromptTokens != null && lastPromptTokens > 0;
  if (!hasThreshold || !hasPrompt) {
    return {
      available: false,
      usedPct: 0,
      remainingPct: 100,
      remainingTokens: 0,
      totalTokens: threshold && threshold > 0 ? threshold : 0,
      color: COLOR.normal,
      level: 'normal',
      title: '上下文用量：发一条消息后显示',
    };
  }

  const usedPct = Math.min(100, Math.round((lastPromptTokens! / threshold!) * 100));
  const remainingPct = 100 - usedPct;
  const remainingTokens = Math.max(0, threshold! - lastPromptTokens!);
  const level: ContextLevel =
    usedPct >= 80 ? 'critical' : usedPct >= 50 ? 'warn' : 'normal';

  return {
    available: true,
    usedPct,
    remainingPct,
    remainingTokens,
    totalTokens: threshold!,
    color: COLOR[level],
    level,
    title:
      `上下文剩余 ${fmtTokens(remainingTokens)} / 总 ${fmtTokens(threshold!)} tokens` +
      `（已用 ${usedPct}%）· 点击压缩较早对话`,
  };
}
