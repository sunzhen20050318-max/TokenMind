import React from 'react';
import type { PendingToolApproval } from '../../types';

interface ToolApprovalModalProps {
  approval: PendingToolApproval | null;
  onApprove: () => void;
  onReject: () => void;
  onTrustAndApprove: () => void;
  onRedirect: (instruction: string) => void;
}

type OptionId = 1 | 2 | 3;

const ACCENT_BG = 'rgba(255,255,255,0.07)';
const ACCENT_LINE = '#d8d8d8';
const ACCENT_FG = '#0b0b0b';
const ACCENT_FILL = '#e8e8e8';

export const ToolApprovalModal: React.FC<ToolApprovalModalProps> = ({
  approval,
  onApprove,
  onReject,
  onTrustAndApprove,
  onRedirect,
}) => {
  const [remainingMs, setRemainingMs] = React.useState(0);
  const [selected, setSelected] = React.useState<OptionId>(1);
  const [trust, setTrust] = React.useState(false);
  const [redirectText, setRedirectText] = React.useState('');
  const redirectInputRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    if (!approval) return;
    setSelected(1);
    setTrust(false);
    setRedirectText('');
  }, [approval?.approval_id]);

  React.useEffect(() => {
    if (selected === 3) {
      window.setTimeout(() => redirectInputRef.current?.focus(), 0);
    } else if (redirectInputRef.current === document.activeElement) {
      redirectInputRef.current?.blur();
    }
  }, [selected]);

  React.useEffect(() => {
    if (!approval?.timeout_s) {
      setRemainingMs(0);
      return;
    }
    const timeoutMs = approval.timeout_s * 1000;
    const startedAt = approval.received_at_ms || Date.now();
    const update = () => {
      setRemainingMs(Math.max(startedAt + timeoutMs - Date.now(), 0));
    };
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [approval]);

  const confirmOption1 = React.useCallback(() => {
    if (trust) onTrustAndApprove();
    else onApprove();
  }, [trust, onApprove, onTrustAndApprove]);

  const confirmOption3 = React.useCallback(() => {
    const text = redirectText.trim();
    if (!text) return;
    onRedirect(text);
  }, [redirectText, onRedirect]);

  const handleConfirm = React.useCallback(() => {
    if (selected === 1) confirmOption1();
    else if (selected === 2) onReject();
    else confirmOption3();
  }, [selected, confirmOption1, onReject, confirmOption3]);

  React.useEffect(() => {
    if (!approval) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inRedirectInput =
        selected === 3 && target === redirectInputRef.current;

      if (e.key === 'Escape') {
        e.preventDefault();
        onReject();
        return;
      }

      if (inRedirectInput) {
        // Inside the textarea: Enter sends, Shift+Enter newline.
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          confirmOption3();
          return;
        }
        // ArrowUp at the start of the textarea hops back to option list
        // (so keyboard users can return to options 1/2 without mouse).
        const el = redirectInputRef.current;
        if (e.key === 'ArrowUp' && el && el.selectionStart === 0) {
          e.preventDefault();
          el.blur();
          setSelected(2);
        }
        return;
      }

      if (e.key === '1') {
        e.preventDefault();
        setSelected(1);
      } else if (e.key === '2') {
        e.preventDefault();
        setSelected(2);
      } else if (e.key === '3') {
        e.preventDefault();
        setSelected(3);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        handleConfirm();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelected((s) => (s === 3 ? 1 : ((s + 1) as OptionId)));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelected((s) => (s === 1 ? 3 : ((s - 1) as OptionId)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [approval, selected, confirmOption1, confirmOption3, onReject, handleConfirm]);

  if (!approval) return null;

  const secondsLeft = Math.max(0, Math.ceil(remainingMs / 1000));

  const handleOptionClick = (id: OptionId) => {
    // Two-step click: first click selects, second click on the already-
    // selected option confirms. Exception: option 3 is always "select +
    // expand textarea"; sending happens via Enter or the send button.
    if (selected !== id) {
      setSelected(id);
      return;
    }
    if (id === 1) confirmOption1();
    else if (id === 2) onReject();
    // id === 3: stay selected; user types and presses Enter / clicks 发送.
  };

  const renderOption = (id: OptionId, label: string) => {
    const isSelected = selected === id;
    return (
      <div
        key={id}
        role="button"
        tabIndex={-1}
        onClick={(e) => {
          handleOptionClick(id);
          // Drop DOM focus so the browser's default focus ring doesn't
          // stick to the clicked element while keyboard updates `selected`.
          (e.currentTarget as HTMLElement).blur();
        }}
        onMouseDown={(e) => e.preventDefault()}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '9px 12px',
          borderRadius: '7px',
          background: isSelected ? ACCENT_BG : 'transparent',
          borderLeft: isSelected ? `3px solid ${ACCENT_LINE}` : '3px solid transparent',
          cursor: 'pointer',
          color: isSelected ? '#fafafa' : '#cfcfcf',
          fontSize: '13.5px',
          userSelect: 'none',
          outline: 'none',
          transition: 'background 80ms ease, color 80ms ease',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '18px',
            height: '18px',
            borderRadius: '4px',
            background: isSelected ? ACCENT_FILL : 'rgba(255,255,255,0.08)',
            color: isSelected ? ACCENT_FG : '#a0a0a0',
            fontSize: '11px',
            fontWeight: 600,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          }}
        >
          {id}
        </span>
        <span>{label}</span>
      </div>
    );
  };

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
        animation: 'tk-approval-rise 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`@keyframes tk-approval-rise {
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
          允许执行此命令？
        </h3>
        <span style={{ fontSize: '11px', color: '#888' }}>
          {approval.timeout_s ? `${secondsLeft}s 内需要确认` : '等待确认'}
        </span>
      </div>

      <div style={{ padding: '0 16px 8px' }}>
        <pre
          style={{
            margin: 0,
            padding: '10px 12px',
            background: '#0b0b0b',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '7px',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: '12px',
            lineHeight: 1.55,
            color: '#e8e8e8',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: '140px',
            overflow: 'auto',
          }}
        >
          {approval.command}
        </pre>
        <div
          style={{
            marginTop: '6px',
            fontSize: '11.5px',
            color: '#7f7f7f',
            lineHeight: 1.5,
            wordBreak: 'break-word',
          }}
        >
          {approval.risk_reason}
          <span style={{ color: '#4d4d4d' }}> · </span>
          <span
            style={{
              fontFamily:
                'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            }}
          >
            {approval.working_dir}
          </span>
        </div>
      </div>

      <div
        style={{
          padding: '4px 8px 4px',
          display: 'flex',
          flexDirection: 'column',
          gap: '1px',
        }}
      >
        {renderOption(1, '允许执行')}
        {renderOption(2, '拒绝')}
        {renderOption(3, '告诉 TokenMind 换种做法')}
      </div>

      {selected === 3 ? (
        <div style={{ padding: '2px 16px 10px' }}>
          <textarea
            ref={redirectInputRef}
            value={redirectText}
            onChange={(e) => setRedirectText(e.target.value)}
            placeholder="告诉 TokenMind 改成怎么做…（Enter 发送，Shift+Enter 换行，↑ 返回选项）"
            rows={2}
            style={{
              width: '100%',
              resize: 'vertical',
              padding: '8px 10px',
              background: '#0b0b0b',
              color: '#f0f0f0',
              border: '1px solid rgba(255,255,255,0.16)',
              borderRadius: '7px',
              fontSize: '12.5px',
              fontFamily: 'inherit',
              lineHeight: 1.5,
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          <div style={{ marginTop: '6px', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={confirmOption3}
              disabled={!redirectText.trim()}
              style={{
                padding: '5px 12px',
                borderRadius: '6px',
                border: 'none',
                background: redirectText.trim() ? ACCENT_FILL : 'rgba(255,255,255,0.08)',
                color: redirectText.trim() ? ACCENT_FG : '#666',
                fontSize: '12px',
                fontWeight: 600,
                cursor: redirectText.trim() ? 'pointer' : 'not-allowed',
              }}
            >
              发送
            </button>
          </div>
        </div>
      ) : null}

      <div
        style={{
          padding: '8px 16px 10px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '11px',
          color: '#7f7f7f',
        }}
      >
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={trust}
            onChange={(e) => setTrust(e.target.checked)}
            style={{ accentColor: ACCENT_FILL, cursor: 'pointer' }}
          />
          本会话内不再询问
        </label>
        <span>Esc 拒绝 · Enter 确认</span>
      </div>
    </div>
  );
};
