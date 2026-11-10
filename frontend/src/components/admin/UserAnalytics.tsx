import React from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { RefreshCw, Users } from 'lucide-react';
import { AdminPageHeader, AdminPanel, ErrorBanner, KpiPill } from './shared';
import { DataTable } from './data-table';
import { Button } from '../shadcn/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '../shadcn/dialog';
import { cn } from '../../lib/utils';
import { formatApiDateTime } from '../../lib/datetime';
import { getUserAnalytics, listUserAnalytics, type UserAnalyticsRow } from '../../services/feedbackService';

const MODE_LABEL: Record<string, string> = {
  general: '通用', ppt: 'PPT', website: '网站', email: '邮箱', bigdata: '大数据', office: '办公',
};

function DistributionBars({ data, label }: { data: { name: string; value: number }[]; label: (n: string) => string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) return <p className="text-xs text-[var(--muted-foreground)]">暂无数据</p>;
  return (
    <div className="flex flex-col gap-1.5">
      {data.map((d) => (
        <div key={d.name} className="flex items-center gap-2 text-xs">
          <span className="w-20 shrink-0 truncate text-[var(--muted-foreground)]">{label(d.name)}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
            <div className="h-full rounded-full bg-indigo-500" style={{ width: `${(d.value / max) * 100}%` }} />
          </div>
          <span className="w-8 shrink-0 text-right tabular-nums text-[var(--foreground)]">{d.value}</span>
        </div>
      ))}
    </div>
  );
}

function DetailDialog({ userId, days, onClose }: { userId: number | null; days: number; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['user-analytics', 'detail', userId, days],
    queryFn: () => getUserAnalytics(userId as number, days),
    enabled: userId !== null,
  });
  const d = q.data;
  return (
    <Dialog open={userId !== null} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex max-h-[88vh] max-w-3xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-[var(--border-subtle)] px-5 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            {d && <span className={cn('size-2 rounded-full', d.online ? 'bg-emerald-500' : 'bg-zinc-300')} />}
            {d ? d.name : '用户详情'}
          </DialogTitle>
          <DialogDescription className="text-xs">{d?.email} · 近 {days} 天</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {!d ? <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">加载中…</div> : (
            <div className="flex flex-col gap-5">
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: '运行次数', value: d.summary.runs },
                  { label: 'Token', value: d.summary.total_tokens.toLocaleString() },
                  { label: '工具调用', value: d.summary.tool_calls },
                  { label: 'LLM 调用', value: d.summary.llm_calls },
                ].map((k) => (
                  <div key={k.label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-center">
                    <div className="text-lg font-semibold tabular-nums text-[var(--foreground)]">{k.value}</div>
                    <div className="text-[11px] text-[var(--muted-foreground)]">{k.label}</div>
                  </div>
                ))}
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">每日趋势</p>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={d.daily} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
                      <defs>
                        <linearGradient id="uaRun" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} tickFormatter={(v: string) => v.slice(5)} />
                      <YAxis tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }} />
                      <Area type="monotone" dataKey="runs" name="运行" stroke="#6366f1" fill="url(#uaRun)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-5">
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">常用工具</p>
                  <DistributionBars data={d.tool_distribution} label={(n) => n} />
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">常用功能</p>
                  <DistributionBars data={d.mode_distribution} label={(n) => MODE_LABEL[n] ?? n} />
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function UserAnalytics() {
  const [days, setDays] = React.useState(14);
  const [detailId, setDetailId] = React.useState<number | null>(null);
  const q = useQuery({ queryKey: ['user-analytics', 'list', days], queryFn: () => listUserAnalytics(days) });

  const columns = React.useMemo<ColumnDef<UserAnalyticsRow>[]>(() => [
    { accessorKey: 'name', header: '用户', cell: (c) => (
      <button type="button" onClick={() => setDetailId(c.row.original.user_id)} className="flex items-center gap-2 text-left hover:text-indigo-600">
        <span className={cn('size-2 shrink-0 rounded-full', c.row.original.online ? 'bg-emerald-500' : 'bg-zinc-300 dark:bg-zinc-600')} title={c.row.original.online ? '在线' : '离线'} />
        <span className="min-w-0">
          <span className="block truncate font-medium text-[var(--foreground)]">{c.getValue() as string}</span>
          <span className="block truncate text-[11px] text-[var(--muted-foreground)]">{c.row.original.email}</span>
        </span>
      </button>
    ) },
    { accessorKey: 'last_active_at', header: '最近活跃', cell: (c) => <span className="text-xs text-[var(--muted-foreground)]">{c.getValue() ? formatApiDateTime(c.getValue() as string) : '—'}</span> },
    { accessorKey: 'runs', header: '运行', cell: (c) => <span className="tabular-nums">{c.getValue() as number}</span> },
    { accessorKey: 'total_tokens', header: 'Token', cell: (c) => <span className="tabular-nums">{(c.getValue() as number).toLocaleString()}</span> },
    { accessorKey: 'tool_calls', header: '工具', cell: (c) => <span className="tabular-nums">{c.getValue() as number}</span> },
    { id: 'top_tools', header: '常用工具', cell: (c) => (
      <div className="flex flex-wrap gap-1">
        {c.row.original.top_tools.slice(0, 3).map((t) => (
          <span key={t.name} className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--muted-foreground)]">{t.name}×{t.count}</span>
        ))}
      </div>
    ) },
    { id: 'top_modes', header: '常用功能', cell: (c) => (
      <div className="flex flex-wrap gap-1">
        {c.row.original.top_modes.slice(0, 3).map((m) => (
          <span key={m.name} className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] text-indigo-600 dark:text-indigo-300">{MODE_LABEL[m.name] ?? m.name}</span>
        ))}
      </div>
    ) },
  ], []);

  return (
    <div className="flex flex-col gap-4">
      <AdminPageHeader
        kicker="使用洞察"
        title="用户分析"
        description="每个用户的用量、在线状态、最近活跃与常用工具/功能，一屏掌握。"
        actions={
          <div className="flex items-center gap-2">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-[10px] border border-[var(--border)] bg-transparent px-3 text-sm outline-none">
              <option value={7}>近 7 天</option>
              <option value={14}>近 14 天</option>
              <option value={30}>近 30 天</option>
              <option value={90}>近 90 天</option>
            </select>
            <Button variant="outline" size="sm" className="gap-1" onClick={() => void q.refetch()}><RefreshCw size={14} /> 刷新</Button>
          </div>
        }
      />
      <div className="flex flex-wrap gap-2">
        <KpiPill label="用户总数" value={q.data?.items.length ?? 0} />
        <KpiPill label="当前在线" value={q.data?.online_count ?? 0} />
      </div>
      {q.isError && <ErrorBanner message="加载用户分析失败" onRetry={() => void q.refetch()} />}
      <AdminPanel>
        <DataTable
          columns={columns}
          data={q.data?.items ?? []}
          isLoading={q.isLoading}
          emptyState={<div className="flex flex-col items-center gap-2 py-12 text-center"><Users size={28} className="text-[var(--muted-foreground)]" /><p className="text-sm text-[var(--muted-foreground)]">暂无用户数据</p></div>}
        />
      </AdminPanel>
      <DetailDialog userId={detailId} days={days} onClose={() => setDetailId(null)} />
    </div>
  );
}
