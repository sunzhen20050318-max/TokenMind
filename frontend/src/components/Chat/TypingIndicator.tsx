import React from 'react';
import { BrandMark } from '../BrandMark';

export const TypingIndicator: React.FC = () => {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        width: '100%',
        padding: '0',
        boxSizing: 'border-box',
        marginBottom: '12px',
        animation: 'typingFadeIn 0.2s ease-out',
      }}
    >
      <div
        style={{
          width: '32px',
          height: '32px',
          flex: '0 0 32px',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'transparent',
          border: 'none',
        }}
      >
        <BrandMark size={24} alt="" variant="icon" style={{ opacity: 0.96 }} />
      </div>

      <div
        style={{
          padding: '6px 0',
          display: 'flex',
          gap: '6px',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: '#857d72',
            animation: 'typingBounce 1.4s infinite ease-in-out',
          }}
        />
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: '#857d72',
            animation: 'typingBounce 1.4s infinite ease-in-out 0.16s',
          }}
        />
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: '#857d72',
            animation: 'typingBounce 1.4s infinite ease-in-out 0.32s',
          }}
        />
      </div>

      <style>{`
        @keyframes typingBounce {
          0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
          40% { transform: scale(1); opacity: 1; }
        }
        @keyframes typingFadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};
