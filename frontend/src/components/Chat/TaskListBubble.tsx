import React from 'react';
import type { TaskListSnapshot, TaskStatus } from '../../types';

interface TaskListBubbleProps {
  snapshot: TaskListSnapshot | null;
  onDismiss: () => void;
}

const MONO =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';

const StatusMark: React.FC<{ status: TaskStatus }> = ({ status }) => {
  if (status === 'completed') {
    return (
      <span
        style={{
          color: '#7fbf7f',
          fontFamily: MONO,
          fontSize: '12px',
          width: '14px',
          textAlign: 'center',
          flexShrink: 0,
        }}
      >
        ✓
      </span>
    );
  }
  if (status === 'in_progress') {
    return (
      <span
        style={{
          width: '14px',
          height: '14px',
          flexShrink: 0,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginTop: '1px',
        }}
        aria-hidden
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <circle cx="6" cy="6" r="5" stroke="rgba(232,232,232,0.35)" strokeWidth="1.5" fill="none" />
          <circle
            cx="6"
            cy="6"
            r="5"
            stroke="#e8e8e8"
            strokeWidth="1.5"
            fill="none"
            strokeDasharray="8 24"
            strokeLinecap="round"
            style={{
              transformOrigin: 'center',
              animation: 'tk-task-spin 1.2s linear infinite',
            }}
          />
        </svg>
      </span>
    );
  }
  if (status === 'paused') {
    return (
      <span
        style={{
          color: 'rgba(217,163,102,0.85)',
          fontFamily: MONO,
          fontSize: '11px',
          width: '14px',
          textAlign: 'center',
          flexShrink: 0,
        }}
        aria-label="已暂停"
      >
        ⏸
      </span>
    );
  }
  return (
    <span
      style={{
        color: 'rgba(255,255,255,0.32)',
        fontFamily: MONO,
        fontSize: '12px',
        width: '14px',
        textAlign: 'center',
        flexShrink: 0,
      }}
    >
      ○
    </span>
  );
};

export const TaskListBubble: React.FC<TaskListBubbleProps> = ({ snapshot, onDismiss }) => {
  const [expanded, setExpanded] = React.useState(true);
  // Reset to expanded whenever a new task list arrives (different
  // task_list_id) so the user always sees the full plan first.
  const lastIdRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!snapshot) {
      lastIdRef.current = null;
      return;
    }
    if (lastIdRef.current !== snapshot.task_list_id) {
      lastIdRef.current = snapshot.task_list_id;
      setExpanded(true);
    }
  }, [snapshot?.task_list_id]);

  const total = snapshot?.tasks.length ?? 0;
  const completed = snapshot?.tasks.filter((t) => t.status === 'completed').length ?? 0;
  const allDone = total > 0 && completed === total;
  const anyPausedRaw = snapshot?.tasks.some((t) => t.status === 'paused') ?? false;
  // "Turn over" means either everything's done OR the agent stopped and
  // some tasks were paused (we surface paused on turn-end from the
  // server). Both should pop the bubble back open and auto-dismiss.
  const turnFinalized = allDone || anyPausedRaw;

  // We want auto-expand + 5s auto-close to fire ONCE per task list id
  // when it enters its final state. Track the trigger in a ref so an
  // unrelated re-render (e.g. parent re-mount) doesn't re-trigger or
  // tear down the timer. Keep the timer in a ref too — putting it in
  // the effect's cleanup caused the parent's inline onDismiss to clear
  // it before it could fire.
  const finalizedIdRef = React.useRef<string | null>(null);
  const dismissTimerRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (!snapshot || !turnFinalized) return;
    if (finalizedIdRef.current === snapshot.task_list_id) return;
    finalizedIdRef.current = snapshot.task_list_id;
    setExpanded(true);
    if (dismissTimerRef.current !== null) {
      window.clearTimeout(dismissTimerRef.current);
    }
    dismissTimerRef.current = window.setTimeout(() => {
      onDismiss();
      dismissTimerRef.current = null;
    }, 5000);
  }, [snapshot?.task_list_id, turnFinalized, onDismiss]);

  // Clean up the auto-dismiss timer only when the component truly unmounts.
  React.useEffect(() => {
    return () => {
      if (dismissTimerRef.current !== null) {
        window.clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = null;
      }
    };
  }, []);

  if (!snapshot || !snapshot.tasks.length) return null;

  const inProgress = snapshot.tasks.find((t) => t.status === 'in_progress');
  const anyPaused = snapshot.tasks.some((t) => t.status === 'paused');
  const statusLabel = allDone
    ? 'completed'
    : inProgress
      ? 'running'
      : anyPaused
        ? 'paused'
        : 'queued';
  const statusColor = allDone
    ? '#7fbf7f'
    : inProgress
      ? '#d8d8d8'
      : anyPaused
        ? '#d9a366'
        : '#9a9a9a';

  return (
    <div
      style={{
        marginBottom: '10px',
        width: '100%',
        background: '#161616',
        border: '1px solid rgba(255,255,255,0.10)',
        borderRadius: '12px',
        overflow: 'hidden',
        fontFamily: MONO,
        animation: 'tk-task-fade-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <style>
        {`
          @keyframes tk-task-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
          @keyframes tk-task-fade-in {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>

      {/* Header — click anywhere except the × to toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0',
          padding: '0',
        }}
      >
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setExpanded((v) => !v)}
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 4px 8px 12px',
            background: 'transparent',
            border: 'none',
            color: '#cfcfcf',
            fontFamily: MONO,
            fontSize: '11.5px',
            cursor: 'pointer',
            outline: 'none',
            textAlign: 'left',
            minWidth: 0,
          }}
        >
          <span
            style={{
              color: '#7f7f7f',
              fontSize: '10px',
              width: '10px',
              display: 'inline-block',
              transition: 'transform 160ms ease',
              transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
              flexShrink: 0,
            }}
          >
            ▸
          </span>
          <span style={{ color: '#a8a8a8', flexShrink: 0 }}>TASK</span>
          <span
            style={{
              color: statusColor,
              fontSize: '11px',
              padding: '1px 6px',
              border: `1px solid ${statusColor}33`,
              borderRadius: '3px',
              background: `${statusColor}10`,
              flexShrink: 0,
            }}
          >
            {statusLabel}
          </span>
          <span style={{ color: '#7f7f7f', flexShrink: 0 }}>
            {completed}/{total}
          </span>
          {!expanded && (inProgress || anyPaused) ? (
            <span
              style={{
                color: '#bdbdbd',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontFamily: 'inherit',
                minWidth: 0,
              }}
            >
              · {(inProgress || snapshot.tasks.find((t) => t.status === 'paused'))?.content}
            </span>
          ) : (
            <span style={{ flex: 1 }} />
          )}
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onDismiss}
          aria-label="关闭任务列表"
          title="关闭"
          style={{
            flexShrink: 0,
            width: '28px',
            height: '28px',
            margin: '4px 8px 4px 0',
            background: 'transparent',
            border: 'none',
            color: '#7f7f7f',
            fontSize: '14px',
            lineHeight: 1,
            cursor: 'pointer',
            borderRadius: '6px',
            outline: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'background 120ms ease, color 120ms ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.06)';
            (e.currentTarget as HTMLButtonElement).style.color = '#e0e0e0';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
            (e.currentTarget as HTMLButtonElement).style.color = '#7f7f7f';
          }}
        >
          ×
        </button>
      </div>

      {/* Body — task list */}
      {expanded ? (
        <div
          style={{
            borderTop: '1px solid rgba(255,255,255,0.05)',
            padding: '6px 0',
            maxHeight: '320px',
            overflowY: 'auto',
          }}
        >
          {snapshot.tasks.map((task, idx) => {
            const isCompleted = task.status === 'completed';
            const isInProgress = task.status === 'in_progress';
            return (
              <div
                key={task.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  padding: '5px 14px',
                  background: isInProgress ? 'rgba(255,255,255,0.035)' : 'transparent',
                  fontSize: '12px',
                  lineHeight: 1.55,
                }}
              >
                <span
                  style={{
                    color: '#5a5a5a',
                    width: '20px',
                    textAlign: 'right',
                    flexShrink: 0,
                    fontFamily: MONO,
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {String(idx + 1).padStart(2, '0')}
                </span>
                <StatusMark status={task.status} />
                <span
                  style={{
                    flex: 1,
                    color: isCompleted ? '#6a6a6a' : isInProgress ? '#fafafa' : '#bdbdbd',
                    textDecoration: isCompleted ? 'line-through' : 'none',
                    textDecorationColor: isCompleted ? 'rgba(106,106,106,0.55)' : undefined,
                    wordBreak: 'break-word',
                    fontFamily: 'inherit',
                  }}
                >
                  {task.content}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
