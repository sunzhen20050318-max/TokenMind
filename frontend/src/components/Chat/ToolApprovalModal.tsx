import React from 'react';
import type { PendingToolApproval } from '../../types';

interface ToolApprovalModalProps {
  approval: PendingToolApproval | null;
  onApprove: () => void;
  onReject: () => void;
  onTrustAndApprove: () => void;
}

export const ToolApprovalModal: React.FC<ToolApprovalModalProps> = ({
  approval,
  onApprove,
  onReject,
  onTrustAndApprove,
}) => {
  const [remainingMs, setRemainingMs] = React.useState(0);

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

  if (!approval) {
    return null;
  }

  const secondsLeft = Math.max(0, Math.ceil(remainingMs / 1000));

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.62)',
        backdropFilter: 'blur(10px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        zIndex: 120,
      }}
    >
      <div
        style={{
          width: 'min(680px, 100%)',
          background: 'linear-gradient(180deg, rgba(22,22,22,0.98) 0%, rgba(11,11,11,0.98) 100%)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '22px',
          boxShadow: '0 24px 80px rgba(0,0,0,0.45)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '18px 22px 14px',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
          }}
        >
          <div>
            <div
              style={{
                fontSize: '11px',
                letterSpacing: '0.18em',
                color: '#8a8a8a',
                textTransform: 'uppercase',
                marginBottom: '8px',
              }}
            >
              Security Check
            </div>
            <h3
              style={{
                margin: 0,
                fontSize: '22px',
                color: '#f4f4f4',
                fontWeight: 600,
              }}
            >
              允许执行高风险命令吗？
            </h3>
          </div>
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '999px',
              background: 'rgba(255,255,255,0.04)',
              color: '#bdbdbd',
              fontSize: '12px',
              whiteSpace: 'nowrap',
            }}
          >
            {approval.timeout_s ? `${secondsLeft}s 内需要确认` : '等待确认'}
          </div>
        </div>

        <div style={{ padding: '20px 22px 22px', display: 'grid', gap: '16px' }}>
          <div
            style={{
              borderRadius: '16px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.08)',
              padding: '14px 16px',
            }}
          >
            <div style={{ fontSize: '12px', color: '#8d8d8d', marginBottom: '6px' }}>风险原因</div>
            <div style={{ fontSize: '14px', lineHeight: 1.65, color: '#f0f0f0' }}>
              {approval.risk_reason}
            </div>
          </div>

          <div
            style={{
              borderRadius: '16px',
              background: '#090909',
              border: '1px solid rgba(255,255,255,0.08)',
              padding: '16px',
            }}
          >
            <div style={{ fontSize: '12px', color: '#8d8d8d', marginBottom: '8px' }}>命令内容</div>
            <code
              style={{
                display: 'block',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                fontSize: '13px',
                color: '#f4f4f4',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
              }}
            >
              {approval.command}
            </code>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '12px',
            }}
          >
            <div
              style={{
                borderRadius: '14px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                padding: '12px 14px',
              }}
            >
              <div style={{ fontSize: '12px', color: '#8d8d8d', marginBottom: '4px' }}>工具</div>
              <div style={{ fontSize: '14px', color: '#f4f4f4' }}>{approval.tool_name}</div>
            </div>
            <div
              style={{
                borderRadius: '14px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                padding: '12px 14px',
              }}
            >
              <div style={{ fontSize: '12px', color: '#8d8d8d', marginBottom: '4px' }}>工作目录</div>
              <div style={{ fontSize: '14px', color: '#f4f4f4', wordBreak: 'break-word' }}>
                {approval.working_dir}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '4px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={onTrustAndApprove}
              style={{
                minWidth: '148px',
                borderRadius: '999px',
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'rgba(255,255,255,0.06)',
                color: '#f3f3f3',
                padding: '11px 18px',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              本会话始终允许
            </button>
            <button
              type="button"
              onClick={onReject}
              style={{
                minWidth: '124px',
                borderRadius: '999px',
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'rgba(255,255,255,0.04)',
                color: '#f3f3f3',
                padding: '11px 18px',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              拒绝执行
            </button>
            <button
              type="button"
              onClick={onApprove}
              style={{
                minWidth: '124px',
                borderRadius: '999px',
                border: 'none',
                background: '#f4f4f4',
                color: '#0b0b0b',
                padding: '11px 18px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              允许执行
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
