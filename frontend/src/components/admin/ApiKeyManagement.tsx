/**
 * API Key 管理：给外部软件（Cursor / Cherry Studio / Dify 等）发放调用凭证。
 * 凭证明文仅在创建时返回一次，之后只能看到前缀。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Terminal,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Switch } from '@/components/shadcn/switch';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import { AdminPageHeader, AdminPanel, ErrorBanner } from './shared';
import {
  GATEWAY_BASE_URL,
  createApiKey,
  deleteApiKey,
  listApiKeys,
  setApiKeyEnabled,
  type ApiKey,
  type CreatedApiKey,
} from '@/services/apiKeyService';
import { cn } from '@/lib/utils';
import { toastError } from '../../lib/errors';

const QUERY_KEY = ['admin', 'api-keys'] as const;

function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ApiKeyManagement() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [nameInput, setNameInput] = React.useState('');
  const [createdKey, setCreatedKey] = React.useState<CreatedApiKey | null>(null);
  const [deletingKey, setDeletingKey] = React.useState<ApiKey | null>(null);
  const [guideOpen, setGuideOpen] = React.useState(true);
  const [copied, setCopied] = React.useState(false);
  const copiedTimerRef = React.useRef<number | null>(null);

  // 卸载时清理复制成功的回退定时器
  React.useEffect(
    () => () => {
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
    },
    [],
  );

  const keysQuery = useQuery({ queryKey: QUERY_KEY, queryFn: listApiKeys });
  const keys = keysQuery.data ?? [];

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const createMutation = useMutation({
    mutationFn: (name: string) => createApiKey(name),
    onSuccess: (saved) => {
      setCreatedKey(saved);
      setCreateOpen(false);
      setNameInput('');
      setCopied(false);
      toast.success('API Key 已创建');
      void invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '创建失败')),
  });

  const toggleMutation = useMutation({
    mutationFn: (payload: { id: number; enabled: boolean }) =>
      setApiKeyEnabled(payload.id, payload.enabled),
    onSuccess: (_data, variables) => {
      toast.success(variables.enabled ? '已启用该 Key' : '已停用该 Key');
      void invalidate();
    },
    onError: (err: Error) => {
      toast.error(toastError(err, '状态更新失败'));
      void invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (keyId: number) => deleteApiKey(keyId),
    onSuccess: () => {
      toast.success('API Key 已删除');
      setDeletingKey(null);
      void invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = window.setTimeout(() => setCopied(false), 2000);
      toast.success('已复制到剪贴板');
    } catch {
      toast.error('复制失败，请手动选中文本复制');
    }
  };

  const handleCreate = () => {
    if (createMutation.isPending) return;
    createMutation.mutate(nameInput.trim() || 'default');
  };

  return (
    <div className="admin-page-stage space-y-4">
      <AdminPageHeader
        kicker="外部接入"
        title="API Key"
        description="外部软件用 sk-agenticos-* 调用本平台的 OpenAI 兼容网关，可直接使用本地智能体的工具与知识库。"
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void keysQuery.refetch()}
              disabled={keysQuery.isFetching}
            >
              {keysQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setNameInput('');
                setCreateOpen(true);
              }}
            >
              <Plus size={14} />
              新建 Key
            </Button>
          </>
        }
      />

      {keysQuery.isError ? (
        <ErrorBanner
          message={
            (keysQuery.error instanceof Error ? keysQuery.error.message : '') ||
            'API Key 列表加载失败'
          }
        />
      ) : null}

      {/* 接入说明：新用户第一次进来默认展开，已有 Key 时收起避免占屏 */}
      <AdminPanel>
        <button
          type="button"
          onClick={() => setGuideOpen((prev) => !prev)}
          aria-expanded={guideOpen}
          className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left transition-colors hover:bg-[var(--surface-2)] focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:outline-none focus-visible:ring-inset"
        >
          <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
            <Terminal size={15} className="shrink-0 text-[var(--muted-foreground)]" />
            如何接入
          </span>
          <ChevronDown
            size={16}
            className={cn(
              'shrink-0 text-[var(--muted-foreground)] transition-transform',
              guideOpen && 'rotate-180',
            )}
          />
        </button>

        {guideOpen ? (
          <div className="space-y-3 border-t border-[var(--border-subtle)] px-5 py-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Base URL</Label>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2.5 py-1.5 font-mono text-xs text-[var(--foreground)]">
                  {GATEWAY_BASE_URL}
                </code>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => void handleCopy(GATEWAY_BASE_URL)}
                  title="复制 Base URL"
                  aria-label="复制 Base URL"
                >
                  <Copy size={13} />
                </Button>
              </div>
            </div>

            <p className="text-xs leading-5 text-[var(--muted-foreground)]">
              把 Base URL 和刚创建的 Key 填进客户端即可。`model` 填智能体的 slug —— 先{' '}
              <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 font-mono">
                GET {GATEWAY_BASE_URL}/models
              </code>{' '}
              查看当前账号可用的列表。网关只会路由到本地智能体，不代理任何外部模型。
            </p>

            <div className="space-y-1.5">
              <Label className="text-xs">cURL 示例</Label>
              <pre className="overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3 font-mono text-[11px] leading-5 text-[var(--foreground)]">{`curl ${GATEWAY_BASE_URL}/chat/completions \\
  -H "Authorization: Bearer sk-agenticos-…" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"general","messages":[{"role":"user","content":"你好"}]}'`}</pre>
            </div>

            <p className="flex items-start gap-1.5 text-[11px] leading-5 text-[var(--muted-foreground)]">
              <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-500" />
              <span>
                通过网关发起的调用<strong className="font-semibold">不经过人工审批</strong>
                ，工具会按智能体配置自动执行。请只把 Key 交给可信软件，并按需在智能体上收紧工具权限。
              </span>
            </p>
          </div>
        ) : null}
      </AdminPanel>

      {/* 列表 */}
      {keysQuery.isLoading ? (
        <AdminPanel className="p-5">
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-11 w-full" />
            ))}
          </div>
        </AdminPanel>
      ) : keys.length === 0 ? (
        <AdminPanel className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)]">
            <KeyRound size={18} className="text-[var(--muted-foreground)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--foreground)]">还没有 API Key</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              创建一个后，就能在 Cursor、Cherry Studio、Dify 等客户端里直接调用本平台智能体。
            </p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => setCreateOpen(true)}>
            <Plus size={14} />
            创建第一个 Key
          </Button>
        </AdminPanel>
      ) : (
        <AdminPanel className="overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--muted-foreground)]">
                <th className="px-5 py-3 font-semibold">名称</th>
                <th className="px-3 py-3 font-semibold">Key</th>
                <th className="px-3 py-3 font-semibold">启用</th>
                <th className="px-3 py-3 font-semibold">最近使用</th>
                <th className="px-3 py-3 font-semibold">创建时间</th>
                <th className="px-5 py-3 text-right font-semibold">操作</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-[var(--border-subtle)] last:border-0 transition-colors hover:bg-[var(--surface-2)]"
                >
                  <td className="px-5 py-3">
                    <p className="font-medium text-[var(--foreground)]">{item.name}</p>
                    <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                      {item.owner_name ?? '—'}
                      {item.owner_email ? ` · ${item.owner_email}` : ''}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    <code className="font-mono text-xs text-[var(--muted-foreground)]">
                      {item.key_masked}
                    </code>
                  </td>
                  <td className="px-3 py-3">
                    <Switch
                      size="sm"
                      checked={item.enabled}
                      disabled={
                        toggleMutation.isPending && toggleMutation.variables?.id === item.id
                      }
                      onCheckedChange={(next) =>
                        toggleMutation.mutate({ id: item.id, enabled: next })
                      }
                      aria-label={`${item.enabled ? '停用' : '启用'} ${item.name}`}
                    />
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--muted-foreground)]">
                    {formatTime(item.last_used_at)}
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--muted-foreground)]">
                    {formatTime(item.created_at)}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-rose-500 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/10"
                      onClick={() => setDeletingKey(item)}
                      title={`删除 ${item.name}`}
                      aria-label={`删除 ${item.name}`}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AdminPanel>
      )}

      {/* 新建：输入名称 */}
      <Dialog
        open={createOpen}
        onOpenChange={(next) => {
          setCreateOpen(next);
          if (!next) setNameInput('');
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新建 API Key</DialogTitle>
            <DialogDescription>
              给这个 Key 起个名字，方便日后辨认用途（例如「本地 Cursor」）。
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              handleCreate();
            }}
            className="space-y-3"
          >
            <div className="space-y-1.5">
              <Label htmlFor="api-key-name">名称</Label>
              <Input
                id="api-key-name"
                autoFocus
                maxLength={64}
                placeholder="例如：本地 Cursor"
                value={nameInput}
                onChange={(event) => setNameInput(event.target.value)}
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateOpen(false)}
                disabled={createMutation.isPending}
              >
                取消
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    创建中
                  </>
                ) : (
                  '创建'
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 创建成功：显示明文（仅此一次） */}
      <Dialog
        open={createdKey !== null}
        onOpenChange={(next) => {
          if (!next) {
            setCreatedKey(null);
            setCopied(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Key 已创建</DialogTitle>
            <DialogDescription>
              复制并妥善保存。出于安全考虑，
              <strong className="font-semibold text-[var(--foreground)]">
                关闭后无法再次查看完整 Key
              </strong>
              ，只能看到前缀。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">完整 Key</Label>
              <div className="flex items-start gap-2">
                <code className="min-w-0 flex-1 break-all rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5 font-mono text-xs leading-5 text-[var(--foreground)]">
                  {createdKey?.key}
                </code>
                <Button
                  variant="outline"
                  size="icon"
                  className="shrink-0"
                  onClick={() => createdKey && void handleCopy(createdKey.key)}
                  title="复制 Key"
                  aria-label="复制 Key"
                >
                  {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
                </Button>
              </div>
            </div>

            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5 text-[11px] leading-5 text-[var(--muted-foreground)]">
              客户端填写：Base URL
              <code className="mx-1 rounded bg-[var(--surface-1)] px-1 font-mono">
                {GATEWAY_BASE_URL}
              </code>
              ，API Key 填上面这串。model 用智能体 slug。
            </div>
          </div>

          <DialogFooter>
            <Button
              onClick={() => {
                setCreatedKey(null);
                setCopied(false);
              }}
            >
              我已保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除二次确认 */}
      <AlertDialog open={deletingKey !== null} onOpenChange={(next) => !next && setDeletingKey(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{deletingKey?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后使用该 Key 的客户端会立即失效（返回 401），且无法恢复。如果只是暂时想停用，把开关关掉即可。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingKey) deleteMutation.mutate(deletingKey.id);
              }}
            >
              {deleteMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
