import React from 'react';

interface BrandMarkProps {
  size?: number;
  alt?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const BrandMark: React.FC<BrandMarkProps> = ({
  size = 20,
  alt = 'SUN-AGENT',
  className,
  style,
}) => (
  <img
    src="/sun-agent-mark.svg"
    alt={alt}
    className={className}
    draggable={false}
    style={{
      width: size,
      height: size,
      display: 'block',
      objectFit: 'contain',
      userSelect: 'none',
      ...style,
    }}
  />
);
