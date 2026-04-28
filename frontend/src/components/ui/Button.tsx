import React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center whitespace-nowrap font-black tracking-[0.01em] transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-100/80 disabled:pointer-events-none disabled:opacity-45',
          {
            'border border-slate-900/80 bg-[linear-gradient(180deg,#1f2937_0%,#020617_100%)] text-white shadow-[0_18px_36px_rgba(15,23,42,0.26)] hover:-translate-y-0.5 hover:shadow-[0_24px_44px_rgba(15,23,42,0.28)] active:translate-y-0':
              variant === 'primary',
            'border border-white/80 bg-white/68 text-slate-700 shadow-[0_10px_26px_rgba(15,23,42,0.06)] ring-1 ring-white/40 hover:-translate-y-0.5 hover:bg-white/88 hover:text-slate-900':
              variant === 'secondary',
            'border border-slate-200/90 bg-white/84 text-slate-700 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white':
              variant === 'outline',
            'border border-transparent bg-transparent text-slate-600 hover:bg-white/65 hover:text-slate-900':
              variant === 'ghost',
            'border border-rose-100/90 bg-rose-50/95 text-rose-600 shadow-[0_10px_24px_rgba(244,63,94,0.12)] hover:-translate-y-0.5 hover:bg-rose-100':
              variant === 'danger',
            'h-9 rounded-2xl px-4 text-xs': size === 'sm',
            'h-11 rounded-[18px] px-5 text-sm': size === 'md',
            'h-14 rounded-[22px] px-7 text-base': size === 'lg',
            'h-11 w-11 rounded-[18px]': size === 'icon',
          },
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
