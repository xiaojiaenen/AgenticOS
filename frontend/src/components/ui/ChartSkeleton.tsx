import React from 'react';
import { cn } from '../../lib/utils';

interface ChartSkeletonProps {
  className?: string;
  variant?: 'area' | 'bar' | 'pie' | 'stat';
  height?: number;
}

/** Skeleton placeholder for dashboard charts while data loads. */
export const ChartSkeleton: React.FC<ChartSkeletonProps> = ({
  className,
  variant = 'area',
  height = 200,
}) => {
  if (variant === 'stat') {
    return (
      <div className={cn('animate-pulse space-y-3 p-4', className)}>
        <div className="h-3 w-24 rounded bg-slate-200" />
        <div className="h-7 w-16 rounded bg-slate-200" />
        <div className="h-2 w-32 rounded bg-slate-100" />
      </div>
    );
  }

  if (variant === 'pie') {
    return (
      <div className={cn('flex items-center justify-center animate-pulse', className)} style={{ height }}>
        <div className="h-32 w-32 rounded-full bg-slate-200" />
        <div className="ml-6 space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="h-3 w-3 rounded bg-slate-200" />
              <div className="h-3 rounded bg-slate-200" style={{ width: 60 + i * 12 }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (variant === 'bar') {
    return (
      <div className={cn('flex items-end gap-2 animate-pulse px-4', className)} style={{ height }}>
        {[40, 65, 50, 80, 55, 70, 45].map((h, i) => (
          <div key={i} className="flex-1 rounded-t bg-slate-200" style={{ height: `${h}%` }} />
        ))}
      </div>
    );
  }

  // area variant
  return (
    <div className={cn('animate-pulse', className)} style={{ height }}>
      <div className="flex items-end h-full gap-1 px-2">
        {[30, 45, 35, 60, 50, 70, 55, 65, 40, 50, 60, 45].map((h, i) => (
          <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-slate-200 to-slate-100" style={{ height: `${h}%` }} />
        ))}
      </div>
    </div>
  );
};
