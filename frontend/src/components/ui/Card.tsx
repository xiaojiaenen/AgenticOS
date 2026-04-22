import React from 'react';
import { cn } from '../../lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Card = ({ className, children, ...props }: CardProps) => {
  return (
    <div className={cn("bg-white/60 backdrop-blur-2xl rounded-2xl shadow-[0_4px_20px_rgba(0,0,0,0.03)] border border-white/60", className)} {...props}>
      {children}
    </div>
  );
};

export const CardHeader = ({ className, children, ...props }: CardProps) => (
  <div className={cn("flex items-center justify-between mb-8", className)} {...props}>
    {children}
  </div>
);

export const CardTitle = ({ className, children, ...props }: CardProps) => (
  <h3 className={cn("text-xl font-bold text-slate-800 flex items-center gap-3", className)} {...props}>
    {children}
  </h3>
);

export const CardContent = ({ className, children, ...props }: CardProps) => (
  <div className={cn("space-y-6", className)} {...props}>
    {children}
  </div>
);
