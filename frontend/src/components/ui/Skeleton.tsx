import React from 'react';
import { cn } from '../../lib/utils';

interface SkeletonProps {
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className }) => (
  <div
    role="status"
    aria-label="Loading"
    className={cn(
      'animate-pulse rounded-2xl bg-gradient-to-r from-sky-100/60 via-sky-200/40 to-sky-100/60',
      className,
    )}
  />
);

export const SkeletonCard: React.FC<{ lines?: number; className?: string }> = ({ lines = 3, className }) => (
  <div className={cn('rounded-2xl border border-white/60 bg-white/50 p-5 space-y-4', className)}>
    <Skeleton className="h-5 w-1/3" />
    <Skeleton className="h-4 w-full" />
    {Array.from({ length: lines - 1 }).map((_, i) => (
      <Skeleton key={i} className="h-4 w-4/5" />
    ))}
  </div>
);

export const SkeletonList: React.FC<{ count?: number; className?: string }> = ({ count = 3, className }) => (
  <div className={cn('space-y-3', className)}>
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="flex items-center gap-4 rounded-2xl border border-white/50 bg-white/45 p-4">
        <Skeleton className="h-10 w-10 rounded-xl" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </div>
    ))}
  </div>
);
