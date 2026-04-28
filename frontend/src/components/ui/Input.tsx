import React from 'react';
import { cn } from '../../lib/utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, type, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="mb-2 ml-1 block text-xs font-black uppercase tracking-[0.2em] text-slate-400">
            {label}
          </label>
        )}
        <input
          type={type}
          className={cn(
            'w-full rounded-[22px] border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80',
            className,
          )}
          ref={ref}
          {...props}
        />
      </div>
    );
  },
);

Input.displayName = 'Input';
