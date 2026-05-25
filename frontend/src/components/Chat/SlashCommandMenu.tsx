import React from 'react';

export interface SlashCommandOption {
  name: string;
  description: string;
}

interface SlashCommandMenuProps {
  options: SlashCommandOption[];
  selectedIndex: number;
  onHover: (index: number) => void;
  onSelect: (option: SlashCommandOption) => void;
}

const MONO =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';

/**
 * Dropdown rendered above the composer when the user types ``/`` at the
 * start of the textarea. Visual style matches ToolApprovalModal /
 * TaskListBubble (dark card, 12px radius, monospace) so the slash
 * surface feels like part of the same family.
 */
export const SlashCommandMenu: React.FC<SlashCommandMenuProps> = ({
  options,
  selectedIndex,
  onHover,
  onSelect,
}) => {
  if (options.length === 0) return null;

  return (
    <div
      role="listbox"
      aria-label="斜杠命令"
      style={{
        background: '#161616',
        border: '1px solid rgba(255,255,255,0.10)',
        borderRadius: '12px',
        overflow: 'hidden',
        fontFamily: MONO,
        marginBottom: '8px',
        boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
        animation: 'tk-slash-fade-in 160ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`
          @keyframes tk-slash-fade-in {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>

      <div
        style={{
          padding: '8px 14px 6px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          color: '#7f7f7f',
          fontSize: '10.5px',
          letterSpacing: '0.04em',
        }}
      >
        SLASH COMMAND · ↑↓ 选择 · ↵ 执行 · Esc 取消
      </div>

      <div style={{ padding: '4px 0', maxHeight: '280px', overflowY: 'auto' }}>
        {options.map((option, idx) => {
          const active = idx === selectedIndex;
          return (
            <button
              key={option.name}
              type="button"
              role="option"
              aria-selected={active}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => onHover(idx)}
              onClick={() => onSelect(option)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'baseline',
                gap: '12px',
                padding: '7px 14px',
                background: active ? 'rgba(255,255,255,0.05)' : 'transparent',
                border: 'none',
                color: active ? '#fafafa' : '#cfcfcf',
                fontFamily: MONO,
                fontSize: '12px',
                textAlign: 'left',
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <span
                style={{
                  color: active ? '#e8e8e8' : '#9a9a9a',
                  width: '90px',
                  flexShrink: 0,
                }}
              >
                /{option.name}
              </span>
              <span
                style={{
                  color: active ? '#bdbdbd' : '#7f7f7f',
                  fontSize: '11.5px',
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  minWidth: 0,
                }}
              >
                {option.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
