import React from 'react';
import { cn } from '../../lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Card = ({ className, children, ...props }: CardProps) => {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-3xl border border-white/65 glass-medium shadow-lg ring-1 ring-white/35 p-6',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader = ({ className, children, ...props }: CardProps) => (
  <div className={cn('mb-3 flex items-center justify-between', className)} {...props}>
    {children}
  </div>
);

export const CardTitle = ({ className, children, as: Component = 'h3', ...props }: CardProps & { as?: 'h1' | 'h2' | 'h3' | 'h4' }) => (
  <Component className={cn('flex items-center gap-3 text-xl font-bold tracking-tight text-slate-900', className)} {...props}>
    {children}
  </Component>
);

export const CardContent = ({ className, children, ...props }: CardProps) => (
  <div className={cn('space-y-6', className)} {...props}>
    {children}
  </div>
);
