import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  CheckCircle2,
  Edit3,
  Loader2,
  Mail,
  Plus,
  Search,
  Shield,
  Trash2,
  User,
  UserCheck,
  UserX,
  X,
} from 'lucide-react';
import { Pagination } from './Pagination';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import {
  AdminUser,
  createUser,
  deleteUser,
  listUsers,
  updateUser,
  updateUserStatus,
  UserFormPayload,
} from '../../services/userService';
import { getStoredUser } from '../../services/authService';
import { cn } from '../../lib/utils';

const ITEMS_PER_PAGE = 8;

type UserFormState = {
  email: string;
  name: string;
  password: string;
  role: 'admin' | 'user';
  is_active: boolean;
};

const emptyForm: UserFormState = {
  email: '',
  name: '',
  password: '',
  role: 'user',
  is_active: true,
};

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function roleLabel(role: string): string {
  return role === 'admin' ? '管理员' : '普通用户';
}

function statusLabel(isActive: boolean): string {
  return isActive ? '正常' : '已禁用';
}

function initials(name: string): string {
  return (name || 'U').slice(0, 1).toUpperCase();
}

export const UserManagement = () => {
  const currentUser = getStoredUser();
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<AdminUser | null>(null);
  const [form, setForm] = useState<UserFormState>(emptyForm);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / ITEMS_PER_PAGE)), [total]);
  const activeUsers = useMemo(() => users.filter((user) => user.is_active).length, [users]);

  const loadUsers = useCallback(async (options?: { page?: number; search?: string }) => {
    const page = options?.page ?? currentPage;
    const search = options?.search ?? searchQuery;
    setIsLoading(true);
    setError(null);
    try {
      const response = await listUsers({
        search,
        offset: (page - 1) * ITEMS_PER_PAGE,
        limit: ITEMS_PER_PAGE,
      });
      setUsers(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '用户加载失败');
    } finally {
      setIsLoading(false);
    }
  }, [currentPage, searchQuery]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await listUsers({
          search: searchQuery,
          offset: (currentPage - 1) * ITEMS_PER_PAGE,
          limit: ITEMS_PER_PAGE,
        });
        if (!cancelled) {
          setUsers(response.items);
          setTotal(response.total);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '用户加载失败');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [currentPage, searchQuery]);

  const openCreateForm = () => {
    setEditingUser(null);
    setForm(emptyForm);
    setFormError(null);
    setIsFormOpen(true);
  };

  const openEditForm = (user: AdminUser) => {
    setEditingUser(user);
    setForm({
      email: user.email,
      name: user.name,
      password: '',
      role: user.role === 'admin' ? 'admin' : 'user',
      is_active: user.is_active,
    });
    setFormError(null);
    setIsFormOpen(true);
  };

  const closeForm = () => {
    if (isSaving) return;
    setIsFormOpen(false);
    setEditingUser(null);
    setFormError(null);
  };

  const handleToggleStatus = async (user: AdminUser) => {
    const nextActive = !user.is_active;
    setUsers((prev) => prev.map((item) => (item.id === user.id ? { ...item, is_active: nextActive } : item)));
    try {
      const updated = await updateUserStatus(user.id, nextActive);
      setUsers((prev) => prev.map((item) => (item.id === user.id ? updated : item)));
    } catch (err) {
      setUsers((prev) => prev.map((item) => (item.id === user.id ? user : item)));
      setError(err instanceof Error ? err.message : '用户状态更新失败');
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (!form.name.trim() || !form.email.trim()) {
      setFormError('请填写昵称和邮箱');
      return;
    }
    if (!editingUser && form.password.length < 6) {
      setFormError('新用户密码至少 6 位');
      return;
    }

    const payload: UserFormPayload = {
      email: form.email.trim(),
      name: form.name.trim(),
      role: form.role,
      is_active: form.is_active,
    };
    if (form.password) payload.password = form.password;

    setIsSaving(true);
    try {
      if (editingUser) {
        const updated = await updateUser(editingUser.id, payload);
        setUsers((prev) => prev.map((user) => (user.id === updated.id ? updated : user)));
      } else {
        await createUser(payload);
        setSearchQuery('');
        setCurrentPage(1);
        await loadUsers({ page: 1, search: '' });
      }
      setIsFormOpen(false);
      setEditingUser(null);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : '保存用户失败');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingUser) return;
    setIsSaving(true);
    setError(null);
    try {
      await deleteUser(deletingUser.id);
      setDeletingUser(null);
      if (users.length === 1 && currentPage > 1) {
        setCurrentPage((page) => page - 1);
      } else {
        await loadUsers();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除用户失败');
    } finally {
      setIsSaving(false);
    }
  };

  const renderUserRow = (user: AdminUser) => {
    const isSelf = currentUser?.id === user.id;
    return (
      <div
        key={user.id}
        className="grid grid-cols-1 gap-4 border-b border-slate-100/80 bg-white/55 px-5 py-4 transition-all hover:bg-white/80 md:grid-cols-[minmax(260px,1.4fr)_120px_120px_128px_220px] md:items-center"
      >
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl border border-white/70 bg-gradient-to-br from-slate-50 to-cyan-50 text-sm font-black text-slate-700 shadow-sm">
            {initials(user.name)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="truncate text-sm font-black text-slate-900">{user.name}</p>
              {isSelf && (
                <span className="rounded-full border border-sky-100 bg-sky-50 px-2 py-0.5 text-[10px] font-bold text-sky-700">
                  当前账号
                </span>
              )}
            </div>
            <p className="mt-1 flex items-center gap-1.5 truncate text-xs font-medium text-slate-500">
              <Mail size={13} />
              {user.email}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm font-bold text-slate-700">
          {user.role === 'admin' ? <Shield size={16} className="text-zinc-800" /> : <User size={16} className="text-slate-400" />}
          {roleLabel(user.role)}
        </div>

        <span
          className={cn(
            'w-fit rounded-full border px-3 py-1 text-xs font-black',
            user.is_active
              ? 'border-emerald-100 bg-emerald-50 text-emerald-600'
              : 'border-rose-100 bg-rose-50 text-rose-600',
          )}
        >
          {statusLabel(user.is_active)}
        </span>

        <div className="text-xs font-bold text-slate-400">{formatDate(user.created_at)}</div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => openEditForm(user)}
            className="gap-2 bg-white/80"
          >
            <Edit3 size={15} />
            编辑
          </Button>
          <Button
            variant={user.is_active ? 'danger' : 'secondary'}
            size="sm"
            onClick={() => handleToggleStatus(user)}
            disabled={isSelf && user.is_active}
            className="gap-2"
          >
            {user.is_active ? <UserX size={15} /> : <UserCheck size={15} />}
            {user.is_active ? '禁用' : '启用'}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDeletingUser(user)}
            disabled={isSelf}
            className="h-9 w-9 text-rose-500 hover:bg-rose-50"
            title="删除用户"
          >
            <Trash2 size={16} />
          </Button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.25em] text-slate-500">User Directory</p>
          <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-900">用户管理</h2>
        </div>
        <Button onClick={openCreateForm} size="lg" className="gap-2 self-start md:self-auto">
          <Plus size={18} />
          新增用户
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { label: '总用户数', value: total, icon: User },
          { label: '当前页正常账号', value: activeUsers, icon: CheckCircle2 },
          { label: '当前页管理员', value: users.filter((user) => user.role === 'admin').length, icon: Shield },
        ].map((item) => (
          <Card key={item.label} className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-widest text-slate-400">{item.label}</p>
                <p className="mt-2 text-3xl font-black tracking-tight text-slate-900">{item.value}</p>
              </div>
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/70 bg-white/70 text-slate-700 shadow-sm">
                <item.icon size={21} />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden p-0">
        <div className="flex flex-col gap-4 border-b border-white/70 p-5 md:flex-row md:items-center md:justify-between">
          <div className="relative w-full md:max-w-md">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索昵称或邮箱"
              className="w-full rounded-2xl border border-white/70 bg-white/70 py-3.5 pl-11 pr-5 text-sm font-bold text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-zinc-300 focus:bg-white focus:ring-4 focus:ring-zinc-100/60"
            />
          </div>
          <div className="text-sm font-bold text-slate-500">
            共 <span className="text-slate-900">{total}</span> 个用户
          </div>
        </div>

        {error && (
          <div className="mx-5 mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
            {error}
          </div>
        )}

        <div className="hidden grid-cols-[minmax(260px,1.4fr)_120px_120px_128px_220px] border-b border-slate-100 px-5 py-3 text-xs font-black uppercase tracking-widest text-slate-400 md:grid">
          <span>用户</span>
          <span>角色</span>
          <span>状态</span>
          <span>注册时间</span>
          <span className="text-right">操作</span>
        </div>

        <div className="min-h-[360px]">
          {isLoading ? (
            <div className="flex h-[360px] items-center justify-center gap-3 text-sm font-bold text-slate-400">
              <Loader2 size={18} className="animate-spin" />
              正在加载用户
            </div>
          ) : users.length > 0 ? (
            users.map(renderUserRow)
          ) : (
            <div className="flex h-[360px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
                <User size={24} />
              </div>
              <p className="text-sm font-black text-slate-600">没有找到匹配的用户</p>
              <p className="mt-1 text-xs font-medium text-slate-400">换个关键词，或新建一个账号</p>
            </div>
          )}
        </div>

        {total > ITEMS_PER_PAGE && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={setCurrentPage}
          />
        )}
      </Card>

      <AnimatePresence>
        {isFormOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 p-4 backdrop-blur-sm"
            onMouseDown={closeForm}
          >
            <motion.form
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.96 }}
              transition={{ duration: 0.22 }}
              onSubmit={handleSubmit}
              onMouseDown={(event) => event.stopPropagation()}
              className="w-full max-w-xl rounded-[28px] border border-white/70 bg-white/85 p-6 shadow-2xl shadow-slate-900/15 backdrop-blur-2xl"
            >
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">
                    {editingUser ? 'Edit User' : 'New User'}
                  </p>
                  <h3 className="mt-1 text-2xl font-black tracking-tight text-slate-900">
                    {editingUser ? '编辑用户' : '新增用户'}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={closeForm}
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                >
                  <X size={19} />
                </button>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Input
                  label="昵称"
                  value={form.name}
                  onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                  placeholder="例如：王小明"
                />
                <Input
                  label="邮箱"
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="name@example.com"
                />
                <Input
                  label={editingUser ? '新密码' : '登录密码'}
                  type="password"
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder={editingUser ? '留空则不修改' : '至少 6 位'}
                />
                <div>
                  <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-widest text-slate-400">
                    角色
                  </label>
                  <select
                    value={form.role}
                    onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value as 'admin' | 'user' }))}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3.5 font-medium text-slate-700 outline-none transition-all focus:border-zinc-400 focus:ring-4 focus:ring-zinc-100/50"
                  >
                    <option value="user">普通用户</option>
                    <option value="admin">管理员</option>
                  </select>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setForm((prev) => ({ ...prev, is_active: !prev.is_active }))}
                className="mt-5 flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4 text-left transition-all hover:bg-white"
              >
                <span>
                  <span className="block text-sm font-black text-slate-800">账号状态</span>
                  <span className="mt-0.5 block text-xs font-medium text-slate-400">
                    {form.is_active ? '允许登录和使用系统' : '禁止登录和使用系统'}
                  </span>
                </span>
                <span
                  className={cn(
                    'flex h-7 w-12 items-center rounded-full p-1 transition-colors',
                    form.is_active ? 'bg-emerald-400' : 'bg-slate-300',
                  )}
                >
                  <span
                    className={cn(
                      'h-5 w-5 rounded-full bg-white shadow-sm transition-transform',
                      form.is_active && 'translate-x-5',
                    )}
                  />
                </span>
              </button>

              {formError && (
                <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                  {formError}
                </div>
              )}

              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button type="button" variant="secondary" onClick={closeForm} disabled={isSaving}>
                  取消
                </Button>
                <Button type="submit" disabled={isSaving} className="gap-2">
                  {isSaving && <Loader2 size={16} className="animate-spin" />}
                  保存
                </Button>
              </div>
            </motion.form>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {deletingUser && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 p-4 backdrop-blur-sm"
            onMouseDown={() => !isSaving && setDeletingUser(null)}
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.96 }}
              onMouseDown={(event) => event.stopPropagation()}
              className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/90 p-6 shadow-2xl shadow-slate-900/15 backdrop-blur-2xl"
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
                <Trash2 size={22} />
              </div>
              <h3 className="text-xl font-black tracking-tight text-slate-900">删除用户</h3>
              <p className="mt-2 text-sm font-medium leading-6 text-slate-500">
                确认删除 {deletingUser.name}？该账号将无法继续登录。
              </p>
              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button type="button" variant="secondary" onClick={() => setDeletingUser(null)} disabled={isSaving}>
                  取消
                </Button>
                <Button type="button" variant="danger" onClick={handleDelete} disabled={isSaving} className="gap-2">
                  {isSaving && <Loader2 size={16} className="animate-spin" />}
                  删除
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
