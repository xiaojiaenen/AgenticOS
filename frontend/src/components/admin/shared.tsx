/**
 * 管理后台共享 UI 原语：页头、KPI 胶囊、状态胶囊、错误横幅、工具条。
 *
 * 2026-10 版式调整（依据后台实测反馈「卡片一个接一个，一直往下滚」）：
 * - 页头从「大卡片」降级为一条**不占背景**的标题栏：标题 + 说明 + 操作按钮
 *   同一行，滚动时先看到数据而不是先看到一整块装饰；
 * - 新增 `AdminToolbar`：筛选、搜索、批量操作、分页放在同一条水平带里，
 *   取代「筛选卡片 + 列表卡片 + 分页卡片」的三段式堆叠；
 * - 所有区块统一 1px 描边 + 极浅阴影，靠留白而不是阴影区分层级。
 */
import * as React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

export function AdminPageHeader({
  kicker,
  title,
  description,
  actions,
  className,
}: {
  kicker: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'flex flex-col gap-3 pb-1 lg:flex-row lg:items-end lg:justify-between lg:gap-6',
        className,
      )}
    >
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted-foreground)]">
          {kicker}
        </p>
        <h2 className="mt-0.5 text-lg font-semibold tracking-tight text-[var(--foreground)]">
          {title}
        </h2>
        {description ? (
          <p className="mt-1 max-w-3xl text-xs leading-5 font-medium text-[var(--muted-foreground)]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}

/**
 * 水平工具条：一条带子容纳筛选 / 搜索 / 批量操作 / 统计。
 *
 * 之所以单独抽出来：以前每页都是「筛选卡片 → 列表卡片 → 分页」三张卡纵向
 * 排列，一屏只放得下两个列表项。收进一条带子后，列表能多显示 40% 的行。
 */
export function AdminToolbar({
  children,
  className,
  align = 'start',
}: {
  children: React.ReactNode;
  className?: string;
  align?: 'start' | 'center';
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2',
        align === 'center' && 'items-center',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function KpiPill({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-medium text-[var(--muted-foreground)]">
      {label}
      {/* tabular-nums：数值刷新时宽度固定，不会左右跳动 */}
      <span className="font-semibold tabular-nums text-[var(--foreground)]">{value}</span>
    </span>
  );
}

export type StatusTone = 'active' | 'inactive' | 'warning' | 'info';

const STATUS_TONE_CLASS: Record<StatusTone, string> = {
  active: 'border-emerald-200/80 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300',
  inactive: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
  warning: 'border-amber-200/80 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300',
  info: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--foreground)]',
};

export function StatusPill({
  tone,
  children,
  className,
}: {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
        STATUS_TONE_CLASS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * 错误横幅。
 *
 * ``onRetry`` 是刻意加的：以前这个组件只渲染一句 message，页面上任何地方都
 * 找不到恢复路径 —— 用户只能自己刷新整个页面。而列表页的请求本来就能重试，
 * 一次网络抖动不该让人丢掉当前的操作上下文。
 */
export function ErrorBanner({
  message,
  onRetry,
  retryLabel = '重试',
  className,
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300',
        className,
      )}
    >
      <AlertCircle size={16} className="shrink-0" />
      <span className="min-w-0 break-words">{message}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)] dark:text-red-200 dark:hover:bg-red-500/20"
        >
          <RefreshCw size={13} className="shrink-0" />
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

/** 卡片容器：与 shadcn Card 视觉一致的普通 section */
export function AdminPanel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        'overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]',
        className,
      )}
    >
      {children}
    </section>
  );
}

/**
 * 区块小标题：卡片内部的「标题 + 右侧操作」行。
 * 用它替代「每块内容都套一张新卡片」——同一页面内不再嵌套卡片。
 */
export function SectionHeading({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-4 py-2.5',
        className,
      )}
    >
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
          {title}
        </p>
        {description ? (
          <p className="mt-0.5 text-xs font-medium text-[var(--muted-foreground)]">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
    </div>
  );
}
