import React from 'react';

interface StatusCardProps {
  model: string | null;
  reasoning: string | null;
  personality: 'warm' | 'pragmatic' | null;
  planMode: boolean;
  messageCount: number;
  consolidatedOffset: number;
  /** TokenMind's soft auto-/compact threshold (config-driven). */
  compactionThreshold: number | null;
  /** Authoritative prompt-token count from the last LLM call. */
  lastPromptTokens: number | null;
  lastPromptAt: string | null;
  lastPromptModel: string | null;
  onClose: () => void;
}

const MONO =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';

const PERSONALITY_LABEL: Record<string, string> = {
  warm: '亲和',
  pragmatic: '务实',
};

// Mirror the dropdown labels in InputArea so /status reads consistently
// with what the user sees in the composer.
const REASONING_LABEL: Record<string, string> = {
  '': '关闭',
  low: '轻度',
  medium: '标准',
  high: '深度',
};

function formatRelative(iso: string | null): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  if (diff < 0) return '刚刚';
  const s = Math.round(diff / 1000);
  if (s < 60) return `${s} 秒前`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.round(h / 24);
  return `${d} 天前`;
}

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 100_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1000).toFixed(0)}k`;
}

/**
 * Read-only summary card opened by ``/status``. Surfaces the current
 * session's runtime preferences plus a token-usage snapshot anchored
 * on the most recent LLM call (precise — same number the API counted).
 */
export const StatusCard: React.FC<StatusCardProps> = ({
  model,
  reasoning,
  personality,
  planMode,
  messageCount,
  consolidatedOffset,
  compactionThreshold,
  lastPromptTokens,
  lastPromptAt,
  lastPromptModel,
  onClose,
}) => {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const hasThreshold = !!(compactionThreshold && compactionThreshold > 0);
  const hasLastPrompt = lastPromptTokens != null && lastPromptTokens > 0;
  const usedPct =
    hasThreshold && hasLastPrompt
      ? Math.min(100, Math.round((lastPromptTokens! / compactionThreshold!) * 100))
      : null;
  const remainingTokens =
    hasThreshold && hasLastPrompt
      ? Math.max(0, compactionThreshold! - lastPromptTokens!)
      : null;

  const lastPromptValue: React.ReactNode = hasLastPrompt ? (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div>
        <span style={{ color: '#fafafa', fontVariantNumeric: 'tabular-nums' }}>
          {lastPromptTokens!.toLocaleString()}
        </span>{' '}
        <span style={{ color: '#7f7f7f' }}>tokens</span>
      </div>
      <div style={{ color: '#7f7f7f', fontSize: '11px' }}>
        {[
          formatRelative(lastPromptAt),
          lastPromptModel ? `模型 ${lastPromptModel}` : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </div>
    </div>
  ) : (
    <span style={{ color: '#9a9a9a' }}>暂无</span>
  );

  const thresholdValue: React.ReactNode = hasThreshold ? (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div>
        <span style={{ color: '#fafafa', fontVariantNumeric: 'tabular-nums' }}>
          {compactionThreshold!.toLocaleString()}
        </span>{' '}
        <span style={{ color: '#7f7f7f' }}>tokens</span>
      </div>
      {usedPct !== null && remainingTokens !== null ? (
        <>
          <div style={{ color: '#9a9a9a', fontSize: '11.5px' }}>
            上次请求已占 {usedPct}% · 还剩{' '}
            <span style={{ color: '#cfcfcf', fontVariantNumeric: 'tabular-nums' }}>
              {fmtTokens(remainingTokens)}
            </span>{' '}
            tokens
          </div>
          <div
            aria-hidden
            style={{
              marginTop: '2px',
              height: '4px',
              borderRadius: '2px',
              background: 'rgba(255,255,255,0.08)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${usedPct}%`,
                background:
                  usedPct >= 80 ? '#d96c6c' : usedPct >= 50 ? '#d9a366' : '#cfcfcf',
                transition: 'width 240ms ease',
              }}
            />
          </div>
        </>
      ) : null}
    </div>
  ) : (
    <span style={{ color: '#9a9a9a' }}>未配置</span>
  );

  const rows: Array<{ label: string; value: React.ReactNode; hint?: string }> = [
    { label: '模型', value: model || '未选择' },
    { label: '思考等级', value: REASONING_LABEL[reasoning || ''] || reasoning || '默认' },
    {
      label: '回答风格',
      value: personality ? PERSONALITY_LABEL[personality] : '系统默认',
    },
    {
      label: '计划模式',
      value: planMode ? '开启 — 多步任务前需先列 task_list' : '关闭',
    },
    {
      label: '消息数',
      value: `${messageCount} 条（已固化 ${consolidatedOffset} 条不在上下文）`,
    },
    {
      label: '上次请求',
      value: lastPromptValue,
    },
    {
      label: '压缩阈值',
      value: thresholdValue,
      hint: '达到一半左右会自动触发记忆压缩（非模型硬件上限）。',
    },
  ];

  return (
    <div
      role="dialog"
      aria-label="会话状态"
      style={{
        marginBottom: '10px',
        background: '#161616',
        border: '1px solid rgba(255,255,255,0.10)',
        borderRadius: '12px',
        overflow: 'hidden',
        fontFamily: MONO,
        boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
        animation: 'tk-status-card-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`
          @keyframes tk-status-card-in {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 12px 10px 16px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        <span style={{ color: '#e8e8e8', fontSize: '12px' }}>STATUS</span>
        <span style={{ marginLeft: '10px', color: '#7f7f7f', fontSize: '11px' }}>
          当前会话状态
        </span>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onClose}
          aria-label="关闭"
          title="关闭 (Esc)"
          style={{
            width: '28px',
            height: '28px',
            background: 'transparent',
            border: 'none',
            color: '#7f7f7f',
            fontSize: '14px',
            cursor: 'pointer',
            borderRadius: '6px',
            outline: 'none',
          }}
        >
          ×
        </button>
      </div>

      <div style={{ padding: '6px 0' }}>
        {rows.map((row) => (
          <div
            key={row.label}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '14px',
              padding: '6px 16px',
              fontSize: '12px',
            }}
          >
            <span style={{ color: '#9a9a9a', width: '90px', flexShrink: 0 }}>{row.label}</span>
            <span
              style={{
                color: '#e8e8e8',
                flex: 1,
                minWidth: 0,
                wordBreak: 'break-word',
              }}
            >
              {row.value}
              {row.hint ? (
                <div style={{ color: '#7f7f7f', fontSize: '10.5px', marginTop: '4px' }}>
                  {row.hint}
                </div>
              ) : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
