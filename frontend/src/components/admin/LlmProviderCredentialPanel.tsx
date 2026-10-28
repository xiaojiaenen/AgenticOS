/**
 * 企业网关的账号池面板。
 *
 * 一个提供商可以挂多个账号：企业网关普遍按账号限配额，全压在一个号上会被
 * 限流甚至锁定。所以这一屏的核心不是「配一个账号密码」，而是回答：
 *
 *   1. **池里有几个号、哪个能用** —— 状态 + 剩余有效期 + 连续失败次数；
 *   2. **流量怎么分** —— 按 priority 升序、同级内最久未用优先；
 *   3. **某个号坏了怎么办** —— 单独重登、单独贴 Cookie、单独停用/删除。
 *
 * 密码与 Cookie 永不回显：输入框始终为空，留空表示「不修改」。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertTriangle,
  Cookie,
  Loader2,
  LogIn,
  Plus,
  Power,
  Trash2,
} from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { StatusPill, type StatusTone } from './shared';
import {
  createProviderAccount,
  deleteProviderAccount,
  listProviderAccounts,
  loginProvider,
  saveAccountCookie,
  updateProviderAccount,
  type CredentialStatus,
  type LlmProvider,
} from '@/services/llmProviderService';
import { toastError } from '../../lib/errors';

const STATUS_META: Record<CredentialStatus['status'], { label: string; tone: StatusTone }> = {
  pending: { label: '未登录', tone: 'inactive' },
  active: { label: '可用', tone: 'active' },
  expired: { label: '已失效', tone: 'warning' },
  failed: { label: '登录失败', tone: 'warning' },
  disabled: { label: '已停用', tone: 'inactive' },
};

function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 剩余有效期：判断「还能不能撑到下一次续期」的唯一依据 */
function formatRemaining(expireAt: string | null): string {
  if (!expireAt) return '未记录';
  const ms = new Date(expireAt).getTime() - Date.now();
  if (Number.isNaN(ms)) return '未记录';
  if (ms <= 0) return '已过期';
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 24) return `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`;
  if (hours >= 1) return `${hours} 小时`;
  return `${Math.max(1, Math.floor(ms / 60_000))} 分钟`;
}

export function LlmProviderCredentialPanel({ provider }: { provider: LlmProvider }) {
  const queryClient = useQueryClient();
  const [openCookieFor, setOpenCookieFor] = useState<number | null>(null);
  const [cookie, setCookie] = useState('');
  const [expireAt, setExpireAt] = useState('');
  const [draft, setDraft] = useState({ label: '', username: '', password: '', priority: '100' });

  const accountsQuery = useQuery({
    queryKey: ['admin', 'llm-provider-accounts', provider.id],
    queryFn: () => listProviderAccounts(provider.id),
  });

  const accounts = accountsQuery.data?.items ?? [];

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['admin', 'llm-provider-accounts', provider.id],
    });
    void queryClient.invalidateQueries({ queryKey: ['admin', 'llm-providers'] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      createProviderAccount(provider.id, {
        label: draft.label.trim(),
        username: draft.username.trim(),
        password: draft.password || undefined,
        priority: Number(draft.priority) || 100,
      }),
    onSuccess: () => {
      toast.success('账号已加入池');
      setDraft({ label: '', username: '', password: '', priority: '100' });
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '新增账号失败')),
  });

  const loginMutation = useMutation({
    mutationFn: (accountId: number) => loginProvider(provider.id, accountId),
    onSuccess: (result) => {
      if (result.success) toast.success(result.message || '自动登录成功');
      else toast.error(result.message || '自动登录失败');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '自动登录失败')),
  });

  const cookieMutation = useMutation({
    mutationFn: (accountId: number) =>
      saveAccountCookie(provider.id, accountId, cookie.trim(), expireAt || undefined),
    onSuccess: () => {
      toast.success('Cookie 已保存');
      setCookie('');
      setExpireAt('');
      setOpenCookieFor(null);
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '保存 Cookie 失败')),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ accountId, disabled }: { accountId: number; disabled: boolean }) =>
      updateProviderAccount(provider.id, accountId, { disabled }),
    onSuccess: (_, vars) => {
      toast.success(vars.disabled ? '已停用，不再参与轮换' : '已启用');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '更新失败')),
  });

  const deleteMutation = useMutation({
    mutationFn: (accountId: number) => deleteProviderAccount(provider.id, accountId),
    onSuccess: () => {
      toast.success('账号已删除');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const busy =
    createMutation.isPending ||
    loginMutation.isPending ||
    cookieMutation.isPending ||
    toggleMutation.isPending ||
    deleteMutation.isPending;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-[var(--foreground)]">账号池</span>
        {accountsQuery.isLoading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--muted-foreground)]" />
        ) : (
          <StatusPill tone={accounts.length > 0 ? 'info' : 'inactive'}>
            {accounts.length} 个账号
          </StatusPill>
        )}
        <span className="text-xs font-medium text-[var(--muted-foreground)]">
          {accountsQuery.data?.rotation_policy ?? ''}
        </span>
      </div>

      {accounts.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3.5 py-4 text-xs font-medium text-[var(--muted-foreground)]">
          还没有账号。先在下面添加一个企业账号，再点「登录」获取会话；也可以直接粘贴浏览器里
          的 Cookie 应急。
        </p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => {
            const meta = STATUS_META[account.status];
            const cookieOpen = openCookieFor === account.id;
            return (
              <div
                key={account.id}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--foreground)]">
                    {account.label || account.username || `账号 #${account.id}`}
                  </span>
                  <StatusPill tone={meta.tone}>{meta.label}</StatusPill>
                  <StatusPill tone="info">优先级 {account.priority}</StatusPill>
                  {account.has_password ? <StatusPill tone="info">已存密码</StatusPill> : null}
                  {account.has_cookie ? <StatusPill tone="info">已存 Cookie</StatusPill> : null}
                  {account.excluded_from_rotation ? (
                    <StatusPill tone="warning">已退出轮换</StatusPill>
                  ) : null}
                </div>

                <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs font-medium text-[var(--muted-foreground)] sm:grid-cols-2 lg:grid-cols-4">
                  <div className="flex gap-1.5">
                    <dt>剩余</dt>
                    <dd className="font-semibold text-[var(--foreground)]">
                      {formatRemaining(account.expire_at)}
                    </dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>上次使用</dt>
                    <dd className="text-[var(--foreground)]">{formatTime(account.last_used_at)}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>上次登录</dt>
                    <dd className="text-[var(--foreground)]">{formatTime(account.last_login_at)}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>连续失败</dt>
                    <dd className="text-[var(--foreground)]">{account.failure_count} 次</dd>
                  </div>
                </dl>

                {account.last_error ? (
                  <p className="mt-2 flex items-start gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 break-words">{account.last_error}</span>
                  </p>
                ) : null}

                <div className="mt-2.5 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => loginMutation.mutate(account.id)}
                    disabled={busy || !account.has_password}
                    title={account.has_password ? undefined : '先补录密码'}
                  >
                    {loginMutation.isPending && loginMutation.variables === account.id ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <LogIn className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    登录
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setOpenCookieFor(cookieOpen ? null : account.id);
                      setCookie('');
                      setExpireAt('');
                    }}
                  >
                    <Cookie className="mr-1.5 h-3.5 w-3.5" />
                    贴 Cookie
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      toggleMutation.mutate({ accountId: account.id, disabled: !account.disabled })
                    }
                    disabled={busy}
                  >
                    <Power className="mr-1.5 h-3.5 w-3.5" />
                    {account.disabled ? '启用' : '停用'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-600 hover:text-red-700 dark:text-red-400"
                    onClick={() => deleteMutation.mutate(account.id)}
                    disabled={busy}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>

                {cookieOpen ? (
                  <div className="mt-3 space-y-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
                    <p className="text-xs font-medium text-[var(--muted-foreground)]">
                      从浏览器开发者工具复制
                      <code className="mx-1 rounded bg-[var(--surface-2)] px-1 py-0.5 text-[11px]">
                        Cookie
                      </code>
                      请求头整段填入。自动登录失效（上游改版 / 验证码 / SSO 多次跳转）时的兜底。
                    </p>
                    <textarea
                      value={cookie}
                      onChange={(e) => setCookie(e.target.value)}
                      rows={3}
                      placeholder="SESSION=...; cookie=...; 其它=..."
                      className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 font-mono text-xs text-[var(--foreground)] outline-none focus-visible:border-[var(--ring)]"
                    />
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="grid gap-1.5">
                        <Label htmlFor={`expire-${account.id}`}>
                          过期时间（留空按默认 TTL 估算）
                        </Label>
                        <Input
                          id={`expire-${account.id}`}
                          type="datetime-local"
                          value={expireAt}
                          onChange={(e) => setExpireAt(e.target.value)}
                          className="w-56"
                        />
                      </div>
                      <Button
                        size="sm"
                        onClick={() => cookieMutation.mutate(account.id)}
                        disabled={busy || !cookie.trim()}
                      >
                        {cookieMutation.isPending ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Cookie className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        保存 Cookie
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div className="space-y-2.5 rounded-lg border border-[var(--border-subtle)] p-3.5">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">添加账号</p>
          <p className="text-xs font-medium text-[var(--muted-foreground)]">
            账号密码只用于自动登录，加密存储且接口不回显。优先级小的先被选中，默认 100。
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="grid gap-1.5">
            <Label htmlFor="acc-label">标签</Label>
            <Input
              id="acc-label"
              value={draft.label}
              placeholder="运营号-01"
              onChange={(e) => setDraft((prev) => ({ ...prev, label: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="acc-username">账号</Label>
            <Input
              id="acc-username"
              value={draft.username}
              placeholder="域账号或邮箱"
              onChange={(e) => setDraft((prev) => ({ ...prev, username: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="acc-password">密码</Label>
            <Input
              id="acc-password"
              type="password"
              autoComplete="new-password"
              value={draft.password}
              placeholder="用于自动登录"
              onChange={(e) => setDraft((prev) => ({ ...prev, password: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="acc-priority">优先级</Label>
            <Input
              id="acc-priority"
              value={draft.priority}
              onChange={(e) => setDraft((prev) => ({ ...prev, priority: e.target.value }))}
            />
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => createMutation.mutate()}
          disabled={busy || !draft.username.trim()}
        >
          {createMutation.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="mr-1.5 h-3.5 w-3.5" />
          )}
          加入账号池
        </Button>
      </div>
    </div>
  );
}
