import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Attachment, Message, MessageCitation } from '../../types';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import { BrandMark } from '../BrandMark';
import { extractTextContent, resolveVisibleCitations } from './messageBubbleContent';
import './messageBubble.css';

interface MessageBubbleProps {
  message: Message;
  embeddedToolChain?: React.ReactNode;
}

function formatAttachmentSize(size?: number): string | null {
  if (typeof size !== 'number' || size <= 0) {
    return null;
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, embeddedToolChain }) => {
  const isUser = message.role === 'user';
  const updateAttachment = useChatStore((state) => state.updateAttachment);
  const renderedContent = extractTextContent(message.content, message.attachments);
  const visibleCitations = useMemo(
    () => resolveVisibleCitations(message, renderedContent),
    [message, renderedContent]
  );
  const [citationsExpanded, setCitationsExpanded] = useState(false);
  const [retainingAttachmentId, setRetainingAttachmentId] = useState<string | null>(null);

  const citationLabel = useMemo(() => {
    const count = visibleCitations.length;
    return count > 0 ? `来源 (${count})` : '来源';
  }, [visibleCitations]);

  const textColor = isUser ? '#111214' : '#ececef';
  const mutedTextColor = isUser ? '#5f636c' : '#979aa3';
  const inlineCodeBackground = isUser ? '#f1f3f6' : '#111215';
  const blockBackground = isUser ? '#f7f8fa' : '#101113';
  const blockBorder = isUser ? '#e0e3e8' : '#292b2f';
  const linkColor = isUser ? '#0a58ca' : '#f1f3f6';

  const handleRetainAttachment = async (attachmentId: string) => {
    setRetainingAttachmentId(attachmentId);
    try {
      const nextAttachment = await api.retainAttachment(attachmentId);
      updateAttachment(attachmentId, nextAttachment);
    } catch (error) {
      console.error('Failed to retain attachment', error);
    } finally {
      setRetainingAttachmentId((current) => (current === attachmentId ? null : current));
    }
  };

  const renderCitation = (citation: MessageCitation, index: number) => (
    <div
      key={`${citation.id || citation.document_id || citation.document_name}-${index}`}
      className="message-bubble__citation-card"
    >
      <div className="message-bubble__citation-title">
        <span className="message-bubble__citation-kb">{citation.knowledge_base_name}</span>
        <span className="message-bubble__citation-separator">/</span>
        <span className="message-bubble__citation-doc">{citation.document_name}</span>
      </div>
      <div className="message-bubble__citation-excerpt">{citation.excerpt}</div>
    </div>
  );

  const renderAttachment = (attachment: Attachment) => {
    const attachmentHref = attachment.id ? api.getAttachmentUrl(attachment.id) : attachment.path;
    const isUserUpload = attachment.origin === 'user_upload';
    const isExpired = attachment.status === 'expired';
    const isSaved = attachment.status === 'saved' && !isUserUpload;
    const isRetaining = !!attachment.id && retainingAttachmentId === attachment.id;
    const canRetain = !!attachment.id && !isUserUpload && attachment.status === 'temporary';
    const canDownload = !!attachmentHref && !isExpired;
    const showStatus = !!attachment.status && (!isUserUpload || isExpired);
    const metaParts = [attachment.category, formatAttachmentSize(attachment.size)].filter(Boolean);

    return (
      <div
        key={`${attachment.id || attachment.path || attachment.name}-${attachment.name}`}
        className={`message-bubble__attachment ${isUser ? 'is-user' : 'is-assistant'} ${attachment.is_image ? 'is-image' : ''} ${isExpired ? 'is-expired' : ''}`}
      >
        {attachment.is_image && canDownload ? (
          <a
            href={attachmentHref}
            target="_blank"
            rel="noreferrer"
            className="message-bubble__attachment-preview"
          >
            <img
              src={attachmentHref}
              alt={attachment.name}
              className="message-bubble__attachment-image"
            />
          </a>
        ) : null}

        <div className="message-bubble__attachment-main">
          {canDownload ? (
            <a
              href={attachmentHref}
              target="_blank"
              rel="noreferrer"
              download={attachment.name}
              className="message-bubble__attachment-body-link"
            >
              <div className="message-bubble__attachment-header">
                <div className="message-bubble__attachment-titlewrap">
                  {!attachment.is_image ? (
                    <span className="message-bubble__attachment-fileicon" aria-hidden="true">
                      📄
                    </span>
                  ) : null}
                  <span className="message-bubble__attachment-name">{attachment.name}</span>
                </div>
                {showStatus ? (
                  <span className={`message-bubble__attachment-status is-${attachment.status}`}>
                    {attachment.status === 'temporary'
                      ? '临时'
                      : attachment.status === 'saved'
                        ? '已保留'
                        : '已过期'}
                  </span>
                ) : null}
              </div>

              {metaParts.length > 0 ? (
                <span className="message-bubble__attachment-type">{metaParts.join(' · ')}</span>
              ) : null}

              {attachment.preview_text ? (
                <div className="message-bubble__attachment-preview-text">{attachment.preview_text}</div>
              ) : null}
            </a>
          ) : (
            <>
              <div className="message-bubble__attachment-header">
                <div className="message-bubble__attachment-titlewrap">
                  {!attachment.is_image ? (
                    <span className="message-bubble__attachment-fileicon" aria-hidden="true">
                      📄
                    </span>
                  ) : null}
                  <span className="message-bubble__attachment-name">{attachment.name}</span>
                </div>
                {showStatus ? (
                  <span className={`message-bubble__attachment-status is-${attachment.status}`}>
                    {attachment.status === 'temporary'
                      ? '临时'
                      : attachment.status === 'saved'
                        ? '已保留'
                        : '已过期'}
                  </span>
                ) : null}
              </div>

              {metaParts.length > 0 ? (
                <span className="message-bubble__attachment-type">{metaParts.join(' · ')}</span>
              ) : null}

              {attachment.preview_text ? (
                <div className="message-bubble__attachment-preview-text">{attachment.preview_text}</div>
              ) : null}
            </>
          )}

          <div className="message-bubble__attachment-actions">
            {canDownload ? (
              <a
                href={attachmentHref}
                target="_blank"
                rel="noreferrer"
                download={attachment.name}
                className="message-bubble__attachment-action"
              >
                下载
              </a>
            ) : (
              <span className="message-bubble__attachment-action is-disabled">已过期</span>
            )}

            {canRetain ? (
              <button
                type="button"
                className="message-bubble__attachment-action"
                onClick={() => handleRetainAttachment(attachment.id!)}
                disabled={isRetaining}
              >
                {isRetaining ? '保留中' : '保留'}
              </button>
            ) : null}

            {isSaved ? (
              <span className="message-bubble__attachment-action is-muted">已转正</span>
            ) : null}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={`message-row ${isUser ? 'is-user' : 'is-assistant'}`}>
      {!isUser ? (
        <div className="message-row__avatar is-assistant">
          <BrandMark size={24} alt="" className="message-row__assistant-mark" variant="icon" />
        </div>
      ) : null}

      <div className="message-row__body">
        <div className={`message-bubble ${isUser ? 'is-user' : 'is-assistant'}`}>
          {embeddedToolChain ? (
            <div className="message-bubble__embedded-toolchain">{embeddedToolChain}</div>
          ) : null}

          <div className="message-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p style={{ margin: '0 0 0.82em', whiteSpace: 'pre-wrap', color: textColor }}>
                    {children}
                  </p>
                ),
                h1: ({ children }) => (
                  <h1
                    style={{
                      margin: '0 0 0.72em',
                      fontSize: '1.56em',
                      lineHeight: 1.2,
                      fontWeight: 700,
                      color: textColor,
                    }}
                  >
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2
                    style={{
                      margin: '0 0 0.68em',
                      fontSize: '1.3em',
                      lineHeight: 1.24,
                      fontWeight: 700,
                      color: textColor,
                    }}
                  >
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3
                    style={{
                      margin: '0 0 0.62em',
                      fontSize: '1.12em',
                      lineHeight: 1.3,
                      fontWeight: 700,
                      color: textColor,
                    }}
                  >
                    {children}
                  </h3>
                ),
                strong: ({ children }) => (
                  <strong style={{ fontWeight: 700, color: textColor }}>{children}</strong>
                ),
                em: ({ children }) => (
                  <em style={{ fontStyle: 'italic', color: textColor }}>{children}</em>
                ),
                ul: ({ children }) => (
                  <ul style={{ margin: '0 0 0.84em', paddingLeft: '1.18em', whiteSpace: 'normal' }}>
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol style={{ margin: '0 0 0.84em', paddingLeft: '1.24em', whiteSpace: 'normal' }}>
                    {children}
                  </ol>
                ),
                li: ({ children }) => (
                  <li
                    style={{
                      margin: '0.2em 0',
                      paddingLeft: '0.06em',
                      lineHeight: '1.72',
                      whiteSpace: 'normal',
                    }}
                  >
                    {children}
                  </li>
                ),
                blockquote: ({ children }) => (
                  <blockquote
                    style={{
                      margin: '0 0 0.9em',
                      padding: '0.06em 0 0.06em 1em',
                      borderLeft: `2px solid ${isUser ? '#d7dbe2' : '#3c3f45'}`,
                      color: mutedTextColor,
                    }}
                  >
                    {children}
                  </blockquote>
                ),
                hr: () => (
                  <hr
                    style={{
                      border: 0,
                      borderTop: `1px solid ${blockBorder}`,
                      margin: '0.9em 0',
                    }}
                  />
                ),
                a: ({ children, href }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      color: linkColor,
                      textDecoration: 'underline',
                      textUnderlineOffset: '2px',
                    }}
                  >
                    {children}
                  </a>
                ),
                table: ({ children }) => (
                  <div style={{ overflowX: 'auto', margin: '0 0 0.95em' }}>
                    <table
                      style={{
                        width: '100%',
                        minWidth: '360px',
                        borderCollapse: 'collapse',
                        fontSize: '13px',
                        color: textColor,
                        border: `1px solid ${blockBorder}`,
                      }}
                    >
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th
                    style={{
                      textAlign: 'left',
                      padding: '8px 10px',
                      background: isUser ? '#f3f5f8' : '#141518',
                      borderBottom: `1px solid ${blockBorder}`,
                      fontWeight: 600,
                    }}
                  >
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td
                    style={{
                      padding: '8px 10px',
                      borderTop: `1px solid ${blockBorder}`,
                      verticalAlign: 'top',
                    }}
                  >
                    {children}
                  </td>
                ),
                code: ({ children, className }) => {
                  const inline = !className;
                  return inline ? (
                    <code
                      style={{
                        backgroundColor: inlineCodeBackground,
                        padding: '2px 5px',
                        borderRadius: '4px',
                        fontSize: '12.5px',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        color: isUser ? '#0b5fc7' : '#e6e8ec',
                      }}
                    >
                      {children}
                    </code>
                  ) : (
                    <code className={className}>{children}</code>
                  );
                },
                pre: ({ children }) => (
                  <pre
                    style={{
                      backgroundColor: blockBackground,
                      padding: '12px 14px',
                      borderRadius: '12px',
                      overflow: 'auto',
                      margin: '0 0 0.92em',
                      border: `1px solid ${blockBorder}`,
                      whiteSpace: 'pre',
                      color: textColor,
                      fontSize: '12.5px',
                      lineHeight: 1.7,
                    }}
                  >
                    {children}
                  </pre>
                ),
              }}
            >
              {renderedContent || (message.attachments?.length ? '已附带文件。' : '')}
            </ReactMarkdown>

            {message.attachments && message.attachments.length > 0 ? (
              <div className="message-bubble__attachments">
                {message.attachments.map(renderAttachment)}
              </div>
            ) : null}

            {!isUser && visibleCitations.length > 0 ? (
              <div className={`message-bubble__citations ${citationsExpanded ? 'is-expanded' : ''}`}>
                <button
                  type="button"
                  className="message-bubble__citations-toggle"
                  onClick={() => setCitationsExpanded((value) => !value)}
                  aria-expanded={citationsExpanded}
                >
                  <span className="message-bubble__citations-label">{citationLabel}</span>
                  <span
                    className={`message-bubble__citations-chevron ${citationsExpanded ? 'is-expanded' : ''}`}
                    aria-hidden="true"
                  >
                    &gt;
                  </span>
                </button>
                <div className="message-bubble__citations-list">{visibleCitations.map(renderCitation)}</div>
              </div>
            ) : null}

            {message.isStreaming ? <span className="message-bubble__cursor" /> : null}
          </div>
        </div>
      </div>

      {isUser ? (
        <div className="message-row__avatar is-user">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#171614">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
        </div>
      ) : null}
    </div>
  );
};
