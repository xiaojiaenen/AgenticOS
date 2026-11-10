import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { MessageSquare, RefreshCw, Trash2 } from 'lucide-react';
import { AdminPageHeader, AdminPanel, ErrorBanner, KpiPill } from './shared';
import { DataTable } from './data-table';
import { Button } from '../shadcn/button';
import { Input } from '../shadcn/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '../shadcn/dialog';
import { cn } from '../../lib/utils';
import { formatApiDateTime } from '../../lib/datetime';
import { toastError } from '../../lib/errors';
import {
  adminDeleteFeedback, adminReplyFeedback, adminUpdateFeedback, getFeedback,
  getFeedbackStats, listFeedback,
  type FeedbackIssue, type IssuePriority, type IssueStatus,
} from '../../services/feedbackService';
import { PRIORITY_META, STATUS_META, STATUS_ORDER, TYPE_META } from '../feedback/feedbackMeta';

const FIELD =
  'w-full rounded-[10px] border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none transition focus-visible:border-[var(--ring)] focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)]';

function ManageDialog({ issueId, onClose }: { issueId: number | null; onClose: () => void }) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['feedback', 'detail', issueId],
    queryFn: () => getFeedback(issueId as number),
    enabled: issueId !== null,
  });
  const [status, setStatus] = React.useState<IssueStatus>('open');
  const [priority, setPriority] = React.useState<IssuePriority>('medium');
  const [version, setVersion] = React.useState('');
  const [note, setNote] = React.useState('');
  const [reply, setReply] = React.useState('');

  React.useEffect(() => {
    const i = detail.data?.issue;
    if (i) { setStatus(i.status); setPriority(i.priority); setVersion(i.shipped_version ?? ''); setNote(i.resolution_note ?? ''); }
  }, [detail.data]);

  const invalidate = () => { void qc.invalidateQueries({ queryKey: ['admin-feedback'] }); void qc.invalidateQueries({ queryKey: ['feedback'] }); };
  const updateMut = useMutation({
    mutationFn: () => adminUpdateFeedback(issueId as number, { status, priority, resolution_note: note || undefined, shipped_version: version || undefined }),
    onSuccess: () => { toast.success('状态已更新'); invalidate(); void detail.refetch(); },
    onError: (e) => toast.error(toastError(e, '更新失败')),
  });
  const replyMut = useMutation({
    mutationFn: () => adminReplyFeedback(issueId as number, reply.trim()),
    onSuccess: () => { toast.success('官方回复已发布'); setReply(''); invalidate(); void detail.refetch(); },
    onError: (e) => toast.error(toastError(e, '回复失败')),
  });
  const deleteMut = useMutation({
    mutationFn: () => adminDeleteFeedback(issueId as number),
    onSuccess: () => { toast.success('已删除'); invalidate(); onClose(); },
    onError: (e) => toast.error(toastError(e, '删除失败')),
  });

  const issue = detail.data?.issue;
  return (
    <Dialog open={issueId !== null} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-[var(--border-subtle)] px-5 py-4">
          <DialogTitle className="text-base">{issue ? `#${issue.id} ${issue.title}` : '反馈详情'}</DialogTitle>
          <DialogDescription className="text-xs">管理状态、优先级与官方回复</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {!issue ? <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">加载中…</div> : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <span>{TYPE_META[issue.type].emoji} {TYPE_META[issue.type].label}</span>
                <span>{issue.author.name}</span>
                <span>👍 {issue.vote_count}</span>
                <span>{formatApiDateTime(issue.created_at)}</span>
              </div>
              {issue.body && <p className="whitespace-pre-wrap rounded-lg bg-[var(--surface-2)] p-3 text-sm text-[var(--foreground)]">{issue.body}</p>}

              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-xs font-semibold text-[var(--foreground)]">状态
                  <select value={status} onChange={(e) => setStatus(e.target.value as IssueStatus)} className={FIELD}>
                    {STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs font-semibold text-[var(--foreground)]">优先级
                  <select value={priority} onChange={(e) => setPriority(e.target.value as IssuePriority)} className={FIELD}>
                    {Object.entries(PRIORITY_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </label>
              </div>
              <label className="flex flex-col gap-1 text-xs font-semibold text-[var(--foreground)]">上线版本（可选）
                <Input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="如 v1.2.0" />
              </label>
              <label className="flex flex-col gap-1 text-xs font-semibold text-[var(--foreground)]">处理结论（可选）
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={cn(FIELD, 'resize-y')} />
              </label>
              <div className="flex items-center justify-between">
                <Button variant="outline" size="sm" className="gap-1 text-rose-600" disabled={deleteMut.isPending} onClick={() => deleteMut.mutate()}>
                  <Trash2 size={14} /> 删除
                </Button>
                <Button size="sm" disabled={updateMut.isPending} onClick={() => updateMut.mutate()}>保存状态</Button>
              </div>

              <div className="border-t border-[var(--border-subtle)] pt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">讨论 · {detail.data?.comments.length ?? 0}</p>
                <div className="flex flex-col gap-2">
                  {detail.data?.comments.map((c) => (
                    <div key={c.id} className={cn('rounded-lg border p-2.5 text-sm', c.is_official ? 'border-indigo-200/70 bg-indigo-50/60 dark:border-indigo-500/30 dark:bg-indigo-500/10' : 'border-[var(--border-subtle)]')}>
                      <div className="mb-1 flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
                        <span className="font-semibold text-[var(--foreground)]">{c.is_system ? '系统' : c.author?.name}</span>
                        {c.is_official && <span className="rounded bg-indigo-600/15 px-1.5 text-indigo-600 dark:text-indigo-300">官方</span>}
                        <span>{formatApiDateTime(c.created_at)}</span>
                      </div>
                      <p className="whitespace-pre-wrap text-[var(--foreground)]">{c.body}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex items-end gap-2">
                  <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={2} placeholder="以官方身份回复…" className={cn(FIELD, 'resize-none')} />
                  <Button size="sm" disabled={!reply.trim() || replyMut.isPending} onClick={() => replyMut.mutate()}>回复</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function FeedbackCenter() {
  const [search, setSearch] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [page, setPage] = React.useState(1);
  const [manageId, setManageId] = React.useState<number | null>(null);

  const stats = useQuery({ queryKey: ['admin-feedback', 'stats'], queryFn: () => getFeedbackStats(true) });
  const list = useQuery({
    queryKey: ['admin-feedback', 'list', { search, status, page }],
    queryFn: () => listFeedback({ search, status: status as IssueStatus | '', page, page_size: 20, sort: 'newest' }, true),
  });

  const columns = React.useMemo<ColumnDef<FeedbackIssue>[]>(() => [
    { accessorKey: 'id', header: '#', cell: (c) => <span className="text-[var(--muted-foreground)]">{c.getValue() as number}</span> },
    { accessorKey: 'title', header: '标题', cell: (c) => (
      <button type="button" onClick={() => setManageId(c.row.original.id)} className="flex items-center gap-1.5 text-left font-medium text-[var(--foreground)] hover:text-indigo-600">
        <span>{TYPE_META[c.row.original.type].emoji}</span><span className="line-clamp-1">{c.getValue() as string}</span>
      </button>
    ) },
    { accessorKey: 'status', header: '状态', cell: (c) => {
      const m = STATUS_META[c.getValue() as IssueStatus];
      return <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold', m.className)}><span className={cn('size-1.5 rounded-full', m.dot)} />{m.label}</span>;
    } },
    { accessorKey: 'vote_count', header: '👍', cell: (c) => <span className="tabular-nums">{c.getValue() as number}</span> },
    { accessorKey: 'author', header: '提交者', cell: (c) => (c.getValue() as FeedbackIssue['author']).name },
    { accessorKey: 'created_at', header: '时间', cell: (c) => <span className="text-xs text-[var(--muted-foreground)]">{formatApiDateTime(c.getValue() as string)}</span> },
  ], []);

  return (
    <div className="flex flex-col gap-4">
      <AdminPageHeader
        kicker="用户声音"
        title="反馈中心"
        description="公开透明的建议与缺陷追踪。处理状态、官方回复与上线版本都留痕，成果一目了然。"
        actions={<Button variant="outline" size="sm" className="gap-1" onClick={() => { void list.refetch(); void stats.refetch(); }}><RefreshCw size={14} /> 刷新</Button>}
      />
      {stats.data && (
        <div className="flex flex-wrap gap-2">
          <KpiPill label="总反馈" value={stats.data.total} />
          <KpiPill label="本周新增" value={stats.data.created_this_week} />
          <KpiPill label="本周解决" value={stats.data.resolved_this_week} />
          <KpiPill label="处理中" value={stats.data.in_progress} />
          <KpiPill label="已上线" value={stats.data.shipped} />
          <KpiPill label="解决率" value={`${Math.round(stats.data.resolve_rate * 100)}%`} />
          <KpiPill label="平均解决" value={stats.data.avg_resolve_hours != null ? `${stats.data.avg_resolve_hours}h` : '—'} />
        </div>
      )}
      {list.isError && <ErrorBanner message="加载反馈失败" onRetry={() => void list.refetch()} />}
      <AdminPanel>
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] p-3">
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="搜索标题/内容…" className="h-9 max-w-xs" />
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={cn(FIELD, 'h-9 w-auto py-0')}>
            <option value="">全部状态</option>
            {STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
          </select>
        </div>
        <DataTable
          columns={columns}
          data={list.data?.items ?? []}
          isLoading={list.isLoading}
          emptyState={<div className="flex flex-col items-center gap-2 py-12 text-center"><MessageSquare size={28} className="text-[var(--muted-foreground)]" /><p className="text-sm text-[var(--muted-foreground)]">暂无反馈</p></div>}
        />
        {(list.data?.total ?? 0) > 20 && (
          <div className="flex items-center justify-center gap-2 border-t border-[var(--border-subtle)] p-3 text-xs">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
            <span className="text-[var(--muted-foreground)]">{page} / {Math.ceil((list.data?.total ?? 0) / 20)}</span>
            <Button variant="outline" size="sm" disabled={page >= Math.ceil((list.data?.total ?? 0) / 20)} onClick={() => setPage((p) => p + 1)}>下一页</Button>
          </div>
        )}
      </AdminPanel>
      <ManageDialog issueId={manageId} onClose={() => setManageId(null)} />
    </div>
  );
}
