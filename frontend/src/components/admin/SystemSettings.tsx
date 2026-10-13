/**
 * 系统设置：LDAP 认证开关。
 * TanStack Query 数据层 + shadcn 组件。
 * 后端 API 不变（services/settingsService.ts）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Server } from 'lucide-react';
import { AdminPageHeader } from './shared';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Switch } from '@/components/shadcn/switch';
import { getLdapSetting, updateLdapSetting } from '@/services/settingsService';

export const SystemSettings = () => {
  const queryClient = useQueryClient();

  const ldapQuery = useQuery({
    queryKey: ['admin', 'settings', 'ldap'],
    queryFn: getLdapSetting,
  });

  const updateMutation = useMutation({
    mutationFn: (next: boolean) => updateLdapSetting(next),
    onSuccess: (result) => {
      toast.success(
        result.ldap_enabled
          ? 'LDAP 认证已开启，用户可使用工号登录'
          : 'LDAP 认证已关闭，仅本地用户可登录',
      );
      void queryClient.invalidateQueries({ queryKey: ['admin', 'settings', 'ldap'] });
    },
    onError: (err: Error) => toast.error(err.message || '保存设置失败'),
  });

  const ldapEnabled = ldapQuery.data?.ldap_enabled ?? false;

  return (
    <div className="space-y-5">
      <AdminPageHeader kicker="系统设置" title="系统配置" />

      {ldapQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
          {(ldapQuery.error as Error).message || '加载设置失败'}
        </div>
      ) : null}

      <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-100 text-zinc-700">
              <Server size={20} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-[var(--foreground)]">LDAP 认证</h3>
              <p className="mt-1 max-w-2xl text-sm font-medium leading-relaxed text-[var(--muted-foreground)]">
                启用后用户可通过工号 + LDAP 密码登录，自动禁用本地密码登录和注册功能。
                开启 <span className="font-semibold text-amber-600">LDAP_AUTO_CREATE_USERS=true</span>{' '}
                时首次登录将自动创建用户。
              </p>
              <div className="mt-2 flex items-center gap-2 text-xs font-medium text-[var(--muted-foreground)]">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    ldapEnabled ? 'bg-emerald-500' : 'bg-zinc-400'
                  }`}
                />
                {ldapEnabled ? '已启用 — LDAP 网关控制身份验证' : '已禁用 — 仅使用本地密码登录'}
              </div>
            </div>
          </div>

          {ldapQuery.isLoading ? (
            <Skeleton className="h-6 w-11 rounded-full" />
          ) : (
            <Switch
              checked={ldapEnabled}
              disabled={updateMutation.isPending}
              onCheckedChange={(next) => updateMutation.mutate(next)}
              aria-label="LDAP 认证开关"
            />
          )}
          {updateMutation.isPending ? (
            <Loader2 size={16} className="animate-spin text-[var(--muted-foreground)]" />
          ) : null}
        </div>
      </section>

      <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
        <div className="rounded-lg border border-[var(--border-subtle)] p-4 text-sm font-medium leading-relaxed text-[var(--muted-foreground)]">
          <p className="font-semibold text-zinc-700">注意：</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>切换 LDAP 状态后无需重启后端服务</li>
            <li>
              LDAP 网关地址、域名等高级配置仍需在{' '}
              <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-300">.env</code>{' '}
              文件中设置
            </li>
            <li>
              首次启用时，系统会从{' '}
              <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-300">.env</code>{' '}
              中的{' '}
              <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-300">
                LDAP_ENABLED
              </code>{' '}
              值同步初始状态
            </li>
          </ul>
        </div>
      </section>
    </div>
  );
};
