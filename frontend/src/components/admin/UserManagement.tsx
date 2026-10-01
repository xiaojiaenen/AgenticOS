/**
 * 用户管理：TanStack Query 数据层 + TanStack Table + react-hook-form/zod 表单
 * + shadcn Select/Dialog/AlertDialog。
 * 后端 API 不变（services/userService.ts）。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  Edit3,
  Loader2,
  Plus,
  Search,
  Trash2,
  User as UserIcon,
  UserCheck,
  UserX,
} from 'lucide-react';
import { DataTable } from './data-table';
import { Pagination } from './Pagination';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { formatApiDate } from '@/lib/datetime';
import { cn } from '@/lib/utils';
import {
  AdminUser,
  UserFormPayload,
  createUser,
  deleteUser,
  listUsers,
  updateUser,
  updateUserStatus,
} from '@/services/userService';
import { getStoredUser } from '@/services/authService';

const ITEMS_PER_PAGE = 12;

// ---------------------------------------------------------------------------
// zod schema（对齐后端 UserFormPayload）
// ---------------------------------------------------------------------------

const userFormSchema = z
  .object({
    email: z.string().min(1, '请填写邮箱').email('邮箱格式不正确'),
    name: z.string().min(1, '请填写名称'),
    password: z.string(),
    role: z.enum(['admin', 'user']),
    is_active: z.boolean(),
  })
  .refine((data) => data.password.length === 0 || data.password.length >= 6, {
    message: '密码至少 6 位',
    path: ['password'],
  });

type UserFormValues = z.infer<typeof userFormSchema>;

function roleLabel(role: string): string {
  return role === 'admin' ? '管理员' : '普通用户';
}

// ---------------------------------------------------------------------------
// 用户表单弹窗（创建 / 编辑共用）
// ---------------------------------------------------------------------------

function UserFormDialog({
  open,
  editingUser,
  onClose,
}: {
  open: boolean;
  editingUser: AdminUser | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = editingUser !== null;

  const form = useForm<UserFormValues>({
    resolver: zodResolver(userFormSchema),
    defaultValues: {
      email: '',
      name: '',
      password: '',
      role: 'user',
      is_active: true,
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        email: editingUser?.email ?? '',
        name: editingUser?.name ?? '',
        password: '',
        role: editingUser?.role === 'admin' ? 'admin' : 'user',
        is_active: editingUser?.is_active ?? true,
      });
    }
  }, [open, editingUser, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: UserFormValues) => {
      const payload: UserFormPayload = {
        email: values.email.trim(),
        name: values.name.trim(),
        role: values.role,
        is_active: values.is_active,
      };
      if (values.password) payload.password = values.password;
      return isEdit && editingUser
        ? updateUser(editingUser.id, payload)
        : createUser(payload);
    },
    onSuccess: () => {
      toast.success(isEdit ? '用户已更新' : '用户已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      onClose();
    },
    onError: (err: Error) => {
      toast.error(err.message || '保存用户失败');
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑用户' : '新增用户'}</DialogTitle>
          <DialogDescription>
            {isEdit ? '调整用户资料与角色权限' : '创建后台登录账号'}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => saveMutation.mutateAsync(values))}
          className="grid grid-cols-1 gap-4 md:grid-cols-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="user-name">名称</Label>
            <Input id="user-name" placeholder="例如：王小明" {...form.register('name')} />
            {form.formState.errors.name ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="user-email">邮箱</Label>
            <Input
              id="user-email"
              type="email"
              placeholder="name@example.com"
              {...form.register('email')}
            />
            {form.formState.errors.email ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.email.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="user-password">{isEdit ? '新密码' : '登录密码'}</Label>
            <Input
              id="user-password"
              type="password"
              placeholder={isEdit ? '留空则不修改' : '至少 6 位'}
              {...form.register('password')}
            />
            {form.formState.errors.password ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.password.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label>角色</Label>
            <Select
              value={form.watch('role')}
              onValueChange={(value) => form.setValue('role', value as UserFormValues['role'])}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择角色" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">普通用户</SelectItem>
                <SelectItem value="admin">管理员</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <label className="flex items-center gap-2.5 md:col-span-2">
            <Checkbox
              checked={form.watch('is_active')}
              onCheckedChange={(checked) => form.setValue('is_active', checked === true)}
            />
            <span className="text-sm font-medium text-zinc-700">
              账号启用（允许登录和使用系统）
            </span>
          </label>

          <DialogFooter className="md:col-span-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={saveMutation.isPending}
            >
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
              {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : null}
              保存
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const UserManagement = () => {
  const currentUser = getStoredUser();
  const queryClient = useQueryClient();

  const [currentPage, setCurrentPage] = React.useState(1);
  const [searchInput, setSearchInput] = React.useState('');
  const [searchQuery, setSearchQuery] = React.useState('');
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingUser, setEditingUser] = React.useState<AdminUser | null>(null);
  const [deletingUser, setDeletingUser] = React.useState<AdminUser | null>(null);

  // 180ms 防抖搜索
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(searchInput);
      setCurrentPage(1);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const usersQuery = useQuery({
    queryKey: ['admin', 'users', currentPage, searchQuery],
    queryFn: () =>
      listUsers({
        search: searchQuery,
        offset: (currentPage - 1) * ITEMS_PER_PAGE,
        limit: ITEMS_PER_PAGE,
      }),
    placeholderData: (prev) => prev,
  });

  const users = usersQuery.data?.items ?? [];
  const total = usersQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));

  const toggleStatusMutation = useMutation({
    mutationFn: ({ user, nextActive }: { user: AdminUser; nextActive: boolean }) =>
      updateUserStatus(user.id, nextActive),
    onSuccess: () => {
      toast.success('用户状态已更新');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (err: Error) => toast.error(err.message || '用户状态更新失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: (userId: number) => deleteUser(userId),
    onSuccess: () => {
      toast.success('用户已删除');
      setDeletingUser(null);
      if (users.length === 1 && currentPage > 1) {
        setCurrentPage((page) => page - 1);
      } else {
        void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      }
    },
    onError: (err: Error) => toast.error(err.message || '删除用户失败'),
  });

  const activeUsers = users.filter((user) => user.is_active).length;
  const adminUsers = users.filter((user) => user.role === 'admin').length;

  const columns = React.useMemo<ColumnDef<AdminUser, unknown>[]>(
    () => [
      {
        id: 'user',
        header: '用户',
        cell: ({ row }) => {
          const user = row.original;
          const isSelf = currentUser?.id === user.id;
          return (
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-semibold text-[var(--foreground)]">{user.name}</p>
                {isSelf ? (
                  <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                    当前账号
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 truncate text-xs font-medium text-[var(--muted-foreground)]">{user.email}</p>
            </div>
          );
        },
      },
      {
        accessorKey: 'role',
        header: '角色',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-700">{roleLabel(String(getValue()))}</span>
        ),
      },
      {
        accessorKey: 'is_active',
        header: '状态',
        cell: ({ getValue }) => {
          const active = getValue() === true;
          return (
            <span
              className={cn(
                'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                active
                  ? 'border-emerald-200/80 bg-emerald-50 text-emerald-700'
                  : 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
              )}
            >
              {active ? '正常' : '已禁用'}
            </span>
          );
        },
      },
      {
        accessorKey: 'created_at',
        header: '创建时间',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-600">
            {formatApiDate(String(getValue()))}
          </span>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const user = row.original;
          const isSelf = currentUser?.id === user.id;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditingUser(user);
                  setFormOpen(true);
                }}
                className="gap-1.5"
              >
                <Edit3 size={14} />
                编辑
              </Button>
              <Button
                variant={user.is_active ? 'destructive' : 'outline'}
                size="sm"
                onClick={() =>
                  toggleStatusMutation.mutate({ user, nextActive: !user.is_active })
                }
                disabled={toggleStatusMutation.isPending || (isSelf && user.is_active)}
                className="gap-1.5"
              >
                {user.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                {user.is_active ? '禁用' : '启用'}
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setDeletingUser(user)}
                disabled={isSelf}
                className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                title="删除用户"
              >
                <Trash2 size={15} />
              </Button>
            </div>
          );
        },
      },
    ],
    [currentUser, toggleStatusMutation],
  );

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="用户管理"
        title="账号与权限"
        actions={
          <>
            <KpiPill label="共" value={total} />
            <KpiPill label="启用" value={activeUsers} />
            <KpiPill label="管理员" value={adminUsers} />
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setEditingUser(null);
                setFormOpen(true);
              }}
            >
              <Plus size={14} />
              新增
            </Button>
          </>
        }
      />

      {usersQuery.isError ? (
        <ErrorBanner message={(usersQuery.error as Error).message || '用户加载失败'} />
      ) : null}

      <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        <div className="flex flex-col gap-2.5 border-b border-[var(--border-subtle)] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-indigo-600">
              用户目录
            </p>
            <h3 className="mt-1 text-base font-semibold tracking-tight text-[var(--foreground)]">
              按名称和邮箱检索
            </h3>
          </div>
          <div className="relative lg:w-[340px]">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
              size={16}
            />
            <Input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="搜索名称或邮箱"
              className="pl-9"
            />
          </div>
        </div>

        <DataTable
          columns={columns}
          data={users}
          isLoading={usersQuery.isLoading}
          skeletonRows={6}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--muted-foreground)] shadow-sm">
                <UserIcon size={20} />
              </div>
              <p className="text-sm font-semibold text-zinc-600">没有找到匹配的用户</p>
              <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
                换个关键词，或者直接创建新账号
              </p>
            </div>
          }
        />

        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={setCurrentPage}
          totalLabel={`共 ${total} 条`}
        />
      </section>

      <UserFormDialog
        open={formOpen}
        editingUser={editingUser}
        onClose={() => {
          setFormOpen(false);
          setEditingUser(null);
        }}
      />

      <AlertDialog
        open={deletingUser !== null}
        onOpenChange={(next) => !next && setDeletingUser(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除用户</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除{' '}
              <span className="font-semibold text-[var(--foreground)]">{deletingUser?.name}</span>
              ？删除后该账号将无法继续登录，所有关联数据将被清理。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingUser) deleteMutation.mutate(deletingUser.id);
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
};
