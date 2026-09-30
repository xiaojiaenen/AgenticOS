/**
 * 企业上游管理：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Dialog/AlertDialog。
 * 后端 API 不变（services/upstreamService.ts）。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  Activity,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
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
import { getStoredUser } from '@/services/authService';
import {
  adminListUpstreamCredentials,
  createUpstreamApiKey,
  getUpstreamStatus,
  listUpstreamApiKeys,
  revokeUpstreamApiKey,
  setUpstreamApiKeyEnabled,
  type UpstreamApiKey,
  type UpstreamCredentialStatus,
} from '@/services/upstreamService';

const statusLabelMap: Record<string, string> = {
  active: '正常',
  pending: '待登录',
  failed: '登录失败',
  expired: '已过期',
};

function formatTime(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return value;
  }
}

const createKeySchema = z.object({
  name: z.string().min(1, '请填写 Key 名称'),
});
type CreateKeyValues = z.infer<typeof createKeySchema>;

export const UpstreamManagement = () => {
  const queryClient = useQueryClient();
  const user = getStoredUser();
  const isAdmin = user?.role === 'admin';

  const [createKeyOpen, setCreateKeyOpen] = React.useState(false);
  const [revokingKey, setRevokingKey] = React.useState<UpstreamApiKey | null>(null);
  const [createdKey, setCreatedKey] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const upstreamQuery = useQuery({
    queryKey: ['admin', 'upstream', 'status'],
    queryFn: getUpstreamStatus,
  });
  const keysQuery = useQuery({
    queryKey: ['admin', 'upstream', 'keys'],
    queryFn: listUpstreamApiKeys,
  });
  const adminQuery = useQuery({
    queryKey: ['admin', 'upstream', 'admin-credentials'],
    queryFn: adminListUpstreamCredentials,
    enabled: isAdmin,
  });

  const apiKeys = keysQuery.data?.items ?? [];
  const adminItems =
    (isAdmin ? adminQuery.data?.items : upstreamQuery.data?.items) ?? [];

  const refreshAll = () => {
    void upstreamQuery.refetch();
    void keysQuery.refetch();
    if (isAdmin) void adminQuery.refetch();
  };

  const form = useForm<CreateKeyValues>({
    resolver: zodResolver(createKeySchema),
    defaultValues: { name: '外部服务' },
  });

  const createKeyMutation = useMutation({
    mutationFn: (values: CreateKeyValues) => createUpstreamApiKey(values.name.trim() || 'default'),
    onSuccess: (item) => {
      toast.success('API Key 已创建，明文仅显示这一次，请立即保存');
      setCreatedKey(item.key ?? null);
      setCreateKeyOpen(false);
      form.reset({ name: '外部服务' });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'upstream'] });
    },
    onError: (err: Error) => toast.error(err.message || '创建 API Key 失败'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      setUpstreamApiKeyEnabled(id, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'upstream'] });
    },
    onError: (err: Error) => toast.error(err.message || '更新失败'),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => revokeUpstreamApiKey(id),
    onSuccess: () => {
      toast.success('API Key 已删除');
      setRevokingKey(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'upstream'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const status = upstreamQuery.data;
  const mine = status?.mine;
  const health = status?.health;
  const cookieReady = Boolean(mine?.healthy);

  const kpis = [
    { label: '上游地址', value: status?.upstream || 'agents.gree.com', icon: Server },
    {
      label: '站点连通',
      value:
        health?.reachable === true
          ? '可达'
          : health?.reachable === false
            ? '不可达'
            : '检测中',
      icon: health?.reachable ? Wifi : WifiOff,
    },
    { label: 'Cookie 策略', value: '登录自动获取 · 快过期自动续期', icon: ShieldCheck },
    {
      label: '本机 Cookie',
      value: cookieReady ? '可用' : mine ? statusLabelMap[mine.status] || mine.status : '未配置',
      icon: KeyRound,
    },
  ];

  // ── API Key 表格 ──
  const keyColumns = React.useMemo<ColumnDef<UpstreamApiKey, unknown>[]>(
    () => [
      {
        accessorKey: 'name',
        header: '名称',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-800">{String(getValue())}</span>
        ),
      },
      {
        id: 'key',
        header: 'Key',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="font-mono text-xs text-zinc-600">
            {row.original.key_masked || `${row.original.prefix}…`}
          </span>
        ),
      },
      {
        accessorKey: 'enabled',
        header: '状态',
        cell: ({ getValue }) => {
          const enabled = getValue() === true;
          return (
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                enabled
                  ? 'border-emerald-200/80 bg-emerald-50 text-emerald-600'
                  : 'border-zinc-200 bg-zinc-100 text-zinc-500'
              }`}
            >
              {enabled ? '启用' : '停用'}
            </span>
          );
        },
      },
      {
        accessorKey: 'last_used_at',
        header: '最近使用',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium tabular-nums text-zinc-600">
            {formatTime(getValue() as string | null)}
          </span>
        ),
      },
      {
        accessorKey: 'created_at',
        header: '创建时间',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium tabular-nums text-zinc-600">
            {formatTime(getValue() as string | null)}
          </span>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const item = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="xs"
                disabled={toggleMutation.isPending}
                onClick={() => toggleMutation.mutate({ id: item.id, enabled: !item.enabled })}
              >
                {item.enabled ? '停用' : '启用'}
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                onClick={() => setRevokingKey(item)}
                title="删除"
              >
                <Trash2 size={14} />
              </Button>
            </div>
          );
        },
      },
    ],
    [toggleMutation],
  );

  // ── 用户登录态总览表格 ──
  const credentialColumns = React.useMemo<ColumnDef<UpstreamCredentialStatus, unknown>[]>(
    () => [
      {
        accessorKey: 'user_id',
        header: '用户 ID',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium tabular-nums text-zinc-700">{Number(getValue())}</span>
        ),
      },
      {
        accessorKey: 'username',
        header: '账号',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-800">{String(getValue())}</span>
        ),
      },
      {
        id: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => {
          const item = row.original;
          return (
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                item.healthy
                  ? 'border-emerald-200/80 bg-emerald-50 text-emerald-600'
                  : item.status === 'failed'
                    ? 'border-rose-200/80 bg-rose-50 text-rose-600'
                    : 'border-amber-200/80 bg-amber-50 text-amber-700'
              }`}
            >
              {statusLabelMap[item.status] || item.status}
            </span>
          );
        },
      },
      {
        accessorKey: 'expire_at',
        header: 'Cookie 过期',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium tabular-nums text-zinc-600">
            {formatTime(getValue() as string | null)}
          </span>
        ),
      },
      {
        accessorKey: 'last_login_at',
        header: '上次登录',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium tabular-nums text-zinc-600">
            {formatTime(getValue() as string | null)}
          </span>
        ),
      },
      {
        accessorKey: 'last_error',
        header: '错误',
        enableSorting: false,
        cell: ({ getValue }) => {
          const err = getValue() as string | null;
          return (
            <span
              className="block max-w-[200px] truncate text-sm font-medium text-rose-500"
              title={err || ''}
            >
              {err || '—'}
            </span>
          );
        },
      },
    ],
    [],
  );

  if (upstreamQuery.isPending) {
    return (
      <div className="space-y-5">
        <div className="flex h-40 items-center justify-center gap-3 rounded-lg border border-zinc-200/80 bg-white shadow-sm">
          <Loader2 size={20} className="animate-spin text-zinc-400" />
          <span className="text-sm font-medium text-zinc-400">正在加载企业上游状态...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="企业上游"
        title="agents.gree.com"
        description="登录 AgenticOS 后自动获取上游 Cookie，快过期时自动续期。本机对话默认使用你的 Cookie 直连上游，无需 API Key。API Key 仅用于外部软件接入。"
        actions={
          <Button variant="outline" size="sm" className="gap-1.5" onClick={refreshAll}>
            {upstreamQuery.isFetching ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            刷新
          </Button>
        }
      />

      <section className="grid gap-2.5 rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((item) => (
          <div key={item.label} className="rounded-lg border border-zinc-100 bg-zinc-50/60 px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] font-semibold tracking-wide text-zinc-400">{item.label}</p>
              <item.icon size={14} className="text-zinc-400" />
            </div>
            <p className="mt-1.5 truncate text-lg font-semibold tracking-tight text-zinc-950" title={String(item.value)}>
              {item.value}
            </p>
          </div>
        ))}
      </section>

      {upstreamQuery.isError ? (
        <ErrorBanner
          message={(upstreamQuery.error as Error).message || '加载企业上游状态失败'}
        />
      ) : null}

      {/* API Keys */}
      <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-zinc-200/80 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <KeyRound size={18} className="text-indigo-600" />
            <div>
              <h2 className="text-base font-semibold text-zinc-900">API Key</h2>
              <p className="mt-0.5 text-xs font-medium text-zinc-400">
                仅供外部软件：<code>Authorization: Bearer sk-agenticos-…</code> 调用{' '}
                <code>/v1/chat/completions</code>。本机 AgenticOS 不需要 Key。
              </p>
            </div>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => setCreateKeyOpen(true)}>
            <Plus size={14} />
            创建 Key
          </Button>
        </div>

        {createdKey && (
          <div className="border-b border-zinc-100 bg-emerald-50/50 px-5 py-4">
            <p className="text-xs font-semibold text-emerald-700">
              新建 Key（请立即复制保存，关闭后无法再次查看明文）
            </p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 truncate rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs font-medium text-zinc-800">
                {createdKey}
              </code>
              <Button
                type="button"
                variant="outline"
                size="xs"
                className="gap-1"
                onClick={async () => {
                  if (!createdKey) return;
                  try {
                    await navigator.clipboard.writeText(createdKey);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  } catch {
                    // ignore
                  }
                }}
              >
                <Copy size={12} />
                {copied ? '已复制' : '复制'}
              </Button>
            </div>
          </div>
        )}

        <DataTable
          columns={keyColumns}
          data={apiKeys}
          isLoading={keysQuery.isLoading}
          skeletonRows={4}
          emptyState={
            <p className="py-6 text-center text-sm font-medium text-zinc-400">
              尚无 API Key，点击「创建 Key」生成
            </p>
          }
        />
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-indigo-600" />
            <h2 className="text-base font-semibold text-zinc-900">连接与配置</h2>
          </div>
          <dl className="mt-4 space-y-3 text-sm">
            {[
              ['上游 API', status?.base_url || 'https://agents.gree.com'],
              ['登录页', status?.login_url || '—'],
              ['自动登录', status?.auto_login_enabled ? '开启（登录时自动获取 Cookie）' : '关闭'],
              ['预续期', '过期前 2 小时自动续期'],
              ['HTTP 状态', health?.http_status != null ? String(health.http_status) : '—'],
              ['网关地址', '/v1/chat/completions'],
            ].map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4">
                <dt className="shrink-0 font-medium text-zinc-500">{k}</dt>
                <dd className="truncate text-right font-medium text-zinc-800" title={String(v)}>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-indigo-600" />
            <h2 className="text-base font-semibold text-zinc-900">我的 Cookie</h2>
          </div>
          {mine ? (
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-500">状态</span>
                <span
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                    mine.healthy
                      ? 'bg-emerald-500/15 text-emerald-600'
                      : mine.status === 'failed'
                        ? 'bg-rose-500/15 text-rose-600'
                        : 'bg-amber-500/15 text-amber-700'
                  }`}
                >
                  {statusLabelMap[mine.status] || mine.status}
                  {mine.healthy ? ' · Cookie 可用' : ''}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-500">账号</span>
                <span className="font-medium text-zinc-800">{mine.username}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-500">过期时间</span>
                <span className="font-medium tabular-nums text-zinc-800">{formatTime(mine.expire_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-500">上次登录</span>
                <span className="font-medium tabular-nums text-zinc-800">
                  {formatTime(mine.last_login_at)}
                </span>
              </div>
              {mine.last_error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-600">
                  {mine.last_error}
                </p>
              )}
            </div>
          ) : (
            <div className="mt-4 rounded-lg bg-zinc-50 px-4 py-6 text-center text-sm font-medium text-zinc-500">
              尚未配置上游凭据。
              <br />
              使用 LDAP 工号登录后会自动获取 Cookie。
            </div>
          )}
        </section>
      </div>

      {isAdmin && (
        <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-zinc-200/80 px-5 py-4">
            <div className="flex items-center gap-2">
              <ShieldCheck size={18} className="text-indigo-600" />
              <h2 className="text-base font-semibold text-zinc-900">用户登录态总览</h2>
            </div>
            <span className="text-xs font-medium text-zinc-400">
              共 {adminItems.length} 条 · 自动续期中
            </span>
          </div>
          {adminQuery.isError ? (
            <div className="p-4">
              <ErrorBanner
                message={(adminQuery.error as Error).message || '用户登录态加载失败'}
              />
            </div>
          ) : (
            <DataTable
              columns={credentialColumns}
              data={adminItems}
              isLoading={adminQuery.isLoading}
              skeletonRows={4}
              emptyState={
                <p className="py-6 text-center text-sm font-medium text-zinc-400">
                  暂无用户配置上游登录态
                </p>
              }
            />
          )}
        </section>
      )}

      <section className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
        <p className="text-[11px] font-semibold tracking-wide text-zinc-400">
          自动流程（无需手动登录）
        </p>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm font-medium text-zinc-500">
          <li>用户登录 AgenticOS（LDAP / 本地）</li>
          <li>自动写入上游凭据并 Playwright 登录 agents.gree.com</li>
          <li>Cookie 快过期（默认提前 2 小时）由后台任务自动续期</li>
          <li>
            本机对话直接使用当前用户 Cookie，无需 API Key；外部软件才用 Key 调{' '}
            <code>/v1/chat/completions</code>
          </li>
        </ol>
      </section>

      {/* 创建 Key 弹窗 */}
      <Dialog open={createKeyOpen} onOpenChange={setCreateKeyOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>创建 API Key</DialogTitle>
            <DialogDescription>
              创建后明文仅显示一次，请立即复制保存。
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={form.handleSubmit((values) => void createKeyMutation.mutateAsync(values))}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <Label htmlFor="upstream-key-name">Key 名称</Label>
              <Input id="upstream-key-name" placeholder="名称，如 OpenSpider" {...form.register('name')} />
              {form.formState.errors.name ? (
                <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateKeyOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={createKeyMutation.isPending} className="gap-2">
                {createKeyMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                创建
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 删除 Key 确认 */}
      <AlertDialog open={revokingKey !== null} onOpenChange={(next) => !next && setRevokingKey(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除 API Key</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除 Key「{revokingKey?.name}」？使用该 Key 的外部服务将立即失去访问权限。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revokeMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={revokeMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (revokingKey) revokeMutation.mutate(revokingKey.id);
              }}
            >
              {revokeMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
