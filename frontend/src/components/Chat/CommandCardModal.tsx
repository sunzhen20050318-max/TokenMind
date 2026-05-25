import React from 'react';

export interface CommandCardOption {
  value: string;
  label: string;
  hint?: string;
  badge?: string;
  disabled?: boolean;
}

interface CommandCardModalProps {
  title: string;
  subtitle?: string;
  options: ReadonlyArray<CommandCardOption>;
  selectedValue: string | null;
  onSubmit: (value: string) => void;
  onCancel: () => void;
  footerHint?: string;
  /** Optional left-side icon glyph (single character). */
  icon?: string;
}

const MONO =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';

/**
 * Shared single-select card used by /personality, /model, /reasoning,
 * and any future slash-command setting picker. Visual style mirrors
 * ToolApprovalModal / TaskListBubble so the whole slash family looks
 * like one family.
 *
 * Keyboard: ↑↓ to move, Enter to confirm, Esc to cancel, digits 1-9 to
 * jump straight to that option.
 */
export const CommandCardModal: React.FC<CommandCardModalProps> = ({
  title,
  subtitle,
  options,
  selectedValue,
  onSubmit,
  onCancel,
  footerHint,
  icon,
}) => {
  const initialIndex = Math.max(
    0,
    options.findIndex((option) => option.value === selectedValue),
  );
  const [highlightIndex, setHighlightIndex] = React.useState(initialIndex);

  React.useEffect(() => {
    setHighlightIndex(initialIndex);
    // We only want this on open / selectedValue change — options is a
    // ref-stable list from the caller's useMemo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedValue]);

  // Defer attaching the global Enter handler by a frame. Without this
  // delay the same Enter keystroke that triggered the slash-menu's
  // ``dispatchSlashCommand`` (which set ``openCard`` and mounted this
  // modal) could be caught by our fresh window listener on browsers
  // that fire keydown-repeat or for users holding the key — the
  // result was the card flashing open and auto-confirming the current
  // selection before the user saw any options. 100ms is well under
  // human reaction time so a deliberate Enter is unaffected.
  const armedRef = React.useRef(false);
  React.useEffect(() => {
    const armTimer = window.setTimeout(() => {
      armedRef.current = true;
    }, 120);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlightIndex((idx) => {
          let next = idx;
          for (let step = 0; step < options.length; step += 1) {
            next = (next + 1) % options.length;
            if (!options[next]?.disabled) return next;
          }
          return idx;
        });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlightIndex((idx) => {
          let next = idx;
          for (let step = 0; step < options.length; step += 1) {
            next = (next - 1 + options.length) % options.length;
            if (!options[next]?.disabled) return next;
          }
          return idx;
        });
        return;
      }
      if (e.key === 'Enter') {
        if (!armedRef.current) return;
        e.preventDefault();
        const target = options[highlightIndex];
        if (target && !target.disabled) onSubmit(target.value);
        return;
      }
      const digit = parseInt(e.key, 10);
      if (!Number.isNaN(digit) && digit >= 1 && digit <= options.length) {
        const target = options[digit - 1];
        if (target && !target.disabled) {
          e.preventDefault();
          setHighlightIndex(digit - 1);
          onSubmit(target.value);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(armTimer);
      window.removeEventListener('keydown', onKey);
    };
  }, [highlightIndex, options, onCancel, onSubmit]);

  return (
    <div
      role="dialog"
      aria-label={title}
      style={{
        marginBottom: '10px',
        background: '#161616',
        border: '1px solid rgba(255,255,255,0.10)',
        borderRadius: '12px',
        overflow: 'hidden',
        fontFamily: MONO,
        boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
        animation: 'tk-cmd-card-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`
          @keyframes tk-cmd-card-in {
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
        {icon ? (
          <span style={{ color: '#9a9a9a', marginRight: '8px', fontSize: '13px' }}>{icon}</span>
        ) : null}
        <span style={{ color: '#e8e8e8', fontSize: '12px' }}>{title}</span>
        {subtitle ? (
          <span style={{ marginLeft: '10px', color: '#7f7f7f', fontSize: '11px' }}>
            {subtitle}
          </span>
        ) : null}
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onCancel}
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

      <div style={{ padding: '6px 0', maxHeight: '320px', overflowY: 'auto' }}>
        {options.map((option, idx) => {
          const active = idx === highlightIndex && !option.disabled;
          const isCurrent = option.value === selectedValue;
          return (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={active}
              disabled={option.disabled}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => !option.disabled && setHighlightIndex(idx)}
              onClick={() => !option.disabled && onSubmit(option.value)}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                width: '100%',
                padding: '8px 14px',
                background: active ? 'rgba(255,255,255,0.05)' : 'transparent',
                border: 'none',
                color: option.disabled ? '#5a5a5a' : active ? '#fafafa' : '#cfcfcf',
                fontFamily: MONO,
                fontSize: '12px',
                textAlign: 'left',
                cursor: option.disabled ? 'not-allowed' : 'pointer',
                outline: 'none',
              }}
            >
              <span
                style={{
                  color: option.disabled ? '#3a3a3a' : '#5a5a5a',
                  width: '22px',
                  textAlign: 'right',
                  flexShrink: 0,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {idx + 1}.
              </span>
              <span
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '2px',
                  flex: 1,
                  minWidth: 0,
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>{option.label}</span>
                  {option.badge ? (
                    <span
                      style={{
                        color: '#cfcfcf',
                        fontSize: '10.5px',
                        padding: '1px 6px',
                        border: '1px solid rgba(255,255,255,0.18)',
                        borderRadius: '3px',
                        background: 'rgba(255,255,255,0.05)',
                      }}
                    >
                      {option.badge}
                    </span>
                  ) : null}
                  {isCurrent ? (
                    <span style={{ color: '#9a9a9a', fontSize: '11px' }}>· 当前</span>
                  ) : null}
                </span>
                {option.hint ? (
                  <span
                    style={{
                      color: option.disabled ? '#444' : '#7f7f7f',
                      fontSize: '11px',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {option.hint}
                  </span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>

      <div
        style={{
          padding: '8px 14px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          color: '#7f7f7f',
          fontSize: '10.5px',
          letterSpacing: '0.04em',
        }}
      >
        {footerHint || '↑↓ 选择 · ↵ 确认 · 1-9 直选 · Esc 取消'}
      </div>
    </div>
  );
};
