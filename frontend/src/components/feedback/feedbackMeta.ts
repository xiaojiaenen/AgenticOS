import type { IssueStatus, IssueType, IssuePriority } from '../../services/feedbackService';

export const STATUS_META: Record<IssueStatus, { label: string; className: string; dot: string }> = {
  open: { label: '待处理', className: 'bg-slate-100 text-slate-600 dark:bg-slate-500/15 dark:text-slate-300', dot: 'bg-slate-400' },
  confirmed: { label: '已确认', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', dot: 'bg-sky-500' },
  in_progress: { label: '处理中', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500' },
  resolved: { label: '已解决', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500' },
  shipped: { label: '已上线', className: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300', dot: 'bg-indigo-500' },
  closed: { label: '已关闭', className: 'bg-[var(--surface-2)] text-[var(--muted-foreground)]', dot: 'bg-zinc-400' },
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