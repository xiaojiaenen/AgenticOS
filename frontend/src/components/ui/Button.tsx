import React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

const variants = {
  primary:
    'bg-brand-500 text-white shadow-sm hover:bg-brand-600 active:bg-brand-700',
  secondary:
    'bg-white text-slate-700 border border-slate-200 shadow-xs hover:bg-slate-50 active:bg-slate-100',
  outline:
    'bg-white text-slate-600 border border-slate-200 hover:border-slate-300 hover:text-slate-800 active:bg-slate-50',
  ghost:
    'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-700',
  danger:
    'bg-error-50 text-error-600 border border-error-200 hover:bg-error-100',
};

const sizes = {
  sm: 'h-8 rounded-md px-3 text-xs font-medium',
  md: 'h-9 rounded-md px-4 text-sm font-medium',
  lg: 'h-10 rounded-lg px-5 text-sm font-semibold',
  icon: 'h-9 w-9 rounded-md',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading, disabled, children, type = 'button', ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        className={cn(
          'inline-flex items-center justify-center whitespace-nowrap transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40',
          variants[variant],
          sizes[size],
          className,
        )}
        {...props}
      >
        {isLoading && (
          <svg className="mr-2 h-3.5 w-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        {children}
      </button>
    );
  },
);

Button.displayName = 'Button';
