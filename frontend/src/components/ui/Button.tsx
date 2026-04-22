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
          "inline-flex items-center justify-center font-bold transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
          {
            'bg-zinc-900 text-white hover:bg-zinc-800 shadow-sm shadow-zinc-900/20 hover:shadow-md hover:-translate-y-0.5 transition-all': variant === 'primary',
            'bg-slate-100 text-slate-800 hover:bg-slate-200': variant === 'secondary',
            'border-2 border-slate-200 bg-white hover:border-slate-300 text-slate-700': variant === 'outline',
            'hover:bg-slate-100 text-slate-700': variant === 'ghost',
            'bg-rose-50 text-rose-600 hover:bg-rose-100': variant === 'danger',
            'h-9 px-4 text-xs rounded-xl': size === 'sm',
            'h-11 px-6 text-sm rounded-xl': size === 'md',
            'h-14 px-8 text-base rounded-2xl': size === 'lg',
            'h-11 w-11 rounded-xl': size === 'icon',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';
