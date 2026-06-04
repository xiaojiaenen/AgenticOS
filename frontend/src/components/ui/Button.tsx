import React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

const variants = {
  primary:
    'border border-slate-900/80 bg-[linear-gradient(180deg,#1f2937_0%,#020617_100%)] text-white shadow-button shadow-brand-500/10 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-brand-500/20 active:translate-y-0',
  secondary:
    'border border-white/80 bg-white/68 text-slate-700 shadow-sm ring-1 ring-white/40 hover:-translate-y-0.5 hover:bg-white/88 hover:text-slate-900 hover:shadow-md',
  outline:
    'border border-slate-200/90 bg-white/84 text-slate-700 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white',
  ghost:
    'border border-transparent bg-transparent text-slate-600 hover:bg-white/65 hover:text-slate-900',
  danger:
    'border border-rose-100/90 bg-rose-50/95 text-rose-600 shadow-sm shadow-rose-500/10 hover:-translate-y-0.5 hover:bg-rose-100',
};

const sizes = {
  sm: 'h-9 rounded-xl px-4 text-xs font-bold',
  md: 'h-11 rounded-2xl px-5 text-sm font-bold',
  lg: 'h-14 rounded-xl px-7 text-base font-bold',
  icon: 'h-11 w-11 rounded-2xl',
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
          'inline-flex items-center justify-center whitespace-nowrap tracking-[0.01em] transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100/80 disabled:pointer-events-none disabled:opacity-50',
          variants[variant],
          sizes[size],
          size === 'sm' ? 'font-bold' : 'font-black',
          className,
        )}
        {...props}
      >
        {isLoading && (
          <svg className="mr-2 h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
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
