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
          <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1">
            {label}
          </label>
        )}
        <input
          type={type}
          className={cn(
            "w-full px-5 py-3.5 bg-slate-50 border border-slate-200 rounded-2xl text-slate-700 font-medium",
            "focus:outline-none focus:border-zinc-400 focus:ring-4 focus:ring-zinc-100/50 transition-all",
            className
          )}
          ref={ref}
          {...props}
        />
      </div>
    );
  }
);
Input.displayName = "Input";
