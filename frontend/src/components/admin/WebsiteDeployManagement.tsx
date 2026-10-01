/**
 * 网站部署审批：TanStack Query 数据层 + TanStack Table + shadcn 组件。
 * 后端 API 不变（services/websiteService.ts）。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  AlertCircle,
  Check,
  Clock,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  X,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { StatusPill } from './shared';
import {
  DeployRecord,
  decideDeploy,
  listAllDeploys,
  listPendingDeploys,
} from '@/services/websiteService';

function statusTone(status: string): 'active' | 'inactive' | 'warning' | 'info' {
  switch (status) {
    case 'deployed':
      return 'active';
    case 'pending':
      return 'warning';
    case 'approved':
    case 'deploying':
      return 'info';
    default:
      return 'inactive';
  }
}

function statusLabel(status: string): string {
  const config: Record<string, string> = {
    pending: '待审批',
    approved: '已批准',
    rejected: '已拒绝',
    deployed: '已部署',
    deploying: '部署中',
    failed: '失败',
  };
  return config[status] || status;
}

export function WebsiteDeployManagement() {
  const queryClient = useQueryClient();

  const pendingQuery = useQuery({
    queryKey: ['admin', 'deploys', 'pending'],
    queryFn: listPendingDeploys,
  });
  const allQuery = useQuery({
    queryKey: ['admin', 'deploys', 'all'],
    queryFn: listAllDeploys,
  });

  const loading = pendingQuery.isLoading || allQuery.isLoading;
  const error =
    (pendingQuery.error as Error | null)?.message ??
    (allQuery.error as Error | null)?.message ??
    null;

  const decideMutation = useMutation({
    mutationFn: ({ deployId, decision }: { deployId: number; decision: 'approved' | 'rejected' }) =>
      decideDeploy(deployId, {
        status: decision,
        reason: decision === 'approved' ? '管理员已批准' : '管理员已拒绝',
      }),
    onSuccess: (_data, variables) => {
      toast.success(variables.decision === 'approved' ? '已批准部署' : '已拒绝部署');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'deploys'] });
    },
    onError: (err: Error) => toast.error(err.message || '操作失败'),
  });

  const pendingDeploys = pendingQuery.data ?? [];
  const allDeploys = allQuery.data ?? [];

  const columns = React.useMemo<ColumnDef<DeployRecord, unknown>[]>(
    () => [
      {
        id: 'project',
        header: '项目',
        cell: ({ row }) => {
          const deploy = row.original;
          return (
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Globe className="h-4 w-4 shrink-0 text-[var(--muted-foreground)]" />
                <span className="truncate text-sm font-semibold text-[var(--foreground)]">
                  {deploy.project_slug}
                </span>
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-semibold text-[var(--muted-foreground)]">
                  {deploy.stack}
                </span>
              </div>
              <p className="mt-0.5 truncate text-xs font-medium text-[var(--muted-foreground)]">
                用户 {deploy.requested_by}
                {deploy.target_domain ? ` · ${deploy.target_domain}` : ''}
              </p>
            </div>
          );
        },
      },
      {
        accessorKey: 'status',
        header: '状态',
        cell: ({ getValue }) => {
          const status = String(getValue());
          return <StatusPill tone={statusTone(status)}>{statusLabel(status)}</StatusPill>;
        },
      },
      {
        accessorKey: 'created_at',
        header: '创建时间',
        cell: ({ getValue }) => (
          <span className="text-xs font-medium text-[var(--muted-foreground)]">
            {new Date(String(getValue())).toLocaleString('zh-CN')}
          </span>
        ),
      },
      {
        id: 'link',
        header: '站点',
        enableSorting: false,
        cell: ({ row }) => {
          const deploy = row.original;
          const url = deploy.deploy_url || (deploy.status === 'deployed' ? deploy.target_domain : null);
          if (!url) return <span className="text-xs text-[var(--muted-foreground)]">—</span>;
          return (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              访问
            </a>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="网站管理"
        title="部署审批"
        actions={
          <>
            <KpiPill label="待审批" value={pendingDeploys.length} />
            <KpiPill label="总计" value={allDeploys.length} />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                void pendingQuery.refetch();
                void allQuery.refetch();
              }}
              disabled={loading}
            >
              {loading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
          </>
        }
      />

      {error ? <ErrorBanner message={error} /> : null}

      {/* 待审批请求 */}
      <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <Clock className="h-4 w-4 text-indigo-600" />
          <h3 className="text-base font-semibold text-[var(--foreground)]">待审批请求</h3>
        </div>

        {pendingQuery.isLoading ? (
          <div className="space-y-3" aria-busy="true" aria-label="加载中">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="animate-pulse rounded-lg border border-zinc-200/60 bg-[var(--surface-2)] p-4"
              >
                <div className="flex items-center gap-3">
                  <div className="h-4 w-4 rounded bg-zinc-200" />
                  <div className="h-4 w-40 rounded bg-zinc-200" />
                </div>
                <div className="mt-2 h-3 w-64 rounded bg-zinc-200/80" />
              </div>
            ))}
          </div>
        ) : pendingDeploys.length === 0 ? (
          <p className="py-8 text-center text-sm font-medium text-[var(--muted-foreground)]">
            暂无待审批的部署请求
          </p>
        ) : (
          <div className="space-y-3">
            {pendingDeploys.map((deploy) => (
              <div
                key={deploy.id}
                className="flex flex-col gap-3 rounded-lg border border-[var(--border-subtle)] bg-zinc-50/50 p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-[var(--muted-foreground)]" />
                    <span className="font-semibold text-[var(--foreground)]">{deploy.project_slug}</span>
                    <span className="rounded-full border border-indigo-200/80 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                      {deploy.stack}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-medium text-[var(--muted-foreground)]">
                    用户 {deploy.requested_by}
                    {deploy.target_domain ? ` · ${deploy.target_domain}` : ''}
                  </div>
                  {(deploy.deploy_url || deploy.target_domain) && (
                    <a
                      href={deploy.deploy_url || deploy.target_domain || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      预览
                    </a>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    className="gap-1.5"
                    onClick={() =>
                      decideMutation.mutate({ deployId: deploy.id, decision: 'rejected' })
                    }
                    disabled={decideMutation.isPending}
                  >
                    {decideMutation.isPending &&
                    decideMutation.variables?.deployId === deploy.id &&
                    decideMutation.variables?.decision === 'rejected' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <X size={14} />
                    )}
                    拒绝
                  </Button>
                  <Button
                    size="sm"
                    className="gap-1.5"
                    onClick={() =>
                      decideMutation.mutate({ deployId: deploy.id, decision: 'approved' })
                    }
                    disabled={decideMutation.isPending}
                  >
                    {decideMutation.isPending &&
                    decideMutation.variables?.deployId === deploy.id &&
                    decideMutation.variables?.decision === 'approved' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Check size={14} />
                    )}
                    批准
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 全部部署记录 */}
      <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        <div className="border-b border-[var(--border-subtle)] px-5 py-4">
          <h3 className="text-base font-semibold text-[var(--foreground)]">全部部署记录</h3>
        </div>
        <DataTable
          columns={columns}
          data={allDeploys}
          isLoading={allQuery.isLoading}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <AlertCircle className="mb-3 h-10 w-10 text-zinc-300" />
              <p className="text-sm font-semibold text-zinc-600">暂无部署记录</p>
            </div>
          }
        />
      </section>
    </div>
  );
}
