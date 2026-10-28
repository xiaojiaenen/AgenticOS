/**
 * 权限管理 · 策略。
 * `p` 规则 = 角色在某域下对某资源的动作权限；`g` 规则 = 用户与角色的绑定。
 * 两者字段语义统一为 sub / dom / obj / act，方便互相参照。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Info, Loader2, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
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
import { ErrorBanner } from './shared';
import {
  createPolicy,
  deletePolicy,
  getUserRoles,
  listPolicies,
  listRoles,
  type Policy,
  type PolicyType,
  type UserRoleInfo,
} from '@/services/permissionService';
import { cn } from '@/lib/utils';
import { toastError } from '../../lib/errors';

const POLICIES_KEY = ['admin', 'permissions', 'policies'] as const;

const ACTIONS = ['read', 'write', 'delete', 'admin', '*'] as const;

export function PolicyManagementTab() {
  const queryClient = useQueryClient();
  const [ptype, setPtype] = React.useState<PolicyType>('p');
  const [adding, setAdding] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Policy | null>(null);
  const [roleLookup, setRoleLookup] = React.useState(false);

  const policiesQuery = useQuery({
    queryKey: [...POLICIES_KEY, ptype],
    queryFn: () => listPolicies(ptype),
  });
  const rolesQuery = useQuery({ queryKey: ['admin', 'permissions', 'roles'], queryFn: listRoles });
  const policies = policiesQuery.data ?? [];

  const removeMutation = useMutation({
    mutationFn: (policy: Policy) => deletePolicy(policy),
    onSuccess: () => {
      toast.success('策略已撤销');
      queryClient.invalidateQueries({ queryKey: POLICIES_KEY });
    },
    onError: (err) => toast.error(toastError(err, '撤销策略失败')),
  });

  const roleName = (slug: string) => rolesQuery.data?.find((r) => r.slug === slug)?.name ?? slug;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-0.5">
          {[
            { key: 'p' as PolicyType, label: '权限策略' },
            { key: 'g' as PolicyType, label: '角色绑定' },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setPtype(tab.key)}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                ptype === tab.key
                  ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          新增
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setRoleLookup(true)}>
          <Search className="mr-1.5 h-4 w-4" />
          查看用户角色
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => policiesQuery.refetch()}
          disabled={policiesQuery.isFetching}
        >
          <RefreshCw className={cn('mr-1.5 h-4 w-4', policiesQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3.5 py-2.5 text-xs text-[var(--muted-foreground)]">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {ptype === 'p' ? (
          <span>
            主体填<strong className="text-[var(--foreground)]">角色标识</strong>，资源形如{' '}
            <code className="rounded bg-[var(--surface-1)] px-1">kb:12</code> 或通配{' '}
            <code className="rounded bg-[var(--surface-1)] px-1">kb:*</code>，域名固定填{' '}
            <code className="rounded bg-[var(--surface-1)] px-1">*</code>（部门下线后不再有域隔离）。
          </span>
        ) : (
          <span>
            主体填<strong className="text-[var(--foreground)]">用户标识</strong>（
            <code className="rounded bg-[var(--surface-1)] px-1">user:12</code>），角色填 role
            标识，域名固定填 <code className="rounded bg-[var(--surface-1)] px-1">*</code>。
          </span>
        )}
      </div>

      {policiesQuery.isError && (
        <ErrorBanner message={toastError(policiesQuery.error, '策略加载失败')} onRetry={() => void policiesQuery.refetch()} />
      )}

      <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]">
        {policiesQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : policies.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-[var(--muted-foreground)]">
            {ptype === 'p' ? '还没有任何权限策略' : '还没有任何角色绑定'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-left text-[11px] uppercase tracking-wide text-[var(--muted-foreground)]">
                <tr>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '角色' : '用户'}</th>
                  <th className="px-4 py-2 font-semibold">域</th>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '资源' : '角色'}</th>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '动作' : ''}</th>
                  <th className="w-16 px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {policies.map((policy, index) => (
                  <tr key={`${policy.ptype}-${policy.sub}-${policy.dom}-${policy.obj}-${policy.act}-${index}`}>
                    <td className="px-4 py-2 font-medium text-[var(--foreground)]">
                      {ptype === 'p' ? roleName(policy.sub) : policy.sub}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-[var(--muted-foreground)]">{policy.dom}</td>
                    <td className="px-4 py-2 font-mono text-xs text-[var(--foreground)]">
                      {ptype === 'p' ? policy.obj : roleName(policy.obj)}
                    </td>
                    <td className="px-4 py-2">
                      {ptype === 'p' && (
                        <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                          {policy.act}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        onClick={() => setDeleting(policy)}
                        title="撤销"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {adding && (
        <PolicyEditorDialog
          defaultType={ptype}
          roles={rolesQuery.data ?? []}
          onClose={() => setAdding(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: POLICIES_KEY })}
        />
      )}
      {roleLookup && <UserRoleLookupDialog onClose={() => setRoleLookup(false)} />}

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>撤销这条{deleting?.ptype === 'g' ? '角色绑定' : '权限策略'}？</AlertDialogTitle>
            <AlertDialogDescription>
              撤销后立即生效，相关用户可能失去对该资源的访问能力。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting) removeMutation.mutate(deleting);
                setDeleting(null);
              }}
            >
              撤销
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function PolicyEditorDialog({
  defaultType,
  roles,
  onClose,
  onSaved,
}: {
  defaultType: PolicyType;
  roles: { slug: string; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [ptype, setPtype] = React.useState<PolicyType>(defaultType);
  const [sub, setSub] = React.useState(defaultType === 'g' ? 'user:' : '');
  const [dom, setDom] = React.useState('*');
  const [obj, setObj] = React.useState(defaultType === 'p' ? 'kb:*' : (roles[0]?.slug ?? ''));
  const [act, setAct] = React.useState('read');
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async () => {
    if (!sub.trim() || !obj.trim()) {
      setError(ptype === 'p' ? '主体与资源必填' : '用户标识与角色必填');
      return;
    }
    if (ptype === 'g' && !/^user:\d+$/.test(sub.trim())) {
      setError('用户标识格式应为 user:<用户ID>');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createPolicy({
        ptype,
        sub: sub.trim(),
        dom: dom.trim() || '*',
        obj: obj.trim(),
        act: ptype === 'p' ? act : '-',
      });
      toast.success(ptype === 'p' ? '策略已生效' : '角色绑定已生效');
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新增{ptype === 'p' ? '权限策略' : '角色绑定'}</DialogTitle>
          <DialogDescription>保存后立即对该角色的下一次鉴权请求生效。</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {error && <ErrorBanner message={error} />}
          <div className="space-y-1.5">
            <Label>类型</Label>
            <div className="flex gap-2">
              {[
                { key: 'p' as PolicyType, label: '权限策略 p' },
                { key: 'g' as PolicyType, label: '角色绑定 g' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setPtype(tab.key)}
                  className={cn(
                    'flex-1 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors',
                    ptype === tab.key
                      ? 'border-[var(--foreground)] bg-[var(--surface-1)] text-[var(--foreground)]'
                      : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="policy-sub">{ptype === 'p' ? '角色标识' : '用户标识'}</Label>
            <Input
              id="policy-sub"
              value={sub}
              onChange={(e) => setSub(e.target.value)}
              placeholder={ptype === 'p' ? 'dept_admin' : 'user:12'}
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="policy-dom">域</Label>
            <Input
              id="policy-dom"
              value={dom}
              onChange={(e) => setDom(e.target.value)}
              placeholder="* 或 dept:3"
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="policy-obj">{ptype === 'p' ? '资源' : '角色'}</Label>
            {ptype === 'p' ? (
              <Input
                id="policy-obj"
                value={obj}
                onChange={(e) => setObj(e.target.value)}
                placeholder="kb:12 / kb:*"
                className="font-mono"
              />
            ) : (
              <select
                id="policy-obj"
                value={obj}
                onChange={(e) => setObj(e.target.value)}
                className="h-9 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 text-sm text-[var(--foreground)]"
              >
                {roles.length === 0 && <option value="">（请先创建角色）</option>}
                {roles.map((role) => (
                  <option key={role.slug} value={role.slug}>
                    {role.name}（{role.slug}）
                  </option>
                ))}
              </select>
            )}
          </div>
          {ptype === 'p' && (
            <div className="space-y-1.5">
              <Label htmlFor="policy-act">动作</Label>
              <select
                id="policy-act"
                value={act}
                onChange={(e) => setAct(e.target.value)}
                className="h-9 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 text-sm text-[var(--foreground)]"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 输入用户 ID，看这个人在 Casbin 里实际是什么主体、什么域、什么角色 */
function UserRoleLookupDialog({ onClose }: { onClose: () => void }) {
  const [userId, setUserId] = React.useState('');
  const [result, setResult] = React.useState<UserRoleInfo | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const lookup = async () => {
    const id = Number(userId);
    if (!Number.isInteger(id) || id <= 0) {
      setError('请输入有效的用户 ID');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await getUserRoles(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : '查询失败');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>查看用户角色</DialogTitle>
          <DialogDescription>用于确认某个用户的授权是否按预期生效。</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {error && <ErrorBanner message={error} />}
          <div className="flex gap-2">
            <Input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && lookup()}
              placeholder="用户 ID"
              inputMode="numeric"
              autoFocus
            />
            <Button onClick={lookup} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '查询'}
            </Button>
          </div>
          {result && (
            <dl className="space-y-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-[var(--muted-foreground)]">主体</dt>
                <dd className="font-mono text-[var(--foreground)]">{result.subject}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-[var(--muted-foreground)]">域</dt>
                <dd className="font-mono text-[var(--foreground)]">{result.domain}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-[var(--muted-foreground)]">应用角色</dt>
                <dd className="font-mono text-[var(--foreground)]">{result.app_role}</dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="shrink-0 text-[var(--muted-foreground)]">Casbin 角色</dt>
                <dd className="flex flex-wrap justify-end gap-1">
                  {result.roles.length === 0 ? (
                    <span className="text-[var(--muted-foreground)]">无</span>
                  ) : (
                    result.roles.map((r) => (
                      <span
                        key={r}
                        className="rounded-full bg-[var(--surface-1)] px-2 py-0.5 font-mono text-[var(--foreground)]"
                      >
                        {r}
                      </span>
                    ))
                  )}
                </dd>
              </div>
            </dl>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
