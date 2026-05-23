import React from 'react';
import type {
  PendingUserQuestion,
  UserQuestionAnswer,
  UserQuestionItem,
} from '../../types';

interface UserQuestionModalProps {
  question: PendingUserQuestion | null;
  onSubmit: (answers: Record<string, UserQuestionAnswer>) => void;
  onCancel: () => void;
}

const ACCENT_BG = 'rgba(255,255,255,0.07)';
const ACCENT_LINE = '#d8d8d8';
const ACCENT_FILL = '#e8e8e8';
const ACCENT_FG = '#0b0b0b';
const OTHER_LABEL = 'Other';

interface PerQuestionState {
  selected: Set<string>;
  otherText: string;
}

function emptyState(): PerQuestionState {
  return { selected: new Set(), otherText: '' };
}

function isQuestionAnswered(_item: UserQuestionItem, state: PerQuestionState): boolean {
  if (state.selected.size === 0) return false;
  if (state.selected.has(OTHER_LABEL) && !state.otherText.trim()) return false;
  return true;
}

function buildAnswer(item: UserQuestionItem, state: PerQuestionState): UserQuestionAnswer {
  const labels = Array.from(state.selected);
  const hasOther = state.selected.has(OTHER_LABEL);
  const notes = hasOther ? state.otherText.trim() || undefined : undefined;
  if (item.multiSelect) {
    return { selected: labels, notes };
  }
  return { selected: labels[0] ?? '', notes };
}

export const UserQuestionModal: React.FC<UserQuestionModalProps> = ({
  question,
  onSubmit,
  onCancel,
}) => {
  const [activeTab, setActiveTab] = React.useState(0);
  const [states, setStates] = React.useState<PerQuestionState[]>([]);
  const [cursor, setCursor] = React.useState(0);
  const otherInputRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    if (!question) return;
    setActiveTab(0);
    setStates(question.questions.map(() => emptyState()));
    setCursor(0);
  }, [question?.question_id]);

  // Reset cursor whenever the tab changes so the new tab starts at the
  // first option rather than carrying the cursor index forward.
  React.useEffect(() => {
    setCursor(0);
  }, [activeTab]);

  const items = question?.questions ?? [];
  const tabCount = items.length;
  const currentIdx = tabCount > 0 ? Math.min(activeTab, tabCount - 1) : 0;
  const currentItem = items[currentIdx] as UserQuestionItem | undefined;
  const currentState = states[currentIdx] ?? emptyState();
  // Option list = explicit options + the synthetic "Other" entry.
  const optionLabels: string[] = currentItem
    ? [...currentItem.options.map((o) => o.label), OTHER_LABEL]
    : [];
  const totalOptions = optionLabels.length;
  const allAnswered =
    tabCount > 0 &&
    items.every((item, i) => isQuestionAnswered(item, states[i] ?? emptyState()));

  const updateState = (idx: number, patch: Partial<PerQuestionState>) => {
    setStates((prev) => {
      const next = prev.slice();
      const cur = next[idx] ?? emptyState();
      next[idx] = {
        selected: patch.selected ?? cur.selected,
        otherText: patch.otherText ?? cur.otherText,
      };
      return next;
    });
  };

  const selectSingle = (label: string) => {
    updateState(currentIdx, { selected: new Set([label]) });
  };

  const toggleMulti = (label: string) => {
    const sel = new Set(currentState.selected);
    if (sel.has(label)) sel.delete(label);
    else sel.add(label);
    updateState(currentIdx, { selected: sel });
  };

  const submit = (overrideStates?: PerQuestionState[]) => {
    const useStates = overrideStates ?? states;
    const ok = items.every((item, i) =>
      isQuestionAnswered(item, useStates[i] ?? emptyState()),
    );
    if (!ok) return;
    const out: Record<string, UserQuestionAnswer> = {};
    items.forEach((item, i) => {
      out[item.header || `q${i + 1}`] = buildAnswer(
        item,
        useStates[i] ?? emptyState(),
      );
    });
    onSubmit(out);
  };

  // Try to commit the current tab and move forward. Returns true if the
  // tab was actually answered and we advanced (or submitted on the last
  // tab), false if the user still needs to make a valid choice.
  const advance = () => {
    if (!currentItem) return false;
    if (!isQuestionAnswered(currentItem, currentState)) return false;
    if (currentIdx < tabCount - 1) {
      setActiveTab(currentIdx + 1);
    } else {
      submit();
    }
    return true;
  };

  // Mouse click on an option. For single-select this is the two-step
  // "first click selects, second click confirms" pattern. For multi-
  // select clicks always toggle; advance happens via Enter / button.
  const handleOptionClick = (label: string, idx: number) => {
    if (!currentItem) return;
    setCursor(idx);
    if (currentItem.multiSelect) {
      toggleMulti(label);
      return;
    }
    const alreadySelected = currentState.selected.has(label);
    if (!alreadySelected) {
      selectSingle(label);
      // If the user clicked "Other", focus the textarea immediately so
      // they can start typing without an extra click.
      if (label === OTHER_LABEL) {
        window.setTimeout(() => otherInputRef.current?.focus(), 0);
      }
      return;
    }
    // Second click on the already-selected option = confirm + advance.
    // For "Other" we still need text before we can advance.
    if (label === OTHER_LABEL && !currentState.otherText.trim()) {
      otherInputRef.current?.focus();
      return;
    }
    advance();
  };

  React.useEffect(() => {
    if (!question || !currentItem) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inTextarea = target?.tagName === 'TEXTAREA';

      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        return;
      }

      if (inTextarea) {
        // While typing into the "Other" textarea only intercept Enter
        // (advance) and Shift+Enter (newline default).
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (currentState.otherText.trim()) advance();
        }
        return;
      }

      // Tab navigation (only useful when there are multiple questions).
      if (e.key === 'ArrowLeft' && tabCount > 1) {
        e.preventDefault();
        setActiveTab((t) => (t > 0 ? t - 1 : tabCount - 1));
        return;
      }
      if (e.key === 'ArrowRight' && tabCount > 1) {
        e.preventDefault();
        setActiveTab((t) => (t < tabCount - 1 ? t + 1 : 0));
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = (cursor + 1) % totalOptions;
        setCursor(next);
        // For single-select, moving the cursor also moves the selection
        // so the user sees what they'd commit if they hit Enter now.
        if (!currentItem.multiSelect) {
          selectSingle(optionLabels[next]);
        }
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const next = (cursor - 1 + totalOptions) % totalOptions;
        setCursor(next);
        if (!currentItem.multiSelect) {
          selectSingle(optionLabels[next]);
        }
        return;
      }

      // Digit shortcut: 1-9 select that option directly.
      if (/^[1-9]$/.test(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        if (idx < totalOptions) {
          e.preventDefault();
          setCursor(idx);
          const label = optionLabels[idx];
          if (currentItem.multiSelect) toggleMulti(label);
          else selectSingle(label);
        }
        return;
      }

      // Space toggles in multi-select; in single-select it acts like
      // Enter (commit current cursor + advance).
      if (e.key === ' ') {
        e.preventDefault();
        const label = optionLabels[cursor];
        if (currentItem.multiSelect) toggleMulti(label);
        else {
          selectSingle(label);
        }
        return;
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        // If the user navigated with arrows in single-select, selection
        // is already in sync with cursor — just advance. If they were
        // multi-select, advance requires ≥1 selected (handled inside).
        // If "Other" is the only thing selected but no text yet, focus
        // the textarea instead of advancing.
        if (
          currentState.selected.has(OTHER_LABEL) &&
          !currentState.otherText.trim()
        ) {
          otherInputRef.current?.focus();
          return;
        }
        advance();
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    question,
    cursor,
    activeTab,
    currentItem,
    currentState,
    totalOptions,
    tabCount,
    optionLabels,
    onCancel,
  ]);

  const renderOption = (label: string, description: string | undefined, idx: number) => {
    const isSelected = currentState.selected.has(label);
    const isCursor = cursor === idx;
    // Visual: selection (commit-bound) is shown via background +
    // left-line + filled radio. The cursor (keyboard focus) is shown
    // via a slightly lighter outline so the user knows where Enter
    // will act, even in multi-select where cursor != selected.
    const showCursorOnly = isCursor && !isSelected;
    return (
      <div
        key={label}
        role="button"
        tabIndex={-1}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => handleOptionClick(label, idx)}
        style={{
          display: 'flex',
          gap: '10px',
          padding: '9px 12px',
          borderRadius: '7px',
          background: isSelected
            ? ACCENT_BG
            : showCursorOnly
              ? 'rgba(255,255,255,0.03)'
              : 'transparent',
          borderLeft: isSelected
            ? `3px solid ${ACCENT_LINE}`
            : showCursorOnly
              ? '3px solid rgba(255,255,255,0.18)'
              : '3px solid transparent',
          cursor: 'pointer',
          color: isSelected ? '#fafafa' : '#cfcfcf',
          fontSize: '13px',
          userSelect: 'none',
          outline: 'none',
          transition: 'background 80ms ease, color 80ms ease',
          alignItems: 'flex-start',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '14px',
            height: '14px',
            marginTop: '2px',
            borderRadius: currentItem?.multiSelect ? '3px' : '50%',
            border: `1.5px solid ${isSelected ? ACCENT_FILL : '#666'}`,
            background: isSelected ? ACCENT_FILL : 'transparent',
            flexShrink: 0,
          }}
        >
          {isSelected ? (
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: currentItem?.multiSelect ? '1px' : '50%',
                background: ACCENT_FG,
              }}
            />
          ) : null}
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
          <span style={{ fontWeight: 500 }}>{label}</span>
          {description ? (
            <span style={{ fontSize: '11.5px', color: '#888', lineHeight: 1.45 }}>
              {description}
            </span>
          ) : null}
        </div>
      </div>
    );
  };

  if (!question || tabCount === 0 || !currentItem) return null;

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
        animation: 'tk-question-rise 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`@keyframes tk-question-rise {
            from { opacity: 0; transform: translateY(12px); }
            to   { opacity: 1; transform: translateY(0); }
          }`}
      </style>

      {tabCount > 1 ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            padding: '0 8px',
          }}
        >
          <div style={{ display: 'flex', gap: '2px', overflowX: 'auto' }}>
            {items.map((item, i) => {
              const answered = isQuestionAnswered(item, states[i] ?? emptyState());
              const isActive = i === currentIdx;
              return (
                <button
                  key={i}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setActiveTab(i)}
                  style={{
                    padding: '10px 12px',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: isActive
                      ? `2px solid ${ACCENT_FILL}`
                      : '2px solid transparent',
                    color: isActive ? '#f4f4f4' : '#9a9a9a',
                    cursor: 'pointer',
                    fontSize: '12.5px',
                    fontWeight: isActive ? 600 : 500,
                    whiteSpace: 'nowrap',
                    outline: 'none',
                  }}
                >
                  {item.header}
                  {answered ? (
                    <span style={{ marginLeft: '6px', color: '#7fbf7f', fontSize: '11px' }}>
                      ✓
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={onCancel}
            aria-label="取消"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#888',
              fontSize: '16px',
              cursor: 'pointer',
              padding: '8px 10px',
              outline: 'none',
            }}
          >
            ×
          </button>
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            padding: '4px 4px 0',
          }}
        >
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={onCancel}
            aria-label="取消"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#888',
              fontSize: '16px',
              cursor: 'pointer',
              padding: '6px 10px',
              outline: 'none',
            }}
          >
            ×
          </button>
        </div>
      )}

      <div style={{ padding: '12px 16px 4px' }}>
        <h3
          style={{
            margin: 0,
            fontSize: '13.5px',
            fontWeight: 600,
            color: '#f0f0f0',
            lineHeight: 1.5,
          }}
        >
          {currentItem.question}
        </h3>
        {currentItem.multiSelect ? (
          <div style={{ marginTop: '4px', fontSize: '11px', color: '#7f7f7f' }}>
            可多选
          </div>
        ) : null}
      </div>

      <div
        style={{
          padding: '6px 8px 4px',
          display: 'flex',
          flexDirection: 'column',
          gap: '1px',
        }}
      >
        {currentItem.options.map((opt, i) => renderOption(opt.label, opt.description, i))}
        {renderOption(OTHER_LABEL, '让我自己说', currentItem.options.length)}
      </div>

      {currentState.selected.has(OTHER_LABEL) ? (
        <div style={{ padding: '2px 16px 8px' }}>
          <textarea
            ref={otherInputRef}
            value={currentState.otherText}
            onChange={(e) => updateState(currentIdx, { otherText: e.target.value })}
            placeholder="输入你的回答…（Enter 确认，Shift+Enter 换行）"
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
        </div>
      ) : null}

      <div
        style={{
          padding: '10px 16px 12px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        <span style={{ fontSize: '11px', color: '#7f7f7f' }}>
          {tabCount > 1
            ? '↑↓ 选项 · ←→ 切 tab · Enter 下一题 · Esc 取消'
            : '↑↓ 选项 · Enter 提交 · Esc 取消'}
        </span>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => submit()}
          disabled={!allAnswered}
          style={{
            padding: '7px 16px',
            borderRadius: '6px',
            border: 'none',
            background: allAnswered ? ACCENT_FILL : 'rgba(255,255,255,0.08)',
            color: allAnswered ? ACCENT_FG : '#666',
            fontSize: '12.5px',
            fontWeight: 600,
            cursor: allAnswered ? 'pointer' : 'not-allowed',
            outline: 'none',
          }}
        >
          {allAnswered
            ? tabCount > 1
              ? `提交 ${tabCount} 项回答`
              : '提交回答'
            : tabCount > 1
              ? `${items.filter((it, i) => isQuestionAnswered(it, states[i] ?? emptyState())).length}/${tabCount} 已选`
              : '提交回答'}
        </button>
      </div>
    </div>
  );
};
