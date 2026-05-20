import React from 'react';
import { cn } from '../../lib/utils';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center py-16 text-center',
        className,
      )}
    >
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/70 bg-white/70 text-sky-400 shadow-sm transition-all duration-300 hover:scale-110 hover:bg-sky-50/60 hover:text-sky-500 hover:shadow-md">
          {icon}
        </div>
      )}
      <p className="text-sm font-bold text-slate-600">{title}</p>
      {description && (
        <p className="mt-1 text-xs font-medium text-slate-500">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
};
