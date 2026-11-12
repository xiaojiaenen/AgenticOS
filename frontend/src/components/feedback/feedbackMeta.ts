import type { IssueStatus, IssueType, IssuePriority } from '../../services/feedbackService';

export const STATUS_META: Record<
  IssueStatus,
  { label: string; className: string; dot: string; /** 列表行左侧色条 */ rail: string }
> = {
  open: { label: '待处理', className: 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/40 dark:bg-slate-500/15 dark:text-slate-300', dot: 'bg-slate-400', rail: 'bg-slate-300 dark:bg-slate-500' },
  confirmed: { label: '已确认', className: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-500/40 dark:bg-sky-500/15 dark:text-sky-300', dot: 'bg-sky-500', rail: 'bg-sky-400' },
  in_progress: { label: '处理中', className: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500', rail: 'bg-amber-400' },
  resolved: { label: '已解决', className: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500', rail: 'bg-emerald-400' },
  shipped: { label: '已上线', className: 'border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/15 dark:text-zinc-300', dot: 'bg-zinc-500', rail: 'bg-zinc-400' },
  closed: { label: '已关闭', className: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]', dot: 'bg-zinc-400', rail: 'bg-[var(--border-strong)]' },
};

export const TYPE_META: Record<IssueType, { label: string; emoji: string }> = {
  bug: { label: '缺陷', emoji: '🐞' },
  feature: { label: '建议', emoji: '✨' },
  question: { label: '疑问', emoji: '❓' },
  other: { label: '其他', emoji: '💬' },
};

export const PRIORITY_META: Record<IssuePriority, { label: string; className: string }> = {
  low: { label: '低', className: 'text-[var(--muted-foreground)]' },
  medium: { label: '中', className: 'text-amber-600 dark:text-amber-400' },
  high: { label: '高', className: 'text-rose-600 dark:text-rose-400' },
};

export const STATUS_ORDER: IssueStatus[] = ['open', 'confirmed', 'in_progress', 'resolved', 'shipped', 'closed'];