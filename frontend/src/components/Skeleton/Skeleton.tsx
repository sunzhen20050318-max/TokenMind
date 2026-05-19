import React from 'react';

import './skeleton.css';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  radius?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height = 14,
  radius = 6,
  className,
  style,
}) => (
  <div
    className={`tm-skeleton ${className ?? ''}`}
    style={{
      width: width ?? '100%',
      height,
      borderRadius: radius,
      ...style,
    }}
    aria-hidden="true"
  />
);

interface CardGridSkeletonProps {
  count?: number;
  className?: string;
}

/** Three-column-ish card grid placeholder for knowledge bases, projects, etc. */
export const CardGridSkeleton: React.FC<CardGridSkeletonProps> = ({
  count = 6,
  className,
}) => (
  <div className={`tm-skeleton-grid ${className ?? ''}`} aria-busy="true" aria-live="polite">
    {Array.from({ length: count }).map((_, i) => (
      <div className="tm-skeleton-card" key={i}>
        <Skeleton width="60%" height={16} />
        <Skeleton width="40%" height={11} style={{ marginTop: 10 }} />
        <Skeleton width="90%" height={11} style={{ marginTop: 14 }} />
        <Skeleton width="75%" height={11} style={{ marginTop: 6 }} />
      </div>
    ))}
  </div>
);

interface ListSkeletonProps {
  count?: number;
  className?: string;
  withAvatar?: boolean;
}

/** Vertical list placeholder for sessions, documents, memory entries. */
export const ListSkeleton: React.FC<ListSkeletonProps> = ({
  count = 5,
  className,
  withAvatar = false,
}) => (
  <div className={`tm-skeleton-list ${className ?? ''}`} aria-busy="true" aria-live="polite">
    {Array.from({ length: count }).map((_, i) => (
      <div className="tm-skeleton-list-item" key={i}>
        {withAvatar ? <Skeleton width={32} height={32} radius="50%" /> : null}
        <div className="tm-skeleton-list-item__body">
          <Skeleton width="55%" height={13} />
          <Skeleton width="35%" height={10} style={{ marginTop: 8 }} />
        </div>
      </div>
    ))}
  </div>
);
