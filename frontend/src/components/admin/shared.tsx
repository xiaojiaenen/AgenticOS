/**
 * 管理后台共享 UI 原语：页头、KPI 胶囊、状态胶囊、错误横幅。
 * 统一使用新设计 token（zinc 灰阶 + indigo 主色）。
 */
import * as React from 'react';
import { AlertCircle } from 'lucide-react';
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
    <section
      className={cn(
        'flex flex-col gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm lg:flex-row lg:items-center lg:justify-between',
        className,
      )}
    >
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-700">
          {kicker}
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--foreground)]">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm font-medium text-[var(--muted-foreground)]">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </section>
  );
}

export function KpiPill({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-medium text-[var(--muted-foreground)] shadow-sm">
      {label}
      <span className="font-semibold text-[var(--foreground)]">{value}</span>
    </span>
  );
}

export type StatusTone = 'active' | 'inactive' | 'warning' | 'info';

const STATUS_TONE_CLASS: Record<StatusTone, string> = {
  active: 'border-emerald-200/80 bg-emerald-50 text-emerald-700',
  inactive: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
  warning: 'border-amber-200/80 bg-amber-50 text-amber-700',
  info: 'border-zinc-200 bg-zinc-100 text-zinc-800',
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

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm font-medium text-rose-700">
      <AlertCircle size={16} className="shrink-0" />
      <span className="min-w-0 break-words">{message}</span>
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
        'overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm',
        className,
      )}
    >
      {children}
    </section>
  );
}
