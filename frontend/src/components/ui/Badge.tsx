import React from 'react';
import { cn } from '../../lib/utils';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md';
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-sky-50 text-sky-700 border-sky-100',
  success: 'bg-success-50 text-success-700 border-success-100',
  warning: 'bg-warning-50 text-warning-700 border-warning-100',
  danger: 'bg-rose-50 text-rose-600 border-rose-100',
  info: 'bg-info-50 text-info-700 border-info-100',
  neutral: 'bg-white/88 text-slate-500 border-white/80',
};

const sizeStyles = {
  sm: 'px-2 py-0.5 text-[11px]',
  md: 'px-2.5 py-1 text-xs',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  className,
  size = 'sm',
}) => {
  return (
    <span
      role="status"
      className={cn(
        'inline-flex items-center gap-1 rounded-full border font-bold',
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
    >
      {children}
    </span>
  );
};
