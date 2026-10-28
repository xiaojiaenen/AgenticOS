/**
 * 系统设置：LDAP 认证配置。
 *
 * 版式（2026-10 改版）：原来是一列卡片从上往下排 —— 总开关、服务器、服务账号、
 * 用户目录、用户策略、邮箱、连接测试，七张卡叠在一起，改一个字段要滚两屏。
 * 现在改成：
 *   - 顶部一条**状态带**（开关 + 保存 + 未保存标记），常驻可见；
 *   - 主体**双栏**：左栏「连接与凭据」，右栏「目录与策略 / 邮箱」用 Tab 切换，
 *     两栏在同一屏内，改完一处不用找另一处；
 *   - 底部「连接测试」常驻，分阶段显示失败在哪一步。
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
  ShieldCheck,
  Users,
  XCircle,
} from 'lucide-react';
import { AdminPageHeader, AdminPanel, ErrorBanner, SectionHeading, StatusPill } from './shared';
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
  type LdapTestStage,
} from '@/services/settingsService';
import { cn } from '@/lib/utils';
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

const STAGE_LABELS: Record<string, string> = {
  server: '服务器可达',
  bind: '服务账号绑定',
  filter: '用户过滤器',
  user: '账号登录',
};

/** 带标题、说明的输入行 */
function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('grid gap-1', className)}>
      <Label htmlFor={htmlFor} className="text-xs font-semibold text-[var(--foreground)]">
        {label}
      </Label>
      {children}
      {hint ? (
        <p className="text-[11px] leading-4 text-[var(--muted-foreground)]">{hint}</p>
      ) : null}
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
      <div className="min-w-0">
        <p className="text-xs font-semibold text-[var(--foreground)]">{label}</p>
        {hint ? (
          <p className="mt-0.5 text-[11px] leading-4 text-[var(--muted-foreground)]">{hint}</p>
        ) : null}
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

/** 分阶段测试结果 */
function TestStages({ stages }: { stages?: LdapTestStage[] }) {
  if (!stages || stages.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1">
      {stages.map((stage, index) => (
        <li key={`${stage.stage}-${index}`} className="flex flex-wrap items-baseline gap-1.5 text-[11px]">
          <span className={stage.ok ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-400'}>
            {stage.ok ? '✓' : '✕'}
          </span>
          <span className="font-semibold text-[var(--foreground)]">
            {STAGE_LABELS[stage.stage] ?? stage.stage}
          </span>
          <span className="text-[var(--muted-foreground)]">
            {stage.ok
              ? stage.stage === 'server'
                ? `${stage.url ?? ''}${stage.tls ? ' · 已加密' : ' · 未加密'}`
                : stage.stage === 'bind'
                  ? `已绑定 ${stage.dn ?? ''}`
                  : stage.stage === 'filter'
                    ? `命中 ${stage.sample_entries ?? 0} 条样例`
                    : stage.stage === 'user'
                      ? `${stage.username ?? ''}${stage.email ? ` · ${stage.email}` : ''}`
                      : '通过'
              : stage.message ?? '失败'}
          </span>
          {typeof stage.elapsed_ms === 'number' ? (
            <span className="text-[var(--muted-foreground)] opacity-70">{stage.elapsed_ms}ms</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export const SystemSettings = () => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<LdapConfigInput>(EMPTY_FORM);
  const [testResult, setTestResult] = useState<LdapTestResult | null>(null);
  const [probeUser, setProbeUser] = useState('');
  const [probePassword, setProbePassword] = useState('');
  const [showProbe, setShowProbe] = useState(false);

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
    mutationFn: (input: { config: LdapConfigInput; probe?: { username?: string; password?: string } }) =>
      testLdapConnection(input.config, input.probe),
    onSuccess: (result) => {
      setTestResult(result);
      if (result.ok) toast.success('连接测试成功');
      else toast.error(result.message || '连接测试失败');
    },
    onError: (err: Error) => toast.error(toastError(err, '连接测试请求失败')),
  });

  const loading = ldapQuery.isLoading;

  const runTest = () => {
    testMutation.mutate({
      config: form,
      probe: showProbe && probeUser.trim() ? { username: probeUser.trim(), password: probePassword } : undefined,
    });
  };

  return (
    <div className="space-y-3">
      <AdminPageHeader
        kicker="系统设置"
        title="LDAP 认证"
        description="直连 LDAP/AD 校验身份。配置存在数据库里（ldap.*），绑定密码加密保存；保存前就能用当前表单值试连。"
      />

      {ldapQuery.isError ? (
        <ErrorBanner
          message={(ldapQuery.error as Error).message || '加载 LDAP 配置失败'}
          onRetry={() => void ldapQuery.refetch()}
        />
      ) : null}

      {/* 状态带：开关、状态、保存 —— 常驻可见，不用滚到底部才能保存 */}
      <AdminPanel>
        <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]">
              <Server size={15} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-semibold text-[var(--foreground)]">LDAP 认证</span>
                <StatusPill tone={form.enabled ? 'active' : 'inactive'}>
                  {form.enabled ? '已启用' : '已禁用'}
                </StatusPill>
                {dirty ? <StatusPill tone="warning">有未保存修改</StatusPill> : null}
                {ldapQuery.data?.bind_password_set ? (
                  <StatusPill tone="info">绑定密码已设置</StatusPill>
                ) : (
                  <StatusPill tone="warning">绑定密码未设置</StatusPill>
                )}
              </div>
              <p className="mt-0.5 text-[11px] leading-4 text-[var(--muted-foreground)]">
                {form.enabled
                  ? '用户通过 LDAP 用户名 + 密码登录，本地密码登录与注册自动关闭'
                  : '仅使用本地密码登录；打开右侧开关后由 LDAP 服务器校验身份'}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Switch
              checked={form.enabled}
              onCheckedChange={(next) => patch({ enabled: next })}
              aria-label="LDAP 认证开关"
            />
            {dirty ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1.5"
                onClick={() => {
                  if (ldapQuery.data) {
                    userEditedRef.current = false;
                    setForm(toForm(ldapQuery.data));
                    setTestResult(null);
                  }
                }}
              >
                <RotateCcw size={13} />
                还原
              </Button>
            ) : null}
            <Button
              size="sm"
              className="h-8 gap-1.5"
              onClick={() => saveMutation.mutate(form)}
              disabled={!dirty || saveMutation.isPending || !portsValid}
              title={!dirty ? '暂无修改' : !portsValid ? '端口必须是 1-65535 的整数' : undefined}
            >
              {saveMutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Save size={13} />
              )}
              保存配置
            </Button>
          </div>
        </div>
      </AdminPanel>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-64 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      ) : (
        /* 双栏：左边连接与凭据，右边目录与策略。两栏同屏，改完一处不用来回滚。 */
        <div className="grid gap-3 lg:grid-cols-2">
          {/* ── 左栏：服务器 + 服务账号 ─────────────────────────────── */}
          <div className="space-y-3">
            <AdminPanel>
              <SectionHeading
                title="服务器连接"
                description="AD 通常 ldaps://dc.corp.com:636；OpenLDAP 可 ldap://host:389 + STARTTLS"
                actions={<Plug size={13} className="text-[var(--muted-foreground)]" />}
              />
              <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
                <Field
                  label="服务器地址"
                  htmlFor="ldap-server-url"
                  hint="含协议与端口"
                  className="sm:col-span-2"
                >
                  <Input
                    id="ldap-server-url"
                    value={form.server_url}
                    placeholder="ldaps://dc.corp.com:636"
                    onChange={(e) => patch({ server_url: e.target.value })}
                    className="h-9 font-mono text-xs"
                  />
                </Field>
                <div className="sm:col-span-2">
                  <ToggleRow
                    label="STARTTLS"
                    hint="ldap:// 明文连接上升级 TLS（ldaps:// 无需开启）"
                    checked={form.start_tls}
                    onCheckedChange={(next) => patch({ start_tls: next })}
                  />
                </div>
              </div>
            </AdminPanel>

            <AdminPanel>
              <SectionHeading
                title="服务账号（只读）"
                description="用于搜索用户目录；密码加密存储，界面不回显"
                actions={<Lock size={13} className="text-[var(--muted-foreground)]" />}
              />
              <div className="grid gap-3 px-4 py-3">
                <Field label="绑定账号 DN" htmlFor="ldap-bind-dn" hint="完整 DN，不是登录名">
                  <Input
                    id="ldap-bind-dn"
                    value={form.bind_dn}
                    placeholder="cn=svc-ldap,ou=Service,dc=corp,dc=com"
                    onChange={(e) => patch({ bind_dn: e.target.value })}
                    className="h-9 font-mono text-xs"
                  />
                </Field>
                <Field
                  label="绑定账号密码"
                  htmlFor="ldap-bind-password"
                  hint={
                    ldapQuery.data?.bind_password_set
                      ? '已设置 —— 留空表示不修改'
                      : '尚未设置 —— 需要先填才能测试'
                  }
                >
                  <Input
                    id="ldap-bind-password"
                    type="password"
                    value={form.bind_password}
                    placeholder={ldapQuery.data?.bind_password_set ? '••••••••（不修改）' : '输入密码'}
                    autoComplete="new-password"
                    onChange={(e) => patch({ bind_password: e.target.value })}
                    className="h-9"
                  />
                </Field>
              </div>
            </AdminPanel>
          </div>

          {/* ── 右栏：目录与策略 / 邮箱 ─────────────────────────────── */}
          <AdminPanel>
            <Tabs defaultValue="directory" className="w-full">
              <div className="border-b border-[var(--border-subtle)] px-3 pt-2">
                <TabsList className="bg-transparent p-0">
                  <TabsTrigger value="directory" className="gap-1.5 text-xs">
                    <Users className="h-3.5 w-3.5" />
                    目录与策略
                  </TabsTrigger>
                  <TabsTrigger value="email" className="gap-1.5 text-xs">
                    <Mail className="h-3.5 w-3.5" />
                    邮箱
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="directory" className="m-0">
                <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
                  <Field
                    label="用户搜索基线 DN"
                    htmlFor="ldap-base-dn"
                    hint="如 dc=corp,dc=com"
                    className="sm:col-span-2"
                  >
                    <Input
                      id="ldap-base-dn"
                      value={form.base_dn}
                      placeholder="dc=corp,dc=com"
                      onChange={(e) => patch({ base_dn: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field
                    label="用户过滤器"
                    htmlFor="ldap-user-filter"
                    hint="{username} 为占位符（自动转义）"
                    className="sm:col-span-2"
                  >
                    <Input
                      id="ldap-user-filter"
                      value={form.user_filter}
                      placeholder="(sAMAccountName={username})"
                      onChange={(e) => patch({ user_filter: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="用户名字段" htmlFor="ldap-attr-username" hint="AD: sAMAccountName / uid">
                    <Input
                      id="ldap-attr-username"
                      value={form.attr_username}
                      onChange={(e) => patch({ attr_username: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="邮箱字段" htmlFor="ldap-attr-email" hint="通常为 mail">
                    <Input
                      id="ldap-attr-email"
                      value={form.attr_email}
                      onChange={(e) => patch({ attr_email: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="显示名字段" htmlFor="ldap-attr-name" hint="AD: displayName / cn">
                    <Input
                      id="ldap-attr-name"
                      value={form.attr_name}
                      onChange={(e) => patch({ attr_name: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <div className="sm:col-span-2 border-t border-[var(--border-subtle)] pt-2">
                    <ToggleRow
                      label="首次登录自动建号"
                      hint="关闭后仅已存在的 LDAP 用户可登录（白名单模式）"
                      checked={form.auto_create_users}
                      onCheckedChange={(next) => patch({ auto_create_users: next })}
                    />
                    <div className="mt-2 flex items-center gap-4 text-xs">
                      <span className="text-[var(--muted-foreground)]">自动建号角色</span>
                      {(['user', 'admin'] as const).map((role) => (
                        <label key={role} className="flex cursor-pointer items-center gap-1.5">
                          <input
                            type="radio"
                            name="ldap-default-role"
                            value={role}
                            checked={form.default_role === role}
                            onChange={() => patch({ default_role: role })}
                            className="h-3.5 w-3.5 accent-[var(--foreground)]"
                          />
                          <span className="text-[var(--foreground)]">
                            {role === 'user' ? '普通用户' : '管理员'}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="email" className="m-0">
                <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <ToggleRow
                      label="登录时自动配置邮箱凭据"
                      hint="LDAP 登录成功后自动写入 IMAP/SMTP 凭据，用户无需手填"
                      checked={form.email_auto_configure}
                      onCheckedChange={(next) => patch({ email_auto_configure: next })}
                    />
                  </div>
                  <Field
                    label="邮箱域名"
                    htmlFor="ldap-email-domain"
                    hint="用户名为工号时用于补全邮箱"
                    className="sm:col-span-2"
                  >
                    <Input
                      id="ldap-email-domain"
                      value={form.email_domain}
                      placeholder="corp.com"
                      onChange={(e) => patch({ email_domain: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="IMAP 主机" htmlFor="ldap-imap-host">
                    <Input
                      id="ldap-imap-host"
                      value={form.imap_host}
                      placeholder="mail.corp.com"
                      onChange={(e) => patch({ imap_host: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="IMAP 端口" htmlFor="ldap-imap-port" hint="1-65535">
                    <Input
                      id="ldap-imap-port"
                      type="number"
                      value={form.imap_port}
                      onChange={(e) =>
                        patch({
                          imap_port: e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
                        })
                      }
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="SMTP 主机" htmlFor="ldap-smtp-host">
                    <Input
                      id="ldap-smtp-host"
                      value={form.smtp_host}
                      placeholder="mail.corp.com"
                      onChange={(e) => patch({ smtp_host: e.target.value })}
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                  <Field label="SMTP 端口" htmlFor="ldap-smtp-port" hint="1-65535">
                    <Input
                      id="ldap-smtp-port"
                      type="number"
                      value={form.smtp_port}
                      onChange={(e) =>
                        patch({
                          smtp_port: e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
                        })
                      }
                      className="h-9 font-mono text-xs"
                    />
                  </Field>
                </div>
              </TabsContent>
            </Tabs>
          </AdminPanel>
        </div>
      )}

      {/* ── 连接测试：常驻在底部，用当前表单值（含未保存修改）───────── */}
      {!loading ? (
        <AdminPanel>
          <SectionHeading
            title="连接测试"
            description="用当前表单值验证：服务器可达 → 服务账号可绑定 → 用户过滤器可执行"
            actions={
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={() => setShowProbe((prev) => !prev)}
                  aria-expanded={showProbe}
                >
                  <ShieldCheck size={13} />
                  {showProbe ? '收起账号验证' : '顺带验证一个账号'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={runTest}
                  disabled={testMutation.isPending}
                >
                  {testMutation.isPending ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Plug size={13} />
                  )}
                  测试连接
                </Button>
              </>
            }
          />

          {showProbe ? (
            <div className="grid gap-2 border-b border-[var(--border-subtle)] bg-[var(--surface-2)]/60 px-4 py-2.5 sm:grid-cols-2">
              <Field
                label="测试账号（用户名）"
                htmlFor="ldap-probe-user"
                hint="用登录名，不是邮箱；密码只用于本次测试，不保存"
              >
                <Input
                  id="ldap-probe-user"
                  value={probeUser}
                  placeholder="zhangsan"
                  onChange={(e) => setProbeUser(e.target.value)}
                  className="h-9 font-mono text-xs"
                  autoComplete="off"
                />
              </Field>
              <Field label="测试账号密码" htmlFor="ldap-probe-password">
                <Input
                  id="ldap-probe-password"
                  type="password"
                  value={probePassword}
                  placeholder="仅本次测试"
                  onChange={(e) => setProbePassword(e.target.value)}
                  className="h-9"
                  autoComplete="new-password"
                />
              </Field>
            </div>
          ) : null}

          <div className="px-4 py-3">
            {testResult ? (
              <div
                className={cn(
                  'rounded-lg border px-3.5 py-2.5 text-xs',
                  testResult.ok
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-200'
                    : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200',
                )}
              >
                <div className="flex items-start gap-2">
                  {testResult.ok ? (
                    <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                  ) : (
                    <XCircle size={14} className="mt-0.5 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold">{testResult.message}</p>
                    {testResult.hint ? (
                      <p className="mt-1 flex items-start gap-1 opacity-90">
                        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                        <span>{testResult.hint}</span>
                      </p>
                    ) : null}
                    <TestStages stages={testResult.stages} />
                    {testResult.ok ? (
                      <p className="mt-1 text-[11px] opacity-75">
                        {testResult.tls ? '传输加密：是' : '传输加密：否（建议开启 SSL/STARTTLS）'}
                        {testResult.server_info?.vendor
                          ? ` · 服务器：${testResult.server_info.vendor}${
                              testResult.server_info.version ? ` ${testResult.server_info.version}` : ''
                            }`
                          : ''}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-xs text-[var(--muted-foreground)]">
                还没测试过。配置改完点「测试连接」—— 它会逐步告诉你卡在哪一层：
                服务器不可达、服务账号绑不上、过滤器写错，还是某个账号登不进。
              </p>
            )}
          </div>
        </AdminPanel>
      ) : null}
    </div>
  );
};
