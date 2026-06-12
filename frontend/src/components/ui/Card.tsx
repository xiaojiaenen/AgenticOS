import React from 'react';
import { LiquidGlass, glassPresets, radii } from '@xiaojiaenen/liquid-glass';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Card = ({ className, children, ...props }: CardProps) => {
  const isGlass = useIsGlassTheme();

  if (isGlass) {
    return (
      <LiquidGlass
        {...glassPresets.card}
        tint="rgba(255,255,255,0.06)"
        radius={radii.card}
      >
        <div
          className={cn('p-6 transition-all duration-200', className)}
          {...props}
        >
          {children}
        </div>
      </LiquidGlass>
    );
  }

  return (
    <div
      className={cn(
        'rounded-lg border border-slate-200/80 bg-white p-6 shadow-sm transition-all duration-200 hover:border-slate-300 hover:shadow-md',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader = ({ className, children, ...props }: CardProps) => (
  <div className={cn('mb-3 flex items-center justify-between', className)} {...props}>
    {children}
  </div>
);

export const CardTitle = ({ className, children, as: Component = 'h3', ...props }: CardProps & { as?: 'h1' | 'h2' | 'h3' | 'h4' }) => {
  const isGlass = useIsGlassTheme();
  return (
    <Component className={cn('flex items-center gap-3 text-lg font-semibold', isGlass ? 'text-slate-900' : 'text-slate-900', className)} {...props}>
      {children}
    </Component>
  );
};

export const CardContent = ({ className, children, ...props }: CardProps) => (
  <div className={cn('space-y-4', className)} {...props}>
    {children}
  </div>
);
