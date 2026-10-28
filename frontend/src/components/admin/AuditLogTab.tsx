/**
 * 权限管理 · 审计日志。
 * 只读排查面板：按动作 / 资源 / 结果过滤，展开看 detail。保留期外可手工清理。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronRight, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Skeleton } from '@/components/shadcn/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/shadcn/alert-dialog';
import { ErrorBanner } from './shared';
import { listAuditLogs, purgeAuditLogs, type AuditLog } from '@/services/permissionService';
import { cn } from '@/lib/utils';
import { toastError } from '../../lib/errors';

const PAGE_SIZE = 50;

const RESULT_STYLE: Record<string, string> = {
  allow: 'bg-emerald-100 text-emerald-700',
  deny: 'bg-rose-100 text-rose-700',
  error: 'bg-amber-100 text-amber-700',
};

const RESULT_LABEL: Record<string, string> = {
  allow: '成功',
  deny: '拒绝',
  error: '异常',
};

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function AuditLogTab() {
  const queryClient = useQueryClient();
  const [action, setAction] = React.useState('');
  const [resourceType, setResourceType] = React.useState('');
  const [result, setResult] = React.useState('');
  const [page, setPage] = React.useState(0);
  const [expanded, setExpanded] = React.useState<Set<number>>(new Set());
  const [purging, setPurging] = React.useState(false);

  const filters = React.useMemo(
    () => ({
      action: action.trim() || undefined,
      resourceType: resourceType.trim() || undefined,
      result: result || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [action, resourceType, result, page],
  );

  const logsQuery = useQuery({
    queryKey: ['admin', 'permissions', 'audit', filters],
    queryFn: () => listAuditLogs(filters),
  });

  const purgeMutation = useMutation({
    mutationFn: () => purgeAuditLogs(),
    onSuccess: (res) => {
      toast.success(`已清理 ${res.deleted} 条（保留期 ${res.retention_days} 天）`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'permissions', 'audit'] });
    },
    onError: (err) => toast.error(toastError(err, '清理失败')),
  });

  const items = logsQuery.data?.items ?? [];
  const total = logsQuery.data?.total ?? 0;
  const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  const resetTo = (fn: () => void) => {
    fn();
    setPage(0);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={action}
          onChange={(e) => resetTo(() => setAction(e.target.value))}
          placeholder="动作，如 role.create"
          className="h-8 w-56"
          aria-label="按动作过滤"
        />
        <Input
          value={resourceType}
          onChange={(e) => resetTo(() => setResourceType(e.target.value))}
          placeholder="资源类型，如 kb"
          className="h-8 w-40"
          aria-label="按资源类型过滤"
        />
        <select
          value={result}
          onChange={(e) => resetTo(() => setResult(e.target.value))}
          className="h-8 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 text-xs text-[var(--foreground)]"
          aria-label="按结果过滤"
        >
          <option value="">全部结果</option>
          <option value="allow">成功</option>
          <option value="deny">拒绝</option>
          <option value="error">异常</option>
        </select>
        <Button size="sm" variant="ghost" onClick={() => logsQuery.refetch()} disabled={logsQuery.isFetching}>
          <RefreshCw className={cn('mr-1.5 h-4 w-4', logsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-[var(--muted-foreground)]">共 {total} 条</span>
          <Button size="sm" variant="outline" onClick={() => setPurging(true)}>
            <Trash2 className="mr-1.5 h-4 w-4" />
            清理过期
          </Button>
        </div>
      </div>

      {logsQuery.isError && (
        <ErrorBanner message={toastError(logsQuery.error, '审计日志加载失败')} onRetry={() => void logsQuery.refetch()} />
      )}

      <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]">
        {logsQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="px-4 py-12 text-center text-sm text-[var(--muted-foreground)]">没有符合条件的审计记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-left text-[11px] uppercase tracking-wide text-[var(--muted-foreground)]">
                <tr>
                  <th className="w-8 px-2 py-2" />
                  <th className="px-3 py-2 font-semibold">时间</th>
                  <th className="px-3 py-2 font-semibold">操作人</th>
                  <th className="px-3 py-2 font-semibold">动作</th>
                  <th className="px-3 py-2 font-semibold">资源</th>
                  <th className="px-3 py-2 font-semibold">结果</th>
                  <th className="px-3 py-2 font-semibold">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {items.map((log) => (
                  <AuditRow
                    key={log.id}
                    log={log}
                    open={expanded.has(log.id)}
                    onToggle={() =>
                      setExpanded((prev) => {
                        const next = new Set(prev);
                        if (next.has(log.id)) next.delete(log.id);
                        else next.add(log.id);
                        return next;
                      })
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <Button
            size="sm"
            variant="outline"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            上一页
          </Button>
          <span className="text-xs text-[var(--muted-foreground)]">
            第 {page + 1} / {maxPage + 1} 页
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= maxPage}
            onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
          >
            下一页
          </Button>
        </div>
      )}

      <AlertDialog open={purging} onOpenChange={setPurging}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>清理过期审计日志？</AlertDialogTitle>
            <AlertDialogDescription>
              只会删除超出保留期（默认 180 天，可在后端配置）的记录，近期日志不受影响。此操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                purgeMutation.mutate();
                setPurging(false);
              }}
            >
              清理
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function AuditRow({ log, open, onToggle }: { log: AuditLog; open: boolean; onToggle: () => void }) {
  const hasDetail = Object.keys(log.detail ?? {}).length > 0;
  return (
    <>
      <tr className="align-top">
        <td className="px-2 py-2">
          <button
            type="button"
            onClick={onToggle}
            disabled={!hasDetail}
            className={cn(
              'flex h-5 w-5 items-center justify-center rounded text-[var(--muted-foreground)] transition-transform',
              hasDetail ? 'hover:bg-[var(--surface-2)]' : 'opacity-0',
              open && 'rotate-90',
            )}
            aria-label={open ? '收起详情' : '展开详情'}
            aria-expanded={open}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--muted-foreground)]">
          {formatTime(log.created_at)}
        </td>
        <td className="max-w-[180px] truncate px-3 py-2 text-xs text-[var(--foreground)]" title={log.actor_email ?? ''}>
          {log.actor_email ?? (log.actor_id != null ? `#${log.actor_id}` : '匿名')}
        </td>
        <td className="px-3 py-2 font-mono text-xs text-[var(--foreground)]">{log.action}</td>
        <td className="px-3 py-2 text-xs text-[var(--muted-foreground)]">
          {log.resource_type ? `${log.resource_type}${log.resource_id ? `:${log.resource_id}` : ''}` : '—'}
        </td>
        <td className="px-3 py-2">
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px] font-medium',
              RESULT_STYLE[log.result] ?? 'bg-[var(--surface-2)] text-[var(--muted-foreground)]',
            )}
          >
            {RESULT_LABEL[log.result] ?? log.result}
          </span>
        </td>
        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-[var(--muted-foreground)]">{log.ip ?? '—'}</td>
      </tr>
      {open && hasDetail && (
        <tr>
          <td colSpan={7} className="bg-[var(--surface-2)] px-4 py-3">
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[var(--surface-1)] p-3 text-[11px] leading-5 text-[var(--foreground)]">
              {JSON.stringify(log.detail, null, 2)}
            </pre>
            {log.user_agent && (
              <p className="mt-2 break-all text-[11px] text-[var(--muted-foreground)]">UA: {log.user_agent}</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
