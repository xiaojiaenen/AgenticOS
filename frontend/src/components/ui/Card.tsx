import React from 'react';
import { cn } from '../../lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Card = ({ className, children, ...props }: CardProps) => {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[30px] border border-white/65 bg-white/[0.62] shadow-[0_28px_80px_rgba(15,23,42,0.08)] ring-1 ring-white/35 backdrop-blur-[28px]',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader = ({ className, children, ...props }: CardProps) => (
  <div className={cn('mb-6 flex items-center justify-between', className)} {...props}>
    {children}
  </div>
);

export const CardTitle = ({ className, children, ...props }: CardProps) => (
  <h3 className={cn('flex items-center gap-3 text-xl font-black tracking-tight text-slate-900', className)} {...props}>
    {children}
  </h3>
);

export const CardContent = ({ className, children, ...props }: CardProps) => (
  <div className={cn('space-y-6', className)} {...props}>
    {children}
  </div>
);
