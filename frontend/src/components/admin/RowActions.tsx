/**
 * 表格行操作：统一的一排轻量图标动作。
 *
 * 为什么单独抽出来：以前每个管理页的自绘行操作都是「描边按钮 + ghost 图标」
 * 混搭，视觉重量不一、列宽被撑开。这里固定成 hover 才显形的图标动作条，
 * 危险动作单独染色，保持表格右侧留白干净。
 */
import React from 'react';
import { cn } from '../../lib/utils';

export interface RowAction {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  /** danger 用红色，只留给不可逆动作 */
  tone?: 'default' | 'danger';
  disabled?: boolean;
}

export function RowActions({
  actions,
  className,
}: {
  actions: RowAction[];
  className?: string;
}) {
  return (
    <div className={cn('flex items-center justify-end gap-1', className)}>
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          title={action.label}
          aria-label={action.label}
          disabled={action.disabled}
          onClick={(event) => {
            event.stopPropagation();
            action.onClick();
          }}
          className={cn(
            'inline-flex size-8 items-center justify-center rounded-lg transition-colors',
            'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
            'hover:bg-[var(--surface-3)]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
            'disabled:pointer-events-none disabled:opacity-40',
            action.tone === 'danger' &&
              'hover:bg-rose-500/10 hover:text-rose-500',
          )}
        >
          {action.icon}
        </button>
      ))}
    </div>
  );
}
