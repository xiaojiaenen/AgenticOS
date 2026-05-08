import React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
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
  sm: 'h-9 rounded-xl px-4 text-xs',
  md: 'h-11 rounded-[16px] px-5 text-sm',
  lg: 'h-14 rounded-xl px-7 text-base',
  icon: 'h-11 w-11 rounded-[16px]',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center whitespace-nowrap font-black tracking-[0.01em] transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100/80 disabled:pointer-events-none disabled:opacity-45',
          variants[variant],
          sizes[size],
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
