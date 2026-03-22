import React, { useRef, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputArea } from './InputArea';
import { ToolChain } from './ToolIndicator';
import { useChatStore } from '../../stores/chatStore';
import { useWebSocket } from '../../hooks/useWebSocket';

interface ChatWindowProps {
  sessionId: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ sessionId }) => {
  const { messages, isLoading, activeTool, addMessage, setLoading, toolCalls, setActiveTool, setCurrentTurnId } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useWebSocket(sessionId);
  const prevMessagesLenRef = useRef<number>(0); // Track previous message count for scroll decisions

  // Find the index of the LAST user message - this is the anchor for tool chain
  let lastUserIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user') {
      lastUserIdx = i;
      break;
    }
  }
  const lastUserMsg = lastUserIdx >= 0 ? messages[lastUserIdx] : null;

  // Filter tool calls for the current turn (matching the last user message's timestamp)
  const currentTurnToolCalls = React.useMemo(() =>
    lastUserMsg?.timestamp
      ? toolCalls.filter(tc => tc.turnId === lastUserMsg.timestamp)
      : [],
    [toolCalls, lastUserMsg?.timestamp]
  );

  // Show tool chain when:
  // 1. There are tool calls for this turn or active tool
  // AND we have found a user message to anchor to
  const hasToolActivity = currentTurnToolCalls.length > 0 || activeTool;
  const showToolChain = hasToolActivity && lastUserIdx >= 0;

  // Smart auto-scroll:
  // - New message arrived (not just tool call) → always scroll smoothly to show it
  // - Only new tool call (no new message) → only scroll if user is near bottom, no smooth animation
  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const newMessagesCount = messages.length - prevMessagesLenRef.current;
    prevMessagesLenRef.current = messages.length;

    if (newMessagesCount > 0) {
      // New messages arrived (user or assistant) → always scroll smoothly
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else if (toolCalls.length > 0 && distanceFromBottom < 100) {
      // Only new tool call and user is near bottom → gentle auto-scroll
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [messages, toolCalls]);

  const handleSend = (content: string) => {
    if (!isConnected) return;
    // Set currentTurnId to this message's timestamp - all subsequent tool calls will be associated with it
    const turnId = new Date().toISOString();
    setCurrentTurnId(turnId);
    setActiveTool(null);
    addMessage({
      role: 'user',
      content,
      timestamp: turnId,
    });
    setLoading(true);
    sendMessage(content);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#0a0a0a',
      }}
    >
      {/* Messages area */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          paddingTop: '24px',
          paddingBottom: '12px',
          contentVisibility: 'auto',
        }}
      >
        {messages.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#6e6e73',
            }}
          >
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="1" style={{ marginBottom: '16px' }}>
              <circle cx="12" cy="12" r="4" fill="#666" stroke="#666"/>
              <line x1="12" y1="2" x2="12" y2="5"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
              <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/>
              <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>
              <line x1="2" y1="12" x2="5" y2="12"/>
              <line x1="19" y1="12" x2="22" y2="12"/>
              <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/>
              <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>
            </svg>
            <p style={{ fontSize: '16px', marginBottom: '8px', color: '#8e8e93' }}>
              Start a conversation with sun-agent
            </p>
            <p style={{ fontSize: '13px' }}>
              Ask questions, get help with tasks, and more
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <React.Fragment key={msg.timestamp ? `${msg.timestamp}-${idx}` : `msg-${idx}`}>
                <MessageBubble message={msg} />
                {/* Show ToolChain AFTER the last user bubble (anchor for current turn) */}
                {msg.role === 'user' && idx === lastUserIdx && showToolChain && (
                  <ToolChain
                    toolCalls={currentTurnToolCalls}
                    isActive={isLoading && !!activeTool}
                    isDone={!isLoading && !currentTurnToolCalls.some(tc => tc.status === 'running')}
                    displayCount={currentTurnToolCalls.length}
                    activeToolName={activeTool || undefined}
                  />
                )}
              </React.Fragment>
            ))}
            {isLoading && !activeTool && messages.length > 0 && <TypingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <InputArea onSend={handleSend} disabled={isLoading || !isConnected} />
    </div>
  );
};