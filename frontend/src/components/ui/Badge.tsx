import React from 'react';
import { cn } from '../../lib/utils';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md';
}

/**
 * 配色全部带 dark: 变体。
 *
 * 之前 neutral 变体硬编码 `bg-white/88 text-slate-500`，暗色主题下是
 * 「白底浅灰字」—— 在深色后台里像一块脏斑。现在一律改成「语义色 + 暗色反相」
 * 的成对写法，保证任何主题下都有足够对比度。
 */
const variantStyles: Record<BadgeVariant, string> = {
  default:
    'bg-sky-50 text-sky-700 border-sky-200/80 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-400/30',
  success:
    'bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400/30',
  warning:
    'bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/30',
  danger:
    'bg-rose-50 text-rose-700 border-rose-200/80 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-400/30',
  info:
    'bg-indigo-50 text-indigo-700 border-indigo-200/80 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-400/30',
  neutral:
    'bg-[var(--surface-2)] text-[var(--muted-foreground)] border-[var(--border-subtle)]',
};

const sizeStyles = {
  sm: 'px-2 py-0.5 text-[11px]',
  md: 'px-2.5 py-1 text-xs',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  className,
  size = 'sm',
}) => {
  return (
    <span
      // 不加 role="status"：列表里每个 Badge 都是 live region 的话，读屏
      // 会把整页标签连续播报一遍。这里是纯展示型徽标，语义由 surrounding 提供。
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-semibold',
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
    >
      {children}
    </span>
  );
};
