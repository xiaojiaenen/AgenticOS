/**
 * 权限管理 · 角色。
 * 角色是 Casbin 的主体（`p` 规则里的 sub），内置角色不可删除。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, RefreshCw, Shield, Trash2 } from 'lucide-react';
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
import { createRole, deleteRole, listRoles, type Role } from '@/services/permissionService';
import { cn } from '@/lib/utils';
import { toastError } from '../../lib/errors';

const ROLES_KEY = ['admin', 'permissions', 'roles'] as const;

export function RoleManagementTab() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Role | null>(null);

  const rolesQuery = useQuery({ queryKey: ROLES_KEY, queryFn: listRoles });
  const roles = rolesQuery.data ?? [];

  const removeMutation = useMutation({
    mutationFn: (roleId: number) => deleteRole(roleId),
    onSuccess: () => {
      toast.success('角色已删除');
      queryClient.invalidateQueries({ queryKey: ['admin', 'permissions'] });
    },
    onError: (err) => toast.error(toastError(err, '删除角色失败')),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          新建角色
        </Button>
        <Button size="sm" variant="ghost" onClick={() => rolesQuery.refetch()} disabled={rolesQuery.isFetching}>
          <RefreshCw className={cn('mr-1.5 h-4 w-4', rolesQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {rolesQuery.isError && (
        <ErrorBanner message={toastError(rolesQuery.error, '角色加载失败')} onRetry={() => void rolesQuery.refetch()} />
      )}

      <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]">
        {rolesQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : roles.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-[var(--muted-foreground)]">还没有角色</p>
        ) : (
          <ul className="divide-y divide-[var(--border-subtle)]">
            {roles.map((role) => (
              <li key={role.id} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]">
                  <Shield className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-[var(--foreground)]">{role.name}</span>
                    <code className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                      {role.slug}
                    </code>
                    {role.is_builtin && (
                      <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700">
                        内置
                      </span>
                    )}
                    {!role.is_active && (
                      <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                        已停用
                      </span>
                    )}
                  </div>
                  {role.description && (
                    <p className="mt-0.5 truncate text-xs text-[var(--muted-foreground)]">{role.description}</p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 shrink-0 px-2 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  disabled={role.is_builtin}
                  title={role.is_builtin ? '内置角色不可删除' : '删除角色'}
                  onClick={() => setDeleting(role)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {creating && <CreateRoleDialog onClose={() => setCreating(false)} />}

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除角色「{deleting?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              该角色的所有权限策略与成员绑定会一并失效。用户不会失去登录能力，但会退回无授权状态。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting) removeMutation.mutate(deleting.id);
                setDeleting(null);
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function CreateRoleDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = React.useState('');
  const [slug, setSlug] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const submit = async () => {
    if (!name.trim()) {
      setError('角色名称必填');
      return;
    }
    if (!/^[a-z][a-z0-9_]*$/.test(slug)) {
      setError('标识需以小写字母开头，只能含小写字母、数字和下划线');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createRole({ name: name.trim(), slug, description });
      toast.success('角色已创建');
      queryClient.invalidateQueries({ queryKey: ROLES_KEY });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建角色失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建角色</DialogTitle>
          <DialogDescription>角色建好后，在「策略」里给它分配资源权限。</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {error && <ErrorBanner message={error} />}
          <div className="space-y-1.5">
            <Label htmlFor="role-name">名称</Label>
            <Input
              id="role-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                // 未手动编辑过 slug 时，跟随名称生成一个合法默认值
                if (!slug || slug === slugify(name)) setSlug(slugify(e.target.value));
              }}
              placeholder="例如：知识库编辑"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role-slug">标识</Label>
            <Input
              id="role-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="kb_editor"
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role-desc">描述</Label>
            <Input
              id="role-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="选填"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 中文名转合法 slug；转不出来时留空，让用户自己填 */
function slugify(value: string): string {
  const ascii = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return /^[a-z]/.test(ascii) ? ascii : '';
}
