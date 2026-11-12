/**
 * 网站部署审批：TanStack Query 数据层 + TanStack Table + shadcn 组件。
 * 后端 API 不变（services/websiteService.ts）。
 */
import * as React from 'react';
import { useState } from 'react';
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
  Eye,
  FileText,
  Presentation,
  FileSpreadsheet } from 'lucide-react';
import { DataTable } from './data-table';
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
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/shadcn/tabs';
import { StatusPill } from './shared';
import {
  DeployRecord,
  cancelDeploy,
  decideDeploy,
  listAllDeploys,
  listPendingDeploys,
  listAdminPublishedItems,
  listAdminPendingPublishedItems,
  decidePublishedItem,
  cancelPublishedItem,
  type PublishedItemRecord,
} from '@/services/websiteService';
import { DeployReviewPanel } from './DeployReviewPanel';
import { toastError } from '../../lib/errors';

/** 外部链接 URL 规范化。
 *
 * 三种形态都要处理：
 * - 绝对 URL（``https://host/path``）—— 原样用；
 * - **站内相对路径**（``/s/<code>/``、``/sites/<slug>/``）—— 原样用，
 *   浏览器会补上当前域。补协议会变成 ``https:///sites/...``（缺主机名，点不开）；
 * - 裸域名（``example.com``，来自 target_domain）—— 补协议。
 */
function toExternalUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const value = raw.trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith('/')) return value;
  return `https://${value}`;
}

/** 安全时间格式化：无效时间戳返回 '--' 而非 "Invalid Date" */
function formatSafeDateTime(value: unknown): string {
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? '--' : d.toLocaleString('zh-CN');
}

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
    deployed: '已发布',
    deploying: '发布中',
    failed: '失败',
    cancelled: '已取消',
    superseded: '已被新版本替代',
  };
  return config[status] || status;
}

const KIND_ICON = {
  ppt: Presentation,
  document: FileText,
  sheet: FileSpreadsheet,
} as const;

function PublishedItemRow({
  item,
  busy,
  onDecide,
  onCancel,
}: {
  item: PublishedItemRecord;
  busy: boolean;
  onDecide?: (decision: 'approved' | 'rejected') => void;
  onCancel?: () => void;
}) {
  const Icon = KIND_ICON[item.kind] ?? FileText;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Icon size={14} className="shrink-0 text-[var(--muted-foreground)]" />
          <span className="truncate text-sm font-semibold text-[var(--foreground)]">
            {item.title}
          </span>
          <StatusPill tone={item.status === 'deployed' ? 'active' : item.status === 'pending' ? 'warning' : 'inactive'}>
            {statusLabel(item.status)}
          </StatusPill>
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-0.5 text-[10px] font-semibold text-[var(--muted-foreground)]">
            {item.kind_label ?? item.kind}
          </span>
        </div>
        {item.description && (
          <p className="mt-1 truncate text-xs text-[var(--muted-foreground)]" title={item.description}>
            {item.description}
          </p>
        )}
        <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">
          用户 {item.user_id} · {formatSafeDateTime(item.created_at)}
          {item.short_code ? ` · /s/${item.short_code}` : ''}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {item.status === 'deployed' && item.short_url && (
          <a
            href={item.short_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-3)]"
          >
            <ExternalLink size={12} />
            打开
          </a>
        )}
        {item.status === 'pending' && onDecide && (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs"
              disabled={busy}
              onClick={() => onDecide('rejected')}
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
              拒绝
            </Button>
            <Button
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              disabled={busy}
              onClick={() => onDecide('approved')}
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              批准
            </Button>
          </>
        )}
        {item.status === 'deployed' && onCancel && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-2 text-xs text-[var(--muted-foreground)]"
            disabled={busy}
            onClick={onCancel}
          >
            取消发布
          </Button>
        )}
      </div>
    </div>
  );
}

export function WebsiteDeployManagement() {
  const queryClient = useQueryClient();
  // 待确认的审批操作（批准/拒绝均需二次确认，防误点）
  // 单内容区 Tab：待审批 / 全部记录。两段内容不再纵向堆叠。
  const [tab, setTab] = useState<'pending' | 'all' | 'published'>('pending');

  const [pendingDecision, setPendingDecision] = useState<{
    deploy: DeployRecord;
    decision: 'approved' | 'rejected';
  } | null>(null);

  const pendingQuery = useQuery({
    queryKey: ['admin', 'deploys', 'pending'],
    queryFn: listPendingDeploys,
  });
  const allQuery = useQuery({
    queryKey: ['admin', 'deploys', 'all'],
    queryFn: listAllDeploys,
  });
  // 文件型作品（PPT / 文档 / 表格）走独立的发布表
  const publishedQuery = useQuery({
    queryKey: ['admin', 'published-items', 'all'],
    queryFn: listAdminPublishedItems,
  });
  const publishedPendingQuery = useQuery({
    queryKey: ['admin', 'published-items', 'pending'],
    queryFn: listAdminPendingPublishedItems,
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
    onError: (err: Error) => toast.error(toastError(err, '操作失败')),
  });

  // ── 文件型作品（PPT / 文档 / 表格）的审批与取消 ──
  const decidePublishedMutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'approved' | 'rejected' }) =>
      decidePublishedItem(id, decision, decision === 'approved' ? '管理员已批准' : '管理员已拒绝'),
    onSuccess: (_data, variables) => {
      toast.success(variables.decision === 'approved' ? '已批准发布' : '已拒绝发布');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'published-items'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '操作失败')),
  });

  const cancelPublishedMutation = useMutation({
    mutationFn: cancelPublishedItem,
    onSuccess: () => {
      toast.success('已取消发布（源产物保留）');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'published-items'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '取消失败')),
  });

  // ── 网站取消部署 ──
  const cancelDeployMutation = useMutation({
    mutationFn: cancelDeploy,
    onSuccess: () => {
      toast.success('已取消部署（源码保留，可重新发布）');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'deploys'] });
      void queryClient.invalidateQueries({ queryKey: ['gallery'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '取消部署失败')),
  });

  const pendingDeploys = pendingQuery.data ?? [];
  const publishedItems = publishedQuery.data ?? [];
  const publishedPending = publishedPendingQuery.data ?? [];

  // 审批前审阅：管理员要能看到「这个东西长什么样」「用户到底要了什么」
  // 「源码有没有危险」才能判断该不该上线。只看项目名 + 文件数就点批准，
  // 等于闭眼放行。
  const [reviewTarget, setReviewTarget] = React.useState<{
    deployId: number;
    slug: string;
  } | null>(null);

  const openPreview = React.useCallback((deployId: number, slug: string) => {
    setReviewTarget({ deployId, slug });
  }, []);
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
            {formatSafeDateTime(getValue())}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '操作',
        enableSorting: false,
        cell: ({ row }) => {
          const deploy = row.original;
          if (deploy.status !== 'deployed' && deploy.status !== 'approved') return null;
          return (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs text-[var(--muted-foreground)]"
              disabled={cancelDeployMutation.isPending}
              onClick={() => cancelDeployMutation.mutate(deploy.id)}
              title="取消部署：站点下线，源码保留"
            >
              取消部署
            </Button>
          );
        },
      },
      {
        id: 'preview',
        header: '预览',
        enableSorting: false,
        cell: ({ row }) => {
          const deploy = row.original;
          return (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() => void openPreview(deploy.id, deploy.project_slug)}
            >
              <Eye className="h-3 w-3" />
              预览
            </Button>
          );
        },
      },
      {
        id: 'link',
        header: '站点',
        enableSorting: false,
        cell: ({ row }) => {
          const deploy = row.original;
          // 优先短链（/s/<code>/）—— 对外地址不暴露目录名。
          const rawUrl =
            deploy.short_url ||
            deploy.deploy_url ||
            (deploy.status === 'deployed' ? deploy.target_domain : null);
          const url = toExternalUrl(rawUrl);
          if (!url) return <span className="text-xs text-[var(--muted-foreground)]">—</span>;
          return (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium text-zinc-700 hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              访问
            </a>
          );
        },
      },
    ],
    [openPreview, cancelDeployMutation],
  );

  return (
    <div className="space-y-3">
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

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)} className="w-full">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="pending" className="gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            待审批
            {pendingDeploys.length > 0 ? (
              <span className="rounded-full bg-[var(--surface-2)] px-1.5 text-[10px] font-semibold tabular-nums">
                {pendingDeploys.length}
              </span>
            ) : null}
          </TabsTrigger>
          <TabsTrigger value="all" className="gap-1.5">
            <Globe className="h-3.5 w-3.5" />
            全部网站
            <span className="rounded-full bg-[var(--surface-2)] px-1.5 text-[10px] font-semibold tabular-nums">
              {allDeploys.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="published" className="gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            文件作品
            {publishedPending.length > 0 ? (
              <span className="rounded-full bg-amber-100 px-1.5 text-[10px] font-semibold tabular-nums text-amber-800">
                {publishedPending.length}
              </span>
            ) : (
              <span className="rounded-full bg-[var(--surface-2)] px-1.5 text-[10px] font-semibold tabular-nums">
                {publishedItems.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="m-0 pt-3">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">

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
                    <span className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-800">
                      {deploy.stack}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-medium text-[var(--muted-foreground)]">
                    用户 {deploy.requested_by}
                    {deploy.target_domain ? ` · ${deploy.target_domain}` : ''}
                  </div>
                  {deploy.description && (
                    <p className="mt-1.5 max-w-xl rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-1.5 text-xs leading-relaxed text-[var(--foreground)]">
                      {deploy.description}
                    </p>
                  )}
                  {(deploy.short_url || deploy.deploy_url || deploy.target_domain) && (
                    <a
                      href={
                        toExternalUrl(
                          deploy.short_url || deploy.deploy_url || deploy.target_domain,
                        ) ?? '#'
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-zinc-700 hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      在线预览
                    </a>
                  )}
                </div>
                <div className="flex gap-2">
                  {/* 审阅面板：一屏给齐网站说明 + 完整对话 + 实时预览 +
                      源码扫描 + AI 风险意见。待审批的申请最需要它 ——
                      只看项目名就点批准等于闭眼放行。 */}
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5"
                    onClick={() => openPreview(deploy.id, deploy.project_slug)}
                  >
                    <Eye className="h-3 w-3" />
                    审阅
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5"
                    onClick={() => setPendingDecision({ deploy, decision: 'rejected' })}
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
                    onClick={() => setPendingDecision({ deploy, decision: 'approved' })}
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
          </div>
        </TabsContent>

        <TabsContent value="published" className="m-0 pt-3">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
            {publishedPending.length > 0 && (
              <div className="mb-4">
                <p className="mb-2 text-xs font-semibold text-[var(--foreground)]">
                  待审批（{publishedPending.length}）
                </p>
                <div className="space-y-3">
                  {publishedPending.map((item) => (
                    <PublishedItemRow
                      key={item.id}
                      item={item}
                      busy={
                        decidePublishedMutation.isPending &&
                        decidePublishedMutation.variables?.id === item.id
                      }
                      onDecide={(decision) =>
                        decidePublishedMutation.mutate({ id: item.id, decision })
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            <p className="mb-2 text-xs font-semibold text-[var(--foreground)]">
              全部文件作品（{publishedItems.length}）
            </p>
            {publishedItems.length === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
                暂无文件作品
              </p>
            ) : (
              <div className="space-y-2">
                {publishedItems.map((item) => (
                  <PublishedItemRow
                    key={item.id}
                    item={item}
                    busy={cancelPublishedMutation.isPending}
                    onCancel={() => cancelPublishedMutation.mutate(item.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="all" className="m-0 pt-3">
          <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]">
        <DataTable
          columns={columns}
          data={allDeploys}
          pageSize={10}
          isLoading={allQuery.isLoading}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <AlertCircle className="mb-3 h-10 w-10 text-zinc-300" />
              <p className="text-sm font-semibold text-[var(--muted-foreground)]">暂无部署记录</p>
            </div>
          }
        />
          </div>
        </TabsContent>
      </Tabs>

      {/* 审批二次确认 */}
      <AlertDialog
        open={pendingDecision !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDecision(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingDecision?.decision === 'approved' ? '批准部署' : '拒绝部署'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDecision?.decision === 'approved'
                ? `确定批准「${pendingDecision?.deploy.project_slug ?? ''}」的部署申请吗？批准后站点将对外发布。`
                : `确定拒绝「${pendingDecision?.deploy.project_slug ?? ''}」的部署申请吗？申请人将看到拒绝原因。`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingDecision) {
                  decideMutation.mutate({
                    deployId: pendingDecision.deploy.id,
                    decision: pendingDecision.decision,
                  });
                }
                setPendingDecision(null);
              }}
              className={
                pendingDecision?.decision === 'rejected'
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : undefined
              }
            >
              {pendingDecision?.decision === 'approved' ? '批准' : '拒绝'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 审批前审阅面板：对话 + 预览 + 源码扫描 + AI 意见 */}
      {reviewTarget && (
        <DeployReviewPanel
          deployId={reviewTarget.deployId}
          projectSlug={reviewTarget.slug}
          onClose={() => setReviewTarget(null)}
        />
      )}
    </div>
  );
}
