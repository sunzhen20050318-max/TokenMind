import React, { useMemo } from 'react';
import { useChatStore } from '../../stores/chatStore';
import './crossSessionApprovalToast.css';

interface CrossSessionApprovalToastProps {
  onJumpToSession: (sessionId: string) => void;
}

interface PendingItem {
  sessionId: string;
  toolName: string;
  command?: string;
}

/**
 * App-level toast that surfaces approvals waiting on background sessions.
 *
 * If the user is looking at session A and session B raises an exec-approval
 * request, the in-chat ToolApprovalModal won't appear (it lives inside
 * ChatWindow which is bound to the foreground session). Without this toast,
 * the user would have no way to know an approval is pending until the 5-minute
 * timeout elapses and the tool is auto-cancelled.
 */
export const CrossSessionApprovalToast: React.FC<CrossSessionApprovalToastProps> = ({
  onJumpToSession,
}) => {
  const currentSession = useChatStore((state) => state.currentSession);
  const sessionsState = useChatStore((state) => state.sessionsState);
  const sessions = useChatStore((state) => state.sessions);
  const projectSessions = useChatStore((state) => state.projectSessions);

  const pendingItems = useMemo<PendingItem[]>(() => {
    return Object.entries(sessionsState)
      .filter(([sessionId, slice]) => sessionId !== currentSession && !!slice.pendingApproval)
      .map(([sessionId, slice]) => ({
        sessionId,
        toolName: slice.pendingApproval!.tool_name,
        command: slice.pendingApproval!.command,
      }));
  }, [currentSession, sessionsState]);

  if (pendingItems.length === 0) {
    return null;
  }

  const labelFor = (sessionId: string): string => {
    const meta =
      sessions.find((s) => s.session_id === sessionId) ||
      projectSessions.find((s) => s.session_id === sessionId);
    return meta?.title || meta?.first_message || sessionId;
  };

  return (
    <div className="cross-session-toast" role="status" aria-live="polite">
      {pendingItems.map((item) => (
        <button
          key={item.sessionId}
          className="cross-session-toast__item"
          onClick={() => onJumpToSession(item.sessionId)}
          type="button"
        >
          <div className="cross-session-toast__head">
            <span className="cross-session-toast__dot" aria-hidden="true" />
            <span className="cross-session-toast__title">需要确认</span>
          </div>
          <div className="cross-session-toast__body">
            会话「{labelFor(item.sessionId)}」请求执行 <code>{item.toolName}</code>
          </div>
          {item.command ? <div className="cross-session-toast__command">{item.command}</div> : null}
          <div className="cross-session-toast__cta">点击切换并审批 →</div>
        </button>
      ))}
    </div>
  );
};
