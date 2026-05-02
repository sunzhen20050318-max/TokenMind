import React from 'react';

interface BrandMarkProps {
  size?: number;
  alt?: string;
  className?: string;
  style?: React.CSSProperties;
  variant?: 'icon' | 'wordmark' | 'sidebar-wordmark';
  tone?: 'light' | 'dark';
}

export const BrandMark: React.FC<BrandMarkProps> = ({
  size = 20,
  alt = 'TokenMind',
  className,
  style,
  variant = 'icon',
  tone = 'light',
}) => (
  <img
    src={
      variant === 'sidebar-wordmark'
        ? tone === 'dark'
          ? '/tokenmind-sidebar-wordmark-black.svg'
          : '/tokenmind-sidebar-wordmark.svg'
        : variant === 'wordmark'
        ? tone === 'dark'
          ? '/tokenmind-wordmark-black.svg'
          : '/tokenmind-wordmark.svg'
        : tone === 'dark'
          ? '/tokenmind-mark-black.svg'
          : '/tokenmind-mark.svg'
    }
    alt={alt}
    className={className}
    draggable={false}
    style={{
      width: 'auto',
      height: size,
      display: 'block',
      objectFit: 'contain',
      userSelect: 'none',
      ...style,
    }}
  />
);
