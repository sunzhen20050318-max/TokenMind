import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../types';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        alignItems: 'flex-start',
        marginBottom: '2px',
        padding: '0 16px',
        gap: '8px',
        animation: 'fadeIn 0.2s ease-out',
      }}
    >
      {!isUser && (
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '50%',
            backgroundColor: '#1c1c1e',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            border: '1px solid #333',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5">
            <circle cx="12" cy="12" r="4" fill="white" stroke="white"/>
            <line x1="12" y1="2" x2="12" y2="4"/>
            <line x1="12" y1="20" x2="12" y2="22"/>
            <line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/>
            <line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/>
            <line x1="2" y1="12" x2="4" y2="12"/>
            <line x1="20" y1="12" x2="22" y2="12"/>
            <line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/>
            <line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/>
          </svg>
        </div>
      )}
      <div
        style={{
          maxWidth: '70%',
          padding: '10px 14px',
          borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 4px',
          backgroundColor: isUser ? '#ffffff' : '#1c1c1e',
          color: isUser ? '#000' : '#e5e5e5',
          fontSize: '14px',
          lineHeight: '1.4',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          border: isUser ? 'none' : '1px solid #2a2a2a',
        }}
      >
        <div style={{ display: 'inline' }}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p style={{ margin: '0' }}>{children}</p>,
              ul: ({ children }) => (
                <ul style={{ margin: '4px 0', paddingLeft: '18px' }}>{children}</ul>
              ),
              ol: ({ children }) => (
                <ol style={{ margin: '4px 0', paddingLeft: '18px' }}>{children}</ol>
              ),
              li: ({ children }) => (
                <li style={{ margin: '2px 0' }}>{children}</li>
              ),
              code: ({ children, ...props }) => {
                const inline = !(props as any).node?.properties?.directive;
                return inline ? (
                  <code
                    style={{
                      backgroundColor: isUser ? '#f0f0f0' : '#0a0a0a',
                      padding: '2px 5px',
                      borderRadius: '4px',
                      fontSize: '12.5px',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                      color: isUser ? '#0066cc' : '#a0a0a0',
                    }}
                  >
                    {children}
                  </code>
                ) : (
                  <code>{children}</code>
                );
              },
              pre: ({ children }) => (
                <pre
                  style={{
                    backgroundColor: '#0a0a0a',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    overflow: 'auto',
                    margin: '6px 0',
                    border: '1px solid #2a2a2a',
                  }}
                >
                  {children}
                </pre>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          {message.isStreaming && (
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '1em',
                marginLeft: '3px',
                verticalAlign: 'text-bottom',
                backgroundColor: isUser ? '#111' : '#7f7f7f',
                opacity: 0.9,
                animation: 'blink 1s steps(1) infinite',
              }}
            />
          )}
        </div>
      </div>
      {isUser && (
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '50%',
            backgroundColor: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#000">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
          </svg>
        </div>
      )}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes blink {
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
};
