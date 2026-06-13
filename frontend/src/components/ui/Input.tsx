import React, { useId } from 'react';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, type, ...props }, ref) => {
    const id = useId();
    const isGlass = useIsGlassTheme();

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={id} className={cn("mb-1.5 ml-0.5 block text-xs font-medium", isGlass ? "text-white/60" : "text-slate-500")}>
            {label}
          </label>
        )}
        <input
          id={id}
          type={type}
          aria-invalid={error ? true : undefined}
          aria-describedby={error && typeof error === 'string' ? `${id}-error` : undefined}
          className={cn(
            'w-full rounded-md border px-3.5 py-2.5 text-sm outline-none transition-all duration-200 placeholder:text-slate-400 focus:border-brand-400 focus:shadow-input-glow disabled:opacity-40 disabled:cursor-not-allowed',
            isGlass
              ? 'bg-white/10 border-white/20 text-white placeholder:text-white/40 focus:border-sky-400 focus:ring-sky-400/30 focus:ring-4 disabled:bg-white/5'
              : 'border-slate-200 bg-white text-slate-800 focus:border-brand-400 focus:shadow-input-glow disabled:bg-slate-50',
            error && 'border-error-400 focus:border-error-400 focus:shadow-[0_0_0_3px_rgba(217,68,68,0.12)]',
            className,
          )}
          ref={ref}
          {...props}
        />
        {typeof error === 'string' && (
          <p id={`${id}-error`} className={cn("mt-1 ml-0.5 text-xs", isGlass ? "text-red-400" : "text-error-500")} role="alert">{error}</p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
