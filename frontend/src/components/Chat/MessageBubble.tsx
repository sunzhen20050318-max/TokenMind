import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Attachment, Message } from '../../types';
import { BrandMark } from '../BrandMark';

interface MessageBubbleProps {
  message: Message;
}

const ATTACHMENTS_TAG = '[Attached Files';

function extractTextContent(
  content: Message['content'],
  attachments: Attachment[] | undefined
): string {
  const hidePlaceholderPaths = new Set((attachments || []).map((item) => item.path));

  const filterLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) {
      return false;
    }
    if (trimmed.startsWith(ATTACHMENTS_TAG)) {
      return false;
    }
    if (trimmed === 'Attached files are available in the workspace:') {
      return false;
    }
    if (trimmed.startsWith('Use read_file for text-based files when possible.')) {
      return false;
    }
    if (trimmed.startsWith('- ') && attachments?.some((item) => trimmed.includes(item.path))) {
      return false;
    }
    if (/^\[(image|file): .+\]$/.test(trimmed)) {
      const path = trimmed.slice(trimmed.indexOf(':') + 1, -1).trim();
      if (hidePlaceholderPaths.has(path)) {
        return false;
      }
    }
    return true;
  };

  if (typeof content === 'string') {
    return content
      .split('\n')
      .filter(filterLine)
      .join('\n')
      .trim();
  }

  if (Array.isArray(content)) {
    return content
      .map((item) => (item && typeof item === 'object' && typeof item.text === 'string' ? item.text : ''))
      .flatMap((text) => text.split('\n'))
      .filter(filterLine)
      .join('\n')
      .trim();
  }

  return '';
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const renderedContent = extractTextContent(message.content, message.attachments);

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
          <BrandMark size={15} alt="" />
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
          lineHeight: '1.55',
          whiteSpace: 'pre-line',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
          border: isUser ? 'none' : '1px solid #2a2a2a',
        }}
      >
        <div style={{ display: 'block' }}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p style={{ margin: '0', whiteSpace: 'pre-line' }}>{children}</p>,
              ul: ({ children }) => (
                <ul style={{ margin: '6px 0', paddingLeft: '1.15em', whiteSpace: 'normal' }}>{children}</ul>
              ),
              ol: ({ children }) => (
                <ol style={{ margin: '6px 0', paddingLeft: '1.2em', whiteSpace: 'normal' }}>{children}</ol>
              ),
              li: ({ children }) => (
                <li style={{ margin: '2px 0', paddingLeft: '0.12em', lineHeight: '1.55', whiteSpace: 'normal' }}>
                  {children}
                </li>
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
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {children}
                </pre>
              ),
            }}
          >
            {renderedContent || (message.attachments?.length ? '已附带文件' : '')}
          </ReactMarkdown>

          {message.attachments && message.attachments.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px',
                marginTop: renderedContent ? '10px' : '0',
              }}
            >
              {message.attachments.map((attachment) => (
                <div
                  key={`${attachment.path}-${attachment.name}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '7px 10px',
                    borderRadius: '12px',
                    backgroundColor: isUser ? '#f3f3f3' : '#111111',
                    border: isUser ? '1px solid #e1e1e1' : '1px solid #2a2a2a',
                    color: isUser ? '#111' : '#d5d5d5',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{attachment.name}</span>
                  {attachment.category ? (
                    <span style={{ color: isUser ? '#666' : '#8d8d8d', textTransform: 'capitalize' }}>
                      {attachment.category}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          )}

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
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
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
