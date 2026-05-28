import React from 'react';
import type { PendingBrowserHandoff } from '../../types';

interface BrowserHandoffModalProps {
  handoff: PendingBrowserHandoff | null;
  onComplete: () => void;
  onCancel: () => void;
}

/**
 * Sister modal to ToolApprovalModal — same visual language (dark card,
 * white accent, pre-style command block) but a different transaction:
 * the agent is paused in a ``browser(action='handoff')`` call waiting
 * for the user to finish a login / verification step in their actual
 * Chrome window. Two outcomes only — "我已完成" resumes the agent,
 * "取消" tells it the user aborted.
 */
const ACCENT_FG = '#0b0b0b';
const ACCENT_FILL = '#e8e8e8';

export const BrowserHandoffModal: React.FC<BrowserHandoffModalProps> = ({
  handoff,
  onComplete,
  onCancel,
}) => {
  const [remainingMs, setRemainingMs] = React.useState(0);

  React.useEffect(() => {
    if (!handoff?.timeout_s) {
      setRemainingMs(0);
      return;
    }
    const timeoutMs = handoff.timeout_s * 1000;
    const startedAt = handoff.received_at_ms || Date.now();
    const update = () => {
      setRemainingMs(Math.max(startedAt + timeoutMs - Date.now(), 0));
    };
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [handoff]);

  React.useEffect(() => {
    if (!handoff) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        onComplete();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handoff, onComplete, onCancel]);

  if (!handoff) return null;

  const secondsLeft = Math.max(0, Math.ceil(remainingMs / 1000));

  return (
    <div
      style={{
        marginBottom: '10px',
        width: '100%',
        background: '#161616',
        border: '1px solid rgba(255,255,255,0.10)',
        borderRadius: '12px',
        boxShadow: '0 12px 36px rgba(0,0,0,0.40)',
        overflow: 'hidden',
        animation: 'tk-handoff-rise 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`@keyframes tk-handoff-rise {
            from { opacity: 0; transform: translateY(12px); }
            to   { opacity: 1; transform: translateY(0); }
          }`}
      </style>

      <div
        style={{
          padding: '12px 16px 8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '13.5px', fontWeight: 600, color: '#f0f0f0' }}>
          需要你接管浏览器
        </h3>
        <span style={{ fontSize: '11px', color: '#888' }}>
          {handoff.timeout_s ? `${secondsLeft}s 内确认` : '等待确认'}
        </span>
      </div>

      <div style={{ padding: '0 16px 12px' }}>
        <pre
          style={{
            margin: 0,
            padding: '10px 12px',
            background: '#0b0b0b',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '7px',
            fontFamily: 'inherit',
            fontSize: '12.5px',
            lineHeight: 1.55,
            color: '#e8e8e8',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {handoff.instructions}
        </pre>
        {handoff.reason ? (
          <div
            style={{
              marginTop: '6px',
              fontSize: '11.5px',
              color: '#7f7f7f',
              lineHeight: 1.5,
              wordBreak: 'break-word',
            }}
          >
            {handoff.reason}
          </div>
        ) : null}
      </div>

      <div
        style={{
          padding: '8px 16px 12px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        <button
          type="button"
          onClick={onCancel}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.16)',
            background: 'transparent',
            color: '#cfcfcf',
            fontSize: '12.5px',
            cursor: 'pointer',
          }}
        >
          取消
        </button>
        <span style={{ fontSize: '11px', color: '#666' }}>
          Esc 取消 · Enter 我已完成
        </span>
        <button
          type="button"
          onClick={onComplete}
          style={{
            padding: '6px 16px',
            borderRadius: '6px',
            border: 'none',
            background: ACCENT_FILL,
            color: ACCENT_FG,
            fontSize: '12.5px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          我已完成
        </button>
      </div>
    </div>
  );
};
