import React, { useState, useRef, useEffect } from 'react';

interface InputAreaProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: '12px',
        padding: '16px 24px',
        backgroundColor: '#0a0a0a',
        borderTop: '1px solid #1a1a1a',
      }}
    >
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Message sun-agent..."
        disabled={disabled}
        rows={1}
        style={{
          flex: 1,
          padding: '10px 16px',
          borderRadius: '12px',
          border: '1px solid #2a2a2a',
          backgroundColor: '#141414',
          color: '#e5e5e5',
          resize: 'none',
          outline: 'none',
          fontSize: '14px',
          fontFamily: 'inherit',
          maxHeight: '150px',
          transition: 'border-color 0.2s ease',
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = '#444';
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = '#2a2a2a';
        }}
      />
      <button
        type="submit"
        disabled={!input.trim() || disabled}
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          border: 'none',
          backgroundColor: input.trim() && !disabled ? '#fff' : '#2a2a2a',
          color: input.trim() && !disabled ? '#000' : '#666',
          fontSize: '18px',
          cursor: input.trim() && !disabled ? 'pointer' : 'not-allowed',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s ease',
          transform: input.trim() && !disabled ? 'scale(1)' : 'scale(0.95)',
        }}
        onMouseOver={(e) => {
          if (input.trim() && !disabled) {
            e.currentTarget.style.backgroundColor = '#e5e5e5';
          }
        }}
        onMouseOut={(e) => {
          if (input.trim() && !disabled) {
            e.currentTarget.style.backgroundColor = '#fff';
          }
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="19" x2="12" y2="5"></line>
          <polyline points="5 12 12 5 19 12"></polyline>
        </svg>
      </button>
    </form>
  );
};
