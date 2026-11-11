/**
 * 运行日志面板：把本轮对话的工具调用与状态聚合成可扫读的时间线。
 *
 * 数据来源就是 `session.messages`（每个 toolCall 已有 name/status/result），
 * 不新增后端接口 —— 这些信息本来就在前端内存里，只是此前散落在气泡内，
 * 长会话里想「这一轮到底跑了什么、哪步失败」只能一条条翻。
 *
 * 定位：调试/复盘用的工具面板，与「对话」主视图并列，不是替代它。
 */
import * as React from 'react';
import { AlertTriangle, CheckCircle2, Clock, Loader2, Wrench, XCircle } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { ToolCall } from '../../types';
import type { SessionPanelProps } from './types';

type LogRow = {
  id: string;
  name: string;
  status: ToolCall['status'];
  /** 结果首行摘要 */
  summary?: string;
  /** 参数摘要 */
  args?: string;
};

const STATUS_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ size?: number; className?: string }>; tone: string }
> = {
  success: { label: '完成', icon: CheckCircle2, tone: 'text-emerald-600 dark:text-emerald-400' },
  error: { label: '失败', icon: XCircle, tone: 'text-rose-600 dark:text-rose-400' },
  pending: { label: '执行中', icon: Loader2, tone: 'text-sky-600 dark:text-sky-400' },
  approval_required: { label: '待审批', icon: AlertTriangle, tone: 'text-amber-600 dark:text-amber-400' },
  approved: { label: '已批准', icon: CheckCircle2, tone: 'text-sky-600 dark:text-sky-400' },
  rejected: { label: '已拒绝', icon: XCircle, tone: 'text-rose-600 dark:text-rose-400' },
};

function shortArgs(args: unknown): string | undefined {
  if (!args || typeof args !== 'object') return undefined;
  const entries = Object.entries(args as Record<string, unknown>);
  if (entries.length === 0) return undefined;
  return entries
    .slice(0, 3)
    .map(([k, v]) => {
      const text = typeof v === 'string' ? v : JSON.stringify(v);
      return `${k}=${text.length > 28 ? `${text.slice(0, 28)}…` : text}`;
    })
    .join(' ');
}

function firstLine(result?: string): string | undefined {
  if (!result) return undefined;
  const line = result.split('\n').find((l) => l.trim());
  if (!line) return undefined;
  return line.length > 80 ? `${line.slice(0, 80)}…` : line;
}

export const RunLogPanel: React.FC<SessionPanelProps> = ({ messages }) => {
  const rows = React.useMemo<LogRow[]>(() => {
    const out: LogRow[] = [];
    for (const message of messages) {
      for (const tool of message.toolCalls ?? []) {
        out.push({
          id: `${message.id}-${tool.id ?? tool.name}`,
          name: tool.name,
          status: tool.status,
          summary: firstLine(tool.result),
          args: shortArgs(tool.arguments),
        });
      }
    }
    return out;
  }, [messages]);

  const stats = React.useMemo(() => {
    const failed = rows.filter((r) => r.status === 'error' || r.status === 'rejected').length;
    const pending = rows.filter(
      (r) => r.status === 'pending' || r.status === 'approval_required',
    ).length;
    return { total: rows.length, failed, pending };
  }, [rows]);

  if (rows.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <Clock size={20} className="text-[var(--muted-foreground)]" />
        <p className="text-sm font-medium text-[var(--muted-foreground)]">
          本轮还没有工具调用
        </p>
        <p className="text-xs text-[var(--muted-foreground)]">
          智能体调用工具后，这里会按时间顺序列出每一步
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs">
        <span className="font-semibold text-[var(--foreground)]">共 {stats.total} 步</span>
        {stats.failed > 0 ? (
          <span className="text-rose-600 dark:text-rose-400">失败 {stats.failed}</span>
        ) : null}
        {stats.pending > 0 ? (
          <span className="text-amber-600 dark:text-amber-400">进行中 {stats.pending}</span>
        ) : null}
      </div>

      <ol className="relative flex flex-col gap-2 pl-4">
        <span className="absolute bottom-2 left-[5px] top-2 w-px bg-[var(--border-subtle)]" aria-hidden />
        {rows.map((row, index) => {
          const meta = STATUS_META[row.status] ?? STATUS_META.pending;
          const Icon = meta.icon;
          const spinning = row.status === 'pending';
          return (
            <li key={row.id} className="relative">
              <span
                className={cn(
                  'absolute -left-4 top-2 h-2 w-2 rounded-full ring-2 ring-[var(--surface-1)]',
                  row.status === 'error' || row.status === 'rejected'
                    ? 'bg-rose-500'
                    : row.status === 'success'
                      ? 'bg-emerald-500'
                      : 'bg-sky-500',
                )}
                aria-hidden
              />
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold tabular-nums text-[var(--muted-foreground)]">
                    {index + 1}
                  </span>
                  <Wrench size={12} className="shrink-0 text-[var(--muted-foreground)]" />
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--foreground)]">
                    {row.name}
                  </span>
                  <span className={cn('flex shrink-0 items-center gap-1 text-[10px] font-semibold', meta.tone)}>
                    <Icon size={11} className={spinning ? 'animate-spin' : undefined} />
                    {meta.label}
                  </span>
                </div>
                {row.args ? (
                  <p className="mt-1 truncate font-mono text-[10px] text-[var(--muted-foreground)]">
                    {row.args}
                  </p>
                ) : null}
                {row.summary ? (
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    {row.summary}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
