import { cn } from '../../lib/utils';
import { Skeleton } from '../shadcn/skeleton';

/**
 * 通用骨架屏。
 *
 * 统一「加载语言」：列表/表格一律用骨架屏占位，而不是整块 spinner。
 * 原因很实际 —— spinner 只能表达「有东西在加载」，骨架屏能表达「加载完会
 * 长什么样」，页面不会在数据到达时突然「塌陷 → 撑开」，视觉上稳得多。
 *
 * 骨架块全部用 `bg-accent`（跟随主题），不用硬编码的 slate 色，否则暗色
 * 主题下会是一片亮白。
 */

export function PanelSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('space-y-3', className)}>
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-3 w-64" />
      <div className="grid gap-3 pt-2 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export function ListSkeleton({
  rows = 5,
  columns = 4,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={cn('space-y-2', className)} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          className={cn(
            'flex items-center gap-4 rounded-lg border border-[var(--border-subtle)] px-4 py-3',
            // 斑马纹：让行边界在骨架阶段就能看出来（真实表格也有同样规则）
            rowIndex % 2 === 1 ? 'bg-[var(--surface-2)]' : 'bg-[var(--surface-1)]',
          )}
        >
          {Array.from({ length: columns }).map((__, colIndex) => (
            <Skeleton
              key={colIndex}
              className={cn('h-3', colIndex === 0 ? 'w-1/4' : 'flex-1')}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div className={cn('grid gap-3 sm:grid-cols-2 lg:grid-cols-3', className)} aria-busy="true">
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="flex flex-col gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4"
        >
          <div className="flex items-center gap-3">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3 w-3/4" />
              <Skeleton className="h-2.5 w-1/2" />
            </div>
          </div>
          <Skeleton className="h-2.5 w-full" />
          <Skeleton className="h-2.5 w-4/5" />
          <div className="flex gap-2 pt-1">
            <Skeleton className="h-6 w-16 rounded-full" />
            <Skeleton className="h-6 w-12 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** 表单区骨架：用于「整个编辑页加载中」。 */
export function FormSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('space-y-5', className)} aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3 w-72" />
      </div>
      <Skeleton className="h-40 rounded-xl" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-9 rounded-lg" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-9 rounded-lg" />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Skeleton className="h-9 w-20 rounded-lg" />
        <Skeleton className="h-9 w-24 rounded-lg" />
      </div>
    </div>
  );
}

/**
 * 局部加载指示器（替代裸 spinner）。
 * 尺寸与颜色都走 token，暗色下不会出现「白底上转圈看不见」。
 */
export function InlineSpinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      className={cn('inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)]', className)}
      role="status"
    >
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-[var(--border-strong)] border-t-[var(--foreground)]"
      />
      {label ? <span>{label}</span> : <span className="sr-only">加载中</span>}
    </span>
  );
}
