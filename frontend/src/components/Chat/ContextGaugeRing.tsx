import React from 'react';

import { computeContextGauge } from './contextGauge';

interface ContextGaugeRingProps {
  /** Authoritative prompt-token count from the last LLM call. */
  lastPromptTokens: number | null;
  /** Soft compaction threshold (config-driven). */
  threshold: number | null;
  /** Click handler — compacts earlier conversation (same as /compact). */
  onCompact?: () => void;
  /** Disable interaction while a compaction is already running. */
  busy?: boolean;
}

/**
 * Small depleting ring in the composer footer showing how much context
 * window is left. The colored arc tracks *remaining* capacity, so as the
 * conversation fills up the arc shrinks and the faint track grows — the
 * less the remaining, the more light shows. Hover shows remaining/total;
 * clicking compacts earlier history. Hidden until the first LLM response
 * gives us an authoritative token count.
 */
export const ContextGaugeRing: React.FC<ContextGaugeRingProps> = ({
  lastPromptTokens,
  threshold,
  onCompact,
  busy = false,
}) => {
  const gauge = computeContextGauge(lastPromptTokens, threshold);
  if (!gauge.available) return null;

  const size = 18;
  const stroke = 2.4;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  // Colored arc length is proportional to remaining capacity.
  const arc = (circumference * gauge.remainingPct) / 100;
  const center = size / 2;

  return (
    <button
      type="button"
      className="composer__context-gauge"
      aria-label={gauge.title}
      disabled={busy || !onCompact}
      onClick={() => onCompact?.()}
    >
      <span className="composer__context-gauge__tip" role="tooltip">
        {gauge.title}
      </span>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth={stroke}
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={gauge.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${arc} ${circumference - arc}`}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: 'stroke-dasharray 240ms ease, stroke 240ms ease' }}
        />
      </svg>
    </button>
  );
};
