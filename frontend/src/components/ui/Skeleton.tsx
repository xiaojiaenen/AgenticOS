import React from 'react';
import { cn } from '../../lib/utils';

interface SkeletonProps {
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className }) => (
  <div
    className={cn(
      'animate-pulse rounded-2xl bg-slate-200/60',
      className,
    )}
  />
);

export const SkeletonCard: React.FC<{ lines?: number }> = ({ lines = 3 }) => (
  <div className="rounded-[24px] border border-white/60 bg-white/50 p-5 space-y-4">
    <Skeleton className="h-5 w-1/3" />
    <Skeleton className="h-4 w-full" />
    {Array.from({ length: lines - 1 }).map((_, i) => (
      <Skeleton key={i} className="h-4 w-4/5" />
    ))}
  </div>
);

export const SkeletonList: React.FC<{ count?: number }> = ({ count = 3 }) => (
  <div className="space-y-3">
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
