import React, { useId } from 'react';
import { cn } from '../../lib/utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, type, ...props }, ref) => {
    const id = useId();

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={id} className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
            {label}
          </label>
        )}
        <input
          id={id}
          type={type}
          aria-invalid={error ? true : undefined}
          aria-describedby={error && typeof error === 'string' ? `${id}-error` : undefined}
          className={cn(
            'w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-brand-200 focus:bg-white focus:ring-4 focus:ring-brand-100/80 disabled:opacity-50 disabled:bg-slate-50 disabled:cursor-not-allowed',
            error && 'border-rose-300 ring-4 ring-rose-100/60 focus:border-rose-300 focus:ring-rose-100/60',
            className,
          )}
          ref={ref}
          {...props}
        />
        {typeof error === 'string' && (
          <p id={`${id}-error`} className="mt-1.5 ml-1 text-xs font-semibold text-rose-500" role="alert">{error}</p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
