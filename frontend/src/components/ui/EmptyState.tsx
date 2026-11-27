import React from 'react';
import { Package } from 'kubai-icons-react';
import { cn } from '../../lib/utils';

export interface EmptyStateAction {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
}

interface EmptyStateProps {
  /** 状态图标。传 null 则用默认的「空盒子」图形。 */
  icon?: React.ReactNode;
  title: string;
  description?: string;
  /** 主行动（最多一个）。空状态没有出口是最常见的体验缺陷 —— 永远给出下一步。 */
  action?: EmptyStateAction;
  /** 次要行动 */
  secondaryAction?: EmptyStateAction;
  /** compact 用于表格内嵌空态，default 用于整块区域 */
  size?: 'compact' | 'default';
  className?: string;
}

/**
 * 统一空状态。
 *
 * 项目里原先有 20 多处手写空状态，句式四种混用（「暂无数据」「还没有 X」
 * 「没有找到匹配」「暂时还没有」），而且多数只有一句话、**没有下一步入口** ——
 * 用户看到「暂无集成」却找不到「新建集成」的按钮，只能去猜。
 *
 * 这个组件把三件事固定下来：
 * 1. 统一句式与排版层次；
 * 2. 图标 + 描述 + 行动的三段式结构，空态不再像报错；
 * 3. 行动按钮强制内联在空态里，不需要用户自己找页面上的按钮。
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  secondaryAction,
  size = 'default',
  className,
}) => {
  const compact = size === 'compact';

  const renderButton = (item: EmptyStateAction, primary: boolean) => (
    <button
      type="button"
      onClick={item.onClick}
      disabled={item.disabled}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
        'disabled:cursor-not-allowed disabled:opacity-50',
        compact ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm',
        primary
          ? 'bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm hover:opacity-90 active:scale-[0.98]'
          : 'border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] hover:bg-[var(--surface-2)] active:scale-[0.98]',
      )}
    >
      {item.label}
    </button>
  );

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'gap-2 px-4 py-8' : 'gap-3 px-6 py-14',
        className,
      )}
    >
      <div className="relative flex items-center justify-center" aria-hidden>
        {!compact && (
          <svg
            className="aos-halo-pulse pointer-events-none absolute -inset-4 h-20 w-20 text-[var(--primary)]/20"
            viewBox="0 0 80 80"
            fill="none"
          >
            <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="1" strokeDasharray="3 5" />
            <circle cx="40" cy="40" r="27" stroke="currentColor" strokeWidth="1" opacity="0.6" />
          </svg>
        )}
        <div
          className={cn(
            'aos-glass-surface relative z-10 flex items-center justify-center rounded-2xl text-[var(--primary)]',
            compact ? 'size-9' : 'size-12',
          )}
        >
          {icon ?? <Package size={compact ? 20 : 28} className="text-[var(--primary)]" trigger="parent" />}
        </div>
      </div>

      <p
        className={cn(
          'font-semibold tracking-tight text-[var(--foreground)]',
          compact ? 'text-sm' : 'text-[15px]',
        )}
      >
        {title}
      </p>

      {description ? (
        <p
          className={cn(
            'max-w-md leading-relaxed text-[var(--muted-foreground)]',
            compact ? 'text-xs' : 'text-sm',
          )}
        >
          {description}
        </p>
      ) : null}

      {action || secondaryAction ? (
        <div className={cn('flex flex-wrap items-center justify-center gap-2', compact ? 'mt-1' : 'mt-2')}>
          {action ? renderButton(action, true) : null}
          {secondaryAction ? renderButton(secondaryAction, false) : null}
        </div>
      ) : null}
    </div>
  );
};
