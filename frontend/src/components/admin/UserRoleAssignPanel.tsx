/**
 * 用户角色分配面板（角色创作与分配分离的「分配」半边）。
 *
 * 独立组件：用户管理页“分配角色”按钮打开、或角色页反向查看成员时使用。
 * 主角色不可取消；额外角色多选，保存后权限取并集。
 */
import { useCallback, useState } from 'react';
import { Check, Loader2, Search, UserCog } from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { toast } from 'sonner';
import { cn } from '../../lib/utils';

interface RoleOption { value: string; label: string; hint: string }
interface UserRolesInfo {
  user_id: number;
  primary_role: string;
  roles: string[];
  permissions: string[];
}

export function UserRoleAssignPanel({ roles }: { roles: RoleOption[] }) {
  const [query, setQuery] = useState('');
  const [info, setInfo] = useState<UserRolesInfo | null>(null);
  const [extra, setExtra] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const uid = Number(query.trim());
    if (!Number.isFinite(uid) || uid <= 0) {
      toast.error('请输入有效的用户 ID');
      return;
    }
    try {
      const data = await apiFetch<UserRolesInfo>(
        `/api/v1/permission-matrix/users/${uid}/roles`, {}, '加载用户角色失败',
      );
      setInfo(data);
      setExtra(data.roles.filter((r) => r !== data.primary_role));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '加载失败');
    }
  }, [query]);

  const save = async () => {
    if (!info) return;
    setSaving(true);
    try {
      await apiFetch(
        `/api/v1/permission-matrix/users/${info.user_id}/roles`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ roles: extra }) },
        '保存用户角色失败',
      );
      toast.success('用户角色已更新，权限将立即生效');
      setInfo(await apiFetch<UserRolesInfo>(
        `/api/v1/permission-matrix/users/${info.user_id}/roles`, {}, '刷新失败',
      ));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <UserCog size={16} className="text-[var(--ring)]" />
        <h3 className="text-sm font-semibold text-[var(--foreground)]">用户角色分配</h3>
        <span className="text-[11px] text-[var(--muted-foreground)]">额外角色与主角色叠加，权限取并集</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void load()}
            placeholder="输入用户 ID"
            className="w-44 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] py-1.5 pl-7 pr-2 text-[11px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
          />
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]"
        >
          查询
        </button>
      </div>
      {info && (
        <div className="mt-4 space-y-3 border-t border-[var(--border-subtle)] pt-3">
          <p className="text-[11px] text-[var(--muted-foreground)]">
            用户 #{info.user_id} · 主角色 <strong className="text-[var(--foreground)]">{info.primary_role}</strong> · 生效 {info.permissions.length} 项权限
          </p>
          <div className="flex flex-wrap gap-2">
            {roles.map((r) => {
              const isPrimary = r.value === info.primary_role;
              const checked = isPrimary || extra.includes(r.value);
              return (
                <label key={r.value} className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px]',
                  checked ? 'border-[var(--ring)] bg-[var(--surface-2)] text-[var(--foreground)]' : 'border-[var(--border-subtle)] text-[var(--muted-foreground)]',
                  isPrimary && 'cursor-not-allowed opacity-70',
                )}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={isPrimary || saving}
                    onChange={(e) => setExtra((prev) => e.target.checked ? [...prev, r.value] : prev.filter((x) => x !== r.value))}
                    className="accent-[var(--ring)]"
                  />
                  {r.label}{isPrimary && '（主角色）'}
                </label>
              );
            })}
          </div>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-[11px] font-semibold text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            保存用户角色
          </button>
        </div>
      )}
    </div>
  );
}
