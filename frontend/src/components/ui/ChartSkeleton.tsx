import React from 'react';

interface ChartSkeletonProps {
  variant?: 'area' | 'bar' | 'line' | 'stat' | 'pie';
  height?: number;
  className?: string;
}

export const ChartSkeleton: React.FC<ChartSkeletonProps> = ({ height = 200, className = '' }) => {
  return (
    <div
      className={`animate-pulse rounded-2xl bg-slate-100 ${className}`}
      style={{ height }}
    />
  );
};
