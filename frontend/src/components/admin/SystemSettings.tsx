/**
 * 系统设置：LDAP 认证配置。
 * 服务器连接、服务账号、用户过滤器、属性映射、用户策略均在后台维护，
 * 支持保存前连接测试。TanStack Query 数据层 + shadcn 组件。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Lock,
  Mail,
  Plug,
  RotateCcw,
  Save,
  Server,
  Users,
  XCircle,
} from 'lucide-react';
import { AdminPageHeader, ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Switch } from '@/components/shadcn/switch';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/shadcn/tabs';
import {
  getLdapConfig,
  testLdapConnection,
  updateLdapConfig,
  type LdapConfig,
  type LdapConfigInput,
  type LdapTestResult,
} from '@/services/settingsService';
import { toastError } from '../../lib/errors';

/** 表单初始值（后端加载完成后覆盖） */
const EMPTY_FORM: LdapConfigInput = {
  enabled: false,
  server_url: '',
  start_tls: false,
  bind_dn: '',
  bind_password: '',
  base_dn: '',
  user_filter: '(sAMAccountName={username})',
  attr_username: 'sAMAccountName',
  attr_email: 'mail',
  attr_name: 'displayName',
  auto_create_users: true,
  default_role: 'user',
  email_domain: '',
  email_auto_configure: false,
  imap_host: '',
  imap_port: 993,
  smtp_host: '',
  smtp_port: 465,
};

const toForm = (config: LdapConfig): LdapConfigInput => ({
  ...config,
  bind_password: '', // 密码不回显；空 = 不修改
});

/** 带标题、说明的输入行 */
function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor} className="text-[var(--foreground)]">
        {label}
      </Label>
      {children}
      {hint ? <p className="text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

/** 开关行 */
function ToggleRow({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-1">
      <div>
        <p className="text-sm font-medium text-[var(--foreground)]">{label}</p>
        {hint ? <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
      </div>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-label={label}
      />
    </div>
  );
}

function SectionCard({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
          {icon}
        </div>
        <div>
          <h3 className="text-base font-semibold text-[var(--foreground)]">{title}</h3>
          <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">{description}</p>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export const SystemSettings = () => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<LdapConfigInput>(EMPTY_FORM);
  const [testResult, setTestResult] = useState<LdapTestResult | null>(null);

  const ldapQuery = useQuery({
    queryKey: ['admin', 'settings', 'ldap'],
    queryFn: getLdapConfig,
  });

  // 后端数据到达后同步表单。
  // 守卫 userEditedRef：保存成功后 invalidate 会再次触发本 effect，
  // 此前无脑 reset 会把用户新一轮未保存编辑覆盖掉。
  const userEditedRef = useRef(false);
  useEffect(() => {
    if (ldapQuery.data && !userEditedRef.current) {
      setForm(toForm(ldapQuery.data));
      setTestResult(null);
    }
  }, [ldapQuery.data]);

  const patch = (values: Partial<LdapConfigInput>) => {
    userEditedRef.current = true;
    setForm((prev) => ({ ...prev, ...values }));
    setTestResult(null);
  };

  // 端口合法性：1-65535 整数（空串 / NaN / 0 均视为非法）
  const portsValid =
    Number.isInteger(form.imap_port) && form.imap_port > 0 && form.imap_port <= 65535 &&
    Number.isInteger(form.smtp_port) && form.smtp_port > 0 && form.smtp_port <= 65535;

  const dirty = useMemo(() => {
    if (!ldapQuery.data) return false;
    const initial = toForm(ldapQuery.data);
    return JSON.stringify(initial) !== JSON.stringify(form);
  }, [form, ldapQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (config: LdapConfigInput) => updateLdapConfig(config),
    onSuccess: (result) => {
      toast.success(
        result.enabled ? '配置已保存，LDAP 认证已开启' : '配置已保存，LDAP 认证未启用',
      );
      // 允许后续 refetch 的最新值重新同步表单
      userEditedRef.current = false;
      void queryClient.invalidateQueries({ queryKey: ['admin', 'settings', 'ldap'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '保存配置失败')),
  });

  const testMutation = useMutation({
    mutationFn: (config: LdapConfigInput) => testLdapConnection(config),
    onSuccess: (result) => {
      setTestResult(result);
      if (result.ok) toast.success('连接测试成功');
      else toast.error(result.message || '连接测试失败');
    },
    onError: (err: Error) => toast.error(toastError(err, '连接测试请求失败')),
  });

  const loading = ldapQuery.isLoading;

  return (
    <div className="space-y-5">
      <AdminPageHeader kicker="系统设置" title="LDAP 认证" />

      {ldapQuery.isError ? (
        <ErrorBanner
          message={(ldapQuery.error as Error).message || '加载 LDAP 配置失败'}
        />
      ) : null}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : (
        <>
          {/* ── 总开关 + 保存 ─────────────────────────────────────────── */}
          <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  <Server size={20} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-[var(--foreground)]">LDAP 认证</h3>
                  <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--muted-foreground)]">
                    启用后用户通过 LDAP 用户名 + 密码登录，本地密码登录与注册自动关闭。
                    首次部署可用环境变量 <code className="rounded bg-zinc-900 px-1 py-0.5 text-xs text-zinc-300">LDAP_ENABLED</code> 引导开关，
                    完整配置以本页面为准。
                  </p>
                  <div className="mt-2 flex items-center gap-2 text-xs font-medium text-[var(--muted-foreground)]">
                    <span
                      className={`inline-block h-1.5 w-1.5 rounded-full ${
                        form.enabled ? 'bg-emerald-500' : 'bg-zinc-400'
                      }`}
                    />
                    {form.enabled ? '已启用 — LDAP 服务器校验身份' : '已禁用 — 仅使用本地密码登录'}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Switch
                  checked={form.enabled}
                  onCheckedChange={(next) => patch({ enabled: next })}
                  aria-label="LDAP 认证开关"
                />
                <Button
                  onClick={() => saveMutation.mutate(form)}
                  disabled={!dirty || saveMutation.isPending || !portsValid}
                  title={!dirty ? '暂无修改' : !portsValid ? '端口必须是 1-65535 的整数' : undefined}
                >
                  {saveMutation.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Save size={16} />
                  )}
                  保存配置
                </Button>
              </div>
            </div>
          </section>

          <Tabs defaultValue="connection" className="w-full">
           <TabsList>
            <TabsTrigger value="connection">连接</TabsTrigger>
            <TabsTrigger value="directory">目录与策略</TabsTrigger>
            <TabsTrigger value="email">邮箱</TabsTrigger>
           </TabsList>

           <TabsContent value="connection" className="space-y-5 pt-5">
          {/* ── 服务器连接 ────────────────────────────────────────────── */}
          <SectionCard
            icon={<Plug size={18} />}
            title="服务器连接"
            description="LDAP/AD 服务器地址与传输安全。AD 通常为 ldaps://dc.corp.com:636；OpenLDAP 可用 ldap://host:389 + STARTTLS。"
          >
            <Field
              label="服务器地址"
              htmlFor="ldap-server-url"
              hint="形如 ldaps://dc.corp.com:636 或 ldap://dc.corp.com:389"
            >
              <Input
                id="ldap-server-url"
                value={form.server_url}
                placeholder="ldaps://dc.corp.com:636"
                onChange={(e) => patch({ server_url: e.target.value })}
              />
            </Field>
            <div className="flex items-end pb-1">
              <ToggleRow
                label="STARTTLS"
                hint="ldap:// 明文连接上升级 TLS（ldaps:// 无需开启）"
                checked={form.start_tls}
                onCheckedChange={(next) => patch({ start_tls: next })}
              />
            </div>
          </SectionCard>

          {/* ── 服务账号 ──────────────────────────────────────────────── */}
          <SectionCard
            icon={<Lock size={18} />}
            title="服务账号（绑定 DN）"
            description="用于搜索用户目录的只读账号，密码加密存储。AD 示例：cn=svc-ldap,ou=Service,dc=corp,dc=com。"
          >
            <Field label="绑定账号 DN" htmlFor="ldap-bind-dn" hint="完整 DN，不是登录名">
              <Input
                id="ldap-bind-dn"
                value={form.bind_dn}
                placeholder="cn=svc-ldap,dc=corp,dc=com"
                onChange={(e) => patch({ bind_dn: e.target.value })}
              />
            </Field>
            <Field
              label="绑定账号密码"
              htmlFor="ldap-bind-password"
              hint={
                ldapQuery.data?.bind_password_set
                  ? '已设置 —— 留空表示不修改'
                  : '尚未设置 —— 保存前无法连接测试'
              }
            >
              <Input
                id="ldap-bind-password"
                type="password"
                value={form.bind_password}
                placeholder={ldapQuery.data?.bind_password_set ? '••••••••（不修改）' : '输入密码'}
                autoComplete="new-password"
                onChange={(e) => patch({ bind_password: e.target.value })}
              />
            </Field>
          </SectionCard>

           </TabsContent>

           <TabsContent value="directory" className="space-y-5 pt-5">
          {/* ── 用户目录 ──────────────────────────────────────────────── */}
          <SectionCard
            icon={<Users size={18} />}
            title="用户目录"
            description="用户搜索基线与属性映射。不同 IdP（AD / OpenLDAP）字段名不同，均可在此配置。"
          >
            <Field label="用户搜索基线 DN" htmlFor="ldap-base-dn" hint="如 dc=corp,dc=com">
              <Input
                id="ldap-base-dn"
                value={form.base_dn}
                placeholder="dc=corp,dc=com"
                onChange={(e) => patch({ base_dn: e.target.value })}
              />
            </Field>
            <Field
              label="用户过滤器"
              htmlFor="ldap-user-filter"
              hint="{username} 为占位符（自动转义）。AD: (sAMAccountName={username})；按邮箱: (mail={username})"
            >
              <Input
                id="ldap-user-filter"
                value={form.user_filter}
                placeholder="(sAMAccountName={username})"
                onChange={(e) => patch({ user_filter: e.target.value })}
              />
            </Field>
            <Field label="用户名字段" htmlFor="ldap-attr-username" hint="AD: sAMAccountName / uid">
              <Input
                id="ldap-attr-username"
                value={form.attr_username}
                onChange={(e) => patch({ attr_username: e.target.value })}
              />
            </Field>
            <Field label="邮箱字段" htmlFor="ldap-attr-email" hint="通常为 mail">
              <Input
                id="ldap-attr-email"
                value={form.attr_email}
                onChange={(e) => patch({ attr_email: e.target.value })}
              />
            </Field>
            <Field label="显示名字段" htmlFor="ldap-attr-name" hint="AD: displayName / cn">
              <Input
                id="ldap-attr-name"
                value={form.attr_name}
                onChange={(e) => patch({ attr_name: e.target.value })}
              />
            </Field>
          </SectionCard>

          {/* ── 用户策略 ──────────────────────────────────────────────── */}
          <SectionCard
            icon={<Users size={18} />}
            title="用户策略"
            description="首次登录的自动建号行为。"
          >
            <div className="sm:col-span-2 divide-y divide-[var(--border-subtle)]">
              <ToggleRow
                label="首次登录自动创建用户"
                hint="域账号密码验证通过即自动建号登录，无需管理员预先授权；关闭后仅已存在的 LDAP 用户可登录"
                checked={form.auto_create_users}
                onCheckedChange={(next) => patch({ auto_create_users: next })}
              />
            </div>
            <Field
              label="自动创建用户的默认角色"
              htmlFor="ldap-default-role"
              hint="系统中第一个用户始终为 admin（保证可管理）"
            >
              <div className="flex h-9 items-center gap-4">
                {(['user', 'admin'] as const).map((role) => (
                  <label key={role} className="flex items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="ldap-default-role"
                      value={role}
                      checked={form.default_role === role}
                      onChange={() => patch({ default_role: role })}
                      className="h-4 w-4 accent-[var(--primary,#3b82f6)]"
                    />
                    {role === 'user' ? '普通用户' : '管理员'}
                  </label>
                ))}
              </div>
            </Field>
          </SectionCard>

           </TabsContent>

           <TabsContent value="email" className="space-y-5 pt-5">
          {/* ── 邮箱自动配置 ──────────────────────────────────────────── */}
          <SectionCard
            icon={<Mail size={18} />}
            title="邮箱自动配置（可选）"
            description="开启后，用户登录成功即自动写入其 IMAP/SMTP 凭据，无需手动填写邮箱设置。"
          >
            <div className="sm:col-span-2">
              <ToggleRow
                label="登录时自动配置邮箱凭据"
                hint="需要配置下方 IMAP/SMTP 服务器与邮箱域名"
                checked={form.email_auto_configure}
                onCheckedChange={(next) => patch({ email_auto_configure: next })}
              />
            </div>
            <Field label="邮箱域名" htmlFor="ldap-email-domain" hint="如 corp.com（用户名为工号时补全邮箱）">
              <Input
                id="ldap-email-domain"
                value={form.email_domain}
                placeholder="corp.com"
                onChange={(e) => patch({ email_domain: e.target.value })}
              />
            </Field>
            <div className="hidden sm:block" />
            <Field label="IMAP 主机" htmlFor="ldap-imap-host">
              <Input
                id="ldap-imap-host"
                value={form.imap_host}
                placeholder="mail.corp.com"
                onChange={(e) => patch({ imap_host: e.target.value })}
              />
            </Field>
            <Field label="IMAP 端口" htmlFor="ldap-imap-port">
              <Input
                id="ldap-imap-port"
                type="number"
                value={form.imap_port}
                onChange={(e) => patch({ imap_port: e.target.value === '' ? ('' as unknown as number) : Number(e.target.value) })}
              />
            </Field>
            <Field label="SMTP 主机" htmlFor="ldap-smtp-host">
              <Input
                id="ldap-smtp-host"
                value={form.smtp_host}
                placeholder="mail.corp.com"
                onChange={(e) => patch({ smtp_host: e.target.value })}
              />
            </Field>
            <Field label="SMTP 端口" htmlFor="ldap-smtp-port">
              <Input
                id="ldap-smtp-port"
                type="number"
                value={form.smtp_port}
                onChange={(e) => patch({ smtp_port: e.target.value === '' ? ('' as unknown as number) : Number(e.target.value) })}
              />
            </Field>
          </SectionCard>
           </TabsContent>
          </Tabs>

          {/* ── 连接测试 ──────────────────────────────────────────────── */}
          <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-base font-semibold text-[var(--foreground)]">连接测试</h3>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  用当前表单配置（含未保存修改）验证服务器可达、服务账号可绑定、用户过滤器可执行。
                </p>
              </div>
              <div className="flex items-center gap-2">
                {dirty ? (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      if (ldapQuery.data) {
                        setForm(toForm(ldapQuery.data));
                        setTestResult(null);
                      }
                    }}
                  >
                    <RotateCcw size={16} />
                    还原
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  onClick={() => testMutation.mutate(form)}
                  disabled={testMutation.isPending}
                >
                  {testMutation.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Plug size={16} />
                  )}
                  测试连接
                </Button>
              </div>
            </div>

            {testResult ? (
              <div
                className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
                  testResult.ok
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200'
                    : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200'
                }`}
              >
                <div className="flex items-start gap-2">
                  {testResult.ok ? (
                    <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                  ) : (
                    <XCircle size={16} className="mt-0.5 shrink-0" />
                  )}
                  <div>
                    <p className="font-medium">{testResult.message}</p>
                    {testResult.hint ? (
                      <p className="mt-1 flex items-center gap-1 text-xs">
                        <AlertTriangle size={12} />
                        {testResult.hint}
                      </p>
                    ) : null}
                    {testResult.ok ? (
                      <p className="mt-1 text-xs opacity-80">
                        {testResult.tls ? '传输加密：是' : '传输加密：否（建议开启 SSL/STARTTLS）'}
                        {testResult.server_info?.vendor
                          ? ` · 服务器：${testResult.server_info.vendor}${
                              testResult.server_info.version ? ` ${testResult.server_info.version}` : ''
                            }`
                          : ''}
                        {typeof testResult.sample_entries === 'number'
                          ? ` · 探测样例：${testResult.sample_entries} 条`
                          : ''}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
};
