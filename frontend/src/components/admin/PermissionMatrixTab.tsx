/**
 * 权限树配置台（参考 Linear / Claude 设置页的克制风格）。
 *
 * - 左侧：角色列表（点选要编辑的角色），右侧：可折叠的三层权限树
 *   （分组 → 权限点），组级「全选/全不选」一次性批量保存（单次 PUT）。
 * - 角色创作与权限分配合一：本页只管「角色 → 权限」，用户分配角色在
 *   UserRoleAssignPanel（用户管理页复用）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check, ChevronDown, ChevronRight, Loader2, RotateCcw, Search, ShieldCheck,
} from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { updateStoredUser, getStoredUser } from '../../services/authTokenStore';
import { toast } from 'sonner';
import { cn } from '../../lib/utils';

interface PermissionPoint {
  key: string;
  label: string;
  description?: string;
}
interface PermissionGroup {
  key: string;
  label: string;
  points: PermissionPoint[];
}
interface MatrixRole {
  value: string;
  label: string;
  hint: string;
  is_builtin: boolean;
  permissions: string[];
  customized: boolean;
}

export function PermissionMatrixTab() {
  const [catalog, setCatalog] = useState<PermissionGroup[]>([]);
  const [roles, setRoles] = useState<MatrixRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>('admin');
  // 折叠状态：默认展开常用分组，其余折叠（降低认知负荷）
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cat, r] = await Promise.all([
        apiFetch<{ groups: PermissionGroup[]; total: number }>('/api/v1/permission-matrix/catalog', {}, '加载权限目录失败'),
        apiFetch<{ roles: MatrixRole[] }>('/api/v1/permission-matrix/roles', {}, '加载角色矩阵失败'),
      ]);
      setCatalog(cat.groups);
      setRoles(r.roles);
      const target = r.roles.find((x) => x.value === selectedRole) ?? r.roles[0];
      if (target) setSelectedRole(target.value);
      // 首次默认展开前 4 组
      setExpanded(new Set(cat.groups.slice(0, 4).map((g) => g.key)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []); // 首次加载

  useEffect(() => { void load(); }, [load]);

  const role = useMemo(
    () => roles.find((r) => r.value === selectedRole),
    [roles, selectedRole],
  );

  /** 一次性保存整份权限数组（组级全选/批量切换只发 1 次请求） */
  const savePermissions = async (next: string[], label: string) => {
    if (!role) return;
    setSaving(role.value);
    try {
      const res = await apiFetch<{ permissions: string[] }>(
        `/api/v1/permission-matrix/roles/${encodeURIComponent(role.value)}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ permissions: next }) },
        '保存权限失败',
      );
      setRoles((prev) => prev.map((r) =>
        r.value === role.value ? { ...r, permissions: res.permissions, customized: true } : r,
      ));
      // 若改的是当前用户自己的角色，刷新本地权限缓存
      const me = getStoredUser();
      if (me?.role === role.value) {
        const fresh = await apiFetch<{ permissions: string[]; capabilities: string[]; can_enter_admin: boolean }>(
          '/api/v1/permission-matrix/me', {}, '刷新权限失败',
        );
        if (me) updateStoredUser({ ...me, permissions: fresh.permissions, capabilities: fresh.capabilities, can_enter_admin: fresh.can_enter_admin });
      }
      toast.success(`${label}已保存`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(null);
    }
  };

  const togglePoint = (pointKey: string) => {
    if (!role) return;
    const next = role.permissions.includes(pointKey)
      ? role.permissions.filter((p) => p !== pointKey)
      : [...role.permissions, pointKey];
    void savePermissions(next, '权限');
  };

  const toggleGroup = (group: PermissionGroup) => {
    if (!role) return;
    const keys = group.points.map((p) => p.key);
    const allOn = keys.every((k) => role.permissions.includes(k));
    const next = allOn
      ? role.permissions.filter((p) => !keys.includes(p))
      : [...new Set([...role.permissions, ...keys])];
    void savePermissions(next, `「${group.label}」分组`);
  };

  const resetRole = async () => {
    if (!role) return;
    setSaving(role.value);
    try {
      const res = await apiFetch<{ permissions: string[] }>(
        `/api/v1/permission-matrix/roles/${encodeURIComponent(role.value)}/reset`,
        { method: 'POST' }, '重置失败',
      );
      setRoles((prev) => prev.map((r) =>
        r.value === role.value ? { ...r, permissions: res.permissions, customized: false } : r,
      ));
      toast.success(`已恢复「${role.label}」的默认权限`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '重置失败');
    } finally {
      setSaving(null);
    }
  };

  const visibleGroups = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.map((g) => ({
      ...g,
      points: g.points.filter((p) => p.key.toLowerCase().includes(q) || p.label.toLowerCase().includes(q)),
    })).filter((g) => g.points.length > 0);
  }, [catalog, search]);

  if (loading) {
    return <div className="flex items-center justify-center py-16 text-[13px] text-[var(--muted-foreground)]"><Loader2 className="mr-2 animate-spin" size={16} />加载权限树…</div>;
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
      {/* 左：角色列表（克制、清晰层级） */}
      <aside className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-2">
        <p className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">角色</p>
        <div className="space-y-0.5">
          {roles.map((r) => {
            const active = r.value === selectedRole;
            return (
              <button
                key={r.value}
                type="button"
                onClick={() => setSelectedRole(r.value)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors',
                  active
                    ? 'bg-[var(--surface-2)] font-medium text-[var(--foreground)]'
                    : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
                )}
              >
                <ShieldCheck size={14} className={cn('shrink-0', active && 'text-[var(--ring)]')} />
                <span className="min-w-0 flex-1 truncate">{r.label}</span>
                {r.customized && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--ring)]" />}
              </button>
            );
          })}
        </div>
      </aside>

      {/* 右：权限树 */}
      <section className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]">
        {/* 头部 */}
        <div className="flex flex-wrap items-center gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-[var(--foreground)]">{role?.label ?? '选择角色'}</h3>
            <p className="mt-0.5 truncate text-[11px] text-[var(--muted-foreground)]">
              {role?.hint ?? ''} · 已启用 {role?.permissions.length ?? 0} / {catalog.reduce((n, g) => n + g.points.length, 0)} 项
            </p>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索权限"
              className="w-40 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] py-1.5 pl-7 pr-2 text-[11px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
            />
          </div>
          {role?.customized && (
            <button
              type="button"
              onClick={() => void resetRole()}
              disabled={saving !== null}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-[11px] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              <RotateCcw size={12} /> 恢复默认
            </button>
          )}
        </div>

        {/* 权限树：分组可折叠 */}
        <div className="max-h-[60vh] space-y-1.5 overflow-y-auto p-3">
          {visibleGroups.map((group) => {
            const keys = group.points.map((p) => p.key);
            const onCount = keys.filter((k) => role?.permissions.includes(k)).length;
            const allOn = onCount === keys.length && keys.length > 0;
            const someOn = onCount > 0 && !allOn;
            const isOpen = expanded.has(group.key) || !!search.trim();
            return (
              <div key={group.key} className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
                {/* 组头：折叠 + 全选 */}
                <div className="flex items-center gap-2 bg-[var(--surface-2)] px-2.5 py-2">
                  <button
                    type="button"
                    onClick={() => setExpanded((prev) => {
                      const next = new Set(prev);
                      if (next.has(group.key)) next.delete(group.key); else next.add(group.key);
                      return next;
                    })}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    aria-expanded={isOpen}
                  >
                    {isOpen ? <ChevronDown size={14} className="shrink-0 text-[var(--muted-foreground)]" /> : <ChevronRight size={14} className="shrink-0 text-[var(--muted-foreground)]" />}
                    <span className="text-[12px] font-medium text-[var(--foreground)]">{group.label}</span>
                    <span className="text-[10px] text-[var(--muted-foreground)]">{onCount}/{keys.length}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleGroup(group)}
                    disabled={saving !== null}
                    title={allOn ? '取消全选' : '全选该分组'}
                    className={cn(
                      'flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors disabled:opacity-50',
                      allOn ? 'border-[var(--ring)] bg-[var(--ring)] text-white'
                        : someOn ? 'border-[var(--ring)] bg-[var(--ring)]/30' : 'border-[var(--border-medium)]',
                    )}
                  >
                    {allOn && <Check size={11} />}
                    {someOn && <span className="h-0.5 w-2 bg-white" />}
                  </button>
                </div>
                {/* 权限点 */}
                {isOpen && (
                  <div className="grid gap-px bg-[var(--border-subtle)] sm:grid-cols-2 xl:grid-cols-3">
                    {group.points.map((p) => {
                      const enabled = role?.permissions.includes(p.key) ?? false;
                      return (
                        <button
                          key={p.key}
                          type="button"
                          onClick={() => togglePoint(p.key)}
                          disabled={saving !== null}
                          className={cn(
                            'flex items-start gap-2 bg-[var(--surface-1)] px-3 py-2 text-left transition-colors hover:bg-[var(--surface-2)] disabled:opacity-60',
                          )}
                        >
                          <span className={cn(
                            'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                            enabled ? 'border-[var(--ring)] bg-[var(--ring)] text-white' : 'border-[var(--border-medium)]',
                          )}>
                            {enabled && <Check size={11} />}
                          </span>
                          <span className="min-w-0">
                            <span className="block text-[11px] font-medium text-[var(--foreground)]">{p.label}</span>
                            <span className="block truncate font-mono text-[9px] text-[var(--muted-foreground)]">{p.key}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {visibleGroups.length === 0 && (
            <div className="py-12 text-center text-[12px] text-[var(--muted-foreground)]">没有匹配的权限点</div>
          )}
        </div>
      </section>
    </div>
  );
}
