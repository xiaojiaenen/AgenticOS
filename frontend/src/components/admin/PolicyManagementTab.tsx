/**
 * 权限管理 · 策略。
 *
 * `p` 规则 = 角色在某域下对某资源的动作权限；`g` 规则 = 用户与角色的绑定。
 * 两者字段语义统一为 sub / dom / obj / act，方便互相参照。
 *
 * 2026-10 改版：所有字段都从「手写标识」改为「从目录里选」。
 * 以前的编辑器要求填 `kb:12`、`user:3` 这种内部标识 —— 管理员根本不知道
 * 某个知识库的 id 是几，只能去数据库里翻，于是这个页面事实上不可用。
 * 现在后端 `/permissions/catalog` 把标识和名字一起返回，这里只做选择；
 * 同时保留「高级模式」让人仍可手填（迁移/批量场景需要）。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Info,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Switch } from '@/components/shadcn/switch';
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
import { AdminPanel, AdminToolbar, ErrorBanner, SectionHeading } from './shared';
import { Pagination } from './Pagination';
import {
  createPolicy,
  deletePolicy,
  getPermissionCatalog,
  getUserRoles,
  listPolicies,
  listRoles,
  type CatalogResource,
  type CatalogSubject,
  type PermissionCatalog,
  type Policy,
  type PolicyType,
  type UserRoleInfo,
} from '@/services/permissionService';
import { cn } from '@/lib/utils';
import { toastError } from '../../lib/errors';

const POLICIES_KEY = ['admin', 'permissions', 'policies'] as const;
const CATALOG_KEY = ['admin', 'permissions', 'catalog'] as const;
const PAGE_SIZE = 20;

export function PolicyManagementTab() {
  const queryClient = useQueryClient();
  const [ptype, setPtype] = React.useState<PolicyType>('p');
  const [adding, setAdding] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Policy | null>(null);
  const [roleLookup, setRoleLookup] = React.useState(false);
  const [filter, setFilter] = React.useState('');
  const [page, setPage] = React.useState(1);

  const policiesQuery = useQuery({
    queryKey: [...POLICIES_KEY, ptype],
    queryFn: () => listPolicies(ptype),
  });
  const rolesQuery = useQuery({ queryKey: ['admin', 'permissions', 'roles'], queryFn: listRoles });
  const catalogQuery = useQuery({ queryKey: CATALOG_KEY, queryFn: getPermissionCatalog });

  const policies = policiesQuery.data ?? [];

  // 名称映射：把 sub / obj 里的标识翻成人话，表格里不再出现裸 id
  const subjectLabel = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of catalogQuery.data?.subjects ?? []) map.set(item.sub, item.label);
    for (const role of rolesQuery.data ?? []) map.set(role.slug, role.name);
    return map;
  }, [catalogQuery.data, rolesQuery.data]);

  const resourceLabel = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of catalogQuery.data?.resources ?? []) map.set(item.obj, item.label);
    return map;
  }, [catalogQuery.data]);

  const visible = React.useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    if (!keyword) return policies;
    return policies.filter((policy) =>
      [policy.sub, policy.obj, policy.act, subjectLabel.get(policy.sub) ?? '', resourceLabel.get(policy.obj) ?? '']
        .join(' ')
        .toLowerCase()
        .includes(keyword),
    );
  }, [policies, filter, subjectLabel, resourceLabel]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = visible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const removeMutation = useMutation({
    mutationFn: (policy: Policy) => deletePolicy(policy),
    onSuccess: () => {
      toast.success('策略已撤销');
      queryClient.invalidateQueries({ queryKey: POLICIES_KEY });
    },
    onError: (err) => toast.error(toastError(err, '撤销策略失败')),
  });

  const roleName = (slug: string) => subjectLabel.get(slug) ?? slug;

  return (
    <div className="space-y-3">
      <AdminToolbar>
        <div className="inline-flex rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-0.5">
          {[
            { key: 'p' as PolicyType, label: '权限策略', hint: '角色 → 资源' },
            { key: 'g' as PolicyType, label: '角色绑定', hint: '用户 → 角色' },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => {
                setPtype(tab.key);
                setPage(1);
              }}
              aria-pressed={ptype === tab.key}
              className={cn(
                'cursor-pointer rounded px-3 py-1 text-xs font-semibold transition-colors',
                ptype === tab.key
                  ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-xs'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
              title={tab.hint}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search
            size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
          />
          <Input
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setPage(1);
            }}
            placeholder="搜索角色 / 资源"
            aria-label="搜索策略"
            className="h-8 w-56 pl-7 text-xs"
          />
        </div>

        <Button size="sm" className="h-8 gap-1.5" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5" />
          新增{ptype === 'p' ? '策略' : '绑定'}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-8 gap-1.5"
          onClick={() => setRoleLookup(true)}
        >
          <Users className="h-3.5 w-3.5" />
          查看用户角色
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto h-8 gap-1.5"
          onClick={() => {
            void policiesQuery.refetch();
            void catalogQuery.refetch();
          }}
          disabled={policiesQuery.isFetching}
        >
          <RefreshCw className={cn('h-3.5 w-3.5', policiesQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </AdminToolbar>

      {policiesQuery.isError && (
        <ErrorBanner
          message={toastError(policiesQuery.error, '策略加载失败')}
          onRetry={() => void policiesQuery.refetch()}
        />
      )}

      <AdminPanel>
        <SectionHeading
          title={ptype === 'p' ? `权限策略 · ${visible.length}` : `角色绑定 · ${visible.length}`}
          description={
            ptype === 'p'
              ? '角色对某个资源能做什么。资源与动作都从下拉里选，不需要记内部标识。'
              : '把用户挂到角色上。一个用户可以有多个角色，权限取并集。'
          }
          actions={
            <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
              域统一为 global（部门已下线）
            </span>
          }
        />

        {policiesQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-9 w-full" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-sm font-medium text-[var(--foreground)]">
              {filter
                ? '没有匹配的策略'
                : ptype === 'p'
                  ? '还没有任何权限策略'
                  : '还没有任何角色绑定'}
            </p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              {filter ? '换个关键词试试' : ptype === 'p' ? '新增一条，从下拉里选角色和资源' : '把用户挂到角色上即可'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-left text-[11px] uppercase tracking-wide text-[var(--muted-foreground)]">
                <tr>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '角色' : '用户'}</th>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '资源' : '角色'}</th>
                  <th className="px-4 py-2 font-semibold">{ptype === 'p' ? '动作' : '域'}</th>
                  <th className="px-4 py-2 font-semibold">标识</th>
                  <th className="w-14 px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {pageItems.map((policy, index) => (
                  <tr
                    key={`${policy.ptype}-${policy.sub}-${policy.dom}-${policy.obj}-${policy.act}-${index}`}
                    className="transition-colors hover:bg-[var(--surface-2)]/70"
                  >
                    <td className="px-4 py-2 font-medium text-[var(--foreground)]">
                      {ptype === 'p' ? roleName(policy.sub) : subjectLabel.get(policy.sub) ?? policy.sub}
                    </td>
                    <td className="px-4 py-2 text-[var(--foreground)]">
                      {ptype === 'p'
                        ? resourceLabel.get(policy.obj) ?? policy.obj
                        : roleName(policy.obj)}
                    </td>
                    <td className="px-4 py-2">
                      {ptype === 'p' ? (
                        <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                          {policy.act}
                        </span>
                      ) : (
                        <span className="font-mono text-[11px] text-[var(--muted-foreground)]">
                          {policy.dom}
                        </span>
                      )}
                    </td>
                    <td className="max-w-[280px] truncate px-4 py-2 font-mono text-[11px] text-[var(--muted-foreground)]">
                      {ptype === 'p' ? `${policy.sub} → ${policy.obj}` : `${policy.sub} → ${policy.obj}`}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className="h-7 w-7 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-500/10"
                        onClick={() => setDeleting(policy)}
                        title="撤销"
                        aria-label="撤销这条规则"
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

        {!policiesQuery.isLoading && visible.length > 0 ? (
          <Pagination
            currentPage={safePage}
            totalPages={totalPages}
            onPageChange={setPage}
            totalLabel={`共 ${visible.length} 条`}
          />
        ) : null}
      </AdminPanel>

      {adding && (
        <PolicyEditorDialog
          defaultType={ptype}
          roles={rolesQuery.data ?? []}
          catalog={catalogQuery.data}
          onClose={() => setAdding(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: POLICIES_KEY })}
        />
      )}
      {roleLookup && <UserRoleLookupDialog catalog={catalogQuery.data} onClose={() => setRoleLookup(false)} />}

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              撤销这条{deleting?.ptype === 'g' ? '角色绑定' : '权限策略'}？
            </AlertDialogTitle>
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

/** 带搜索的选择器：资源/主体可能有上百条，纯下拉不可用 */
function SearchSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  emptyHint,
}: {
  id: string;
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string; hint?: string }[];
  placeholder: string;
  emptyHint: string;
}) {
  const [keyword, setKeyword] = React.useState('');
  const filtered = React.useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    if (!needle) return options.slice(0, 200);
    return options
      .filter((option) => `${option.label} ${option.value}`.toLowerCase().includes(needle))
      .slice(0, 200);
  }, [options, keyword]);

  if (options.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
        {emptyHint}
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      {options.length > 12 ? (
        <Input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="输入关键词过滤"
          className="h-8 text-xs"
          aria-label="过滤选项"
        />
      ) : null}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 text-sm text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
      >
        <option value="">{placeholder}</option>
        {filtered.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
            {option.hint ? ` · ${option.hint}` : ''}
          </option>
        ))}
      </select>
    </div>
  );
}

function PolicyEditorDialog({
  defaultType,
  roles,
  catalog,
  onClose,
  onSaved,
}: {
  defaultType: PolicyType;
  roles: { slug: string; name: string }[];
  catalog: PermissionCatalog | undefined;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [ptype, setPtype] = React.useState<PolicyType>(defaultType);
  const [advanced, setAdvanced] = React.useState(false);
  const [sub, setSub] = React.useState('');
  const [obj, setObj] = React.useState('');
  const [act, setAct] = React.useState('read');
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const roleOptions = (catalog?.subjects ?? [])
    .filter((item) => item.kind === 'role')
    .map((item) => ({ value: item.sub, label: item.label, hint: item.sub }));
  const userOptions = (catalog?.subjects ?? [])
    .filter((item) => item.kind === 'user')
    .map((item) => ({ value: item.sub, label: item.label, hint: item.description }));

  // 资源选项分两组：功能级（推荐，绑定「能做什么」）在前，实例级（逐条控制）在后。
  // 用 optgroup 表达分组，让管理员一眼看出「授权说的是能力，不是某个对象」。
  const featureOptions = (catalog?.resources ?? [])
    .filter((item: CatalogResource) => item.kind === 'feature')
    .map((item: CatalogResource) => ({
      value: item.obj,
      label: item.label,
      hint: item.obj,
    }));
  const instanceOptions = (catalog?.resources ?? [])
    .filter((item: CatalogResource) => item.kind !== 'feature')
    .map((item: CatalogResource) => ({
      value: item.obj,
      label: item.label,
      hint: item.obj,
    }));
  const resourceOptions = [...featureOptions, ...instanceOptions];
  const actionOptions = (catalog?.actions ?? []).map((item) => ({
    value: item.value,
    label: item.label,
  }));

  // 默认选中第一个可选项：不给默认值的话，用户要自己点两次才能开始
  React.useEffect(() => {
    if (ptype === 'p') {
      if (!sub && roleOptions.length > 0) setSub(roleOptions[0].value);
      if (!obj && resourceOptions.length > 0) setObj(resourceOptions[0].value);
    } else {
      if (!sub && userOptions.length > 0) setSub(userOptions[0].value);
      if (!obj && roleOptions.length > 0) setObj(roleOptions[0].value);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ptype, catalog]);

  const submit = async () => {
    if (!sub.trim() || !obj.trim()) {
      setError(ptype === 'p' ? '请选择角色与资源' : '请选择用户与角色');
      return;
    }
    if (ptype === 'g' && !/^user:\d+$/.test(sub.trim())) {
      setError('用户标识格式应为 user:<用户ID>；请从下拉里选择用户');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createPolicy({
        ptype,
        sub: sub.trim(),
        dom: catalog?.domain ?? '*',
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新增{ptype === 'p' ? '权限策略' : '角色绑定'}</DialogTitle>
          <DialogDescription>
            {ptype === 'p'
              ? '选一个角色、一个资源和允许的动作，保存后对下一次鉴权立即生效。'
              : '选一个用户和一个角色，保存后该用户立即获得这个角色的全部策略。'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {error && <ErrorBanner message={error} />}

          <div className="space-y-1.5">
            <Label>类型</Label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { key: 'p' as PolicyType, label: '权限策略', hint: '角色 → 资源' },
                { key: 'g' as PolicyType, label: '角色绑定', hint: '用户 → 角色' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => {
                    setPtype(tab.key);
                    setSub('');
                    setObj('');
                  }}
                  aria-pressed={ptype === tab.key}
                  className={cn(
                    'cursor-pointer rounded-md border px-3 py-2 text-left transition-colors',
                    ptype === tab.key
                      ? 'border-[var(--foreground)] bg-[var(--surface-1)]'
                      : 'border-[var(--border-subtle)] hover:bg-[var(--surface-2)]',
                  )}
                >
                  <span className="block text-xs font-semibold text-[var(--foreground)]">
                    {tab.label}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-[var(--muted-foreground)]">
                    {tab.hint}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="policy-sub">{ptype === 'p' ? '角色' : '用户'}</Label>
            <SearchSelect
              id="policy-sub"
              value={sub}
              onChange={setSub}
              options={ptype === 'p' ? roleOptions : userOptions}
              placeholder={ptype === 'p' ? '选择一个角色' : '选择一个用户'}
              emptyHint={
                ptype === 'p'
                  ? '还没有角色，先去「角色」标签页建一个'
                  : '没有可选用户，先去「用户管理」里创建'
              }
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="policy-obj">{ptype === 'p' ? '授权对象' : '角色'}</Label>
            {ptype === 'p' ? (
              <p className="text-[11px] leading-4 text-[var(--muted-foreground)]">
                优先选<strong className="font-semibold text-[var(--foreground)]">功能</strong>
                （如「构建网站」）—— 它绑定的是能力，不会因为新增一个知识库/技能就要重新授权。
                只有在需要逐条控制某个具体对象时，才选下面的实例项。
              </p>
            ) : null}
            <SearchSelect
              id="policy-obj"
              value={obj}
              onChange={setObj}
              options={ptype === 'p' ? resourceOptions : roleOptions}
              placeholder={ptype === 'p' ? '选择一个资源' : '选择一个角色'}
              emptyHint={
                ptype === 'p' ? '没有可授权资源，先创建知识库或技能' : '还没有角色'
              }
            />
          </div>

          {ptype === 'p' && (
            <div className="space-y-1.5">
              <Label htmlFor="policy-act">动作</Label>
              <select
                id="policy-act"
                value={act}
                onChange={(event) => setAct(event.target.value)}
                className="h-9 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 text-sm text-[var(--foreground)]"
              >
                {actionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}（{option.value}）
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 高级模式：仍允许手写标识（迁移、通配、尚未出现在目录里的资源） */}
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)]/60 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-[var(--foreground)]">高级：手写标识</p>
                <p className="mt-0.5 text-[11px] leading-4 text-[var(--muted-foreground)]">
                  用于通配（<code className="font-mono">kb:*</code>）或目录里还没列出的资源。
                </p>
              </div>
              <Switch
                checked={advanced}
                onCheckedChange={setAdvanced}
                aria-label="切换手写标识模式"
              />
            </div>
            {advanced ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <Input
                  value={sub}
                  onChange={(event) => setSub(event.target.value)}
                  placeholder={ptype === 'p' ? '角色标识，如 kb_editor' : 'user:12'}
                  className="h-8 font-mono text-xs"
                  aria-label="主体标识"
                />
                <Input
                  value={obj}
                  onChange={(event) => setObj(event.target.value)}
                  placeholder={ptype === 'p' ? 'kb:* / kb:12' : '角色标识'}
                  className="h-8 font-mono text-xs"
                  aria-label="资源标识"
                />
              </div>
            ) : null}
          </div>
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

/** 输入用户，看这个人在 Casbin 里实际是什么主体、什么域、什么角色 */
function UserRoleLookupDialog({
  catalog,
  onClose,
}: {
  catalog: PermissionCatalog | undefined;
  onClose: () => void;
}) {
  const [userId, setUserId] = React.useState('');
  const [result, setResult] = React.useState<UserRoleInfo | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const users = (catalog?.subjects ?? []).filter((item: CatalogSubject) => item.kind === 'user');
  const roleName = (slug: string) =>
    (catalog?.subjects ?? []).find((item) => item.sub === slug)?.label ?? slug;

  const lookup = async (raw?: string) => {
    const id = Number(raw ?? userId);
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
          {users.length > 0 ? (
            <div className="space-y-1.5">
              <Label>直接选一个用户</Label>
              <select
                value=""
                onChange={(event) => {
                  const next = event.target.value;
                  if (!next) return;
                  const id = next.replace(/^user:/, '');
                  setUserId(id);
                  void lookup(id);
                }}
                className="h-9 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 text-sm text-[var(--foreground)]"
              >
                <option value="">选择用户（按邮箱）</option>
                {users.map((item) => (
                  <option key={item.sub} value={item.sub}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="flex gap-2">
            <Input
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && void lookup()}
              placeholder="或直接填用户 ID"
              inputMode="numeric"
              aria-label="用户 ID"
            />
            <Button onClick={() => void lookup()} disabled={loading}>
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
                    <span className="text-[var(--muted-foreground)]">无（仅 app_role 生效）</span>
                  ) : (
                    result.roles.map((role) => (
                      <span
                        key={role}
                        className="rounded-full bg-[var(--surface-1)] px-2 py-0.5 font-mono text-[var(--foreground)]"
                      >
                        {roleName(role)}
                      </span>
                    ))
                  )}
                </dd>
              </div>
            </dl>
          )}
          <p className="flex items-start gap-1.5 text-[11px] leading-4 text-[var(--muted-foreground)]">
            <Info size={12} className="mt-0.5 shrink-0" />
            <span>
              管理员（app_role=admin）不看策略表也全量放行；普通用户只看这里列出的 Casbin 角色。
              角色为空时该用户只能访问自己的资源。
            </span>
          </p>
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
