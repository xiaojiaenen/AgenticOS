import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  CheckCircle2,
  Edit3,
  Loader2,
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

const ITEMS_PER_PAGE = 12;

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
  const adminUsers = useMemo(() => users.filter((user) => user.role === 'admin').length, [users]);

  const loadUsers = useCallback(
    async (options?: { page?: number; search?: string }) => {
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
    },
    [currentPage, searchQuery],
  );

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
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '用户加载失败');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
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
      setFormError('请填写名称和邮箱');
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

  return (
    <div className="space-y-6">
      <section className="admin-solid-panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="admin-section-kicker">用户管理</p>
            <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">高密度列表更适合批量维护账号</h2>
            <p className="mt-3 text-sm font-medium leading-7 text-slate-500">
              主页面保留筛选、状态和批量可读信息，创建和编辑统一放进弹窗，避免在长表单和长列表之间来回滚动。
            </p>
          </div>
          <Button onClick={openCreateForm} size="lg" className="gap-2 self-start lg:self-auto">
            <Plus size={18} />
            新增用户
          </Button>
        </div>
      </section>

      <section className="overflow-hidden rounded-[32px] border border-white/60 bg-white/46 shadow-[0_22px_60px_rgba(15,23,42,0.08)] ring-1 ring-white/30 backdrop-blur-[24px]">
        <div className="grid grid-cols-1 divide-y divide-white/55 md:grid-cols-3 md:divide-x md:divide-y-0">
          {[
            { label: '用户总数', value: total, icon: User, tone: 'bg-sky-50 text-sky-700 border-sky-100' },
            { label: '本页启用', value: activeUsers, icon: CheckCircle2, tone: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
            { label: '本页管理员', value: adminUsers, icon: Shield, tone: 'bg-amber-50 text-amber-700 border-amber-100' },
          ].map((item) => (
            <div key={item.label} className="px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{item.label}</p>
                  <p className="mt-2 text-3xl font-black tracking-tight text-slate-900">{item.value}</p>
                </div>
                <div className={cn('flex h-11 w-11 items-center justify-center rounded-2xl border', item.tone)}>
                  <item.icon size={21} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          {error}
        </div>
      )}

      <Card className="overflow-hidden p-0">
        <div className="flex flex-col gap-4 border-b border-white/70 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">用户目录</p>
            <h3 className="mt-2 text-xl font-black tracking-tight text-slate-900">按名称和邮箱快速检索</h3>
          </div>

          <div className="flex w-full flex-col gap-3 lg:w-auto lg:flex-row lg:items-center">
            <div className="relative w-full lg:w-[360px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索名称或邮箱"
                className="w-full rounded-[22px] border border-white/75 bg-white/72 py-3.5 pl-11 pr-5 text-sm font-semibold text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
              />
            </div>
            <div className="rounded-[22px] border border-white/80 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-500">
              共 <span className="font-black text-slate-900">{total}</span> 个用户
            </div>
          </div>
        </div>

        <div className="hidden grid-cols-[minmax(240px,1.5fr)_120px_120px_140px_180px] border-b border-slate-100 px-5 py-3 text-xs font-black uppercase tracking-[0.2em] text-slate-400 xl:grid">
          <span>用户</span>
          <span>角色</span>
          <span>状态</span>
          <span>创建时间</span>
          <span className="text-right">操作</span>
        </div>

        <div className="min-h-[400px]">
          {isLoading ? (
            <div className="flex h-[400px] items-center justify-center gap-3 text-sm font-bold text-slate-400">
              <Loader2 size={18} className="animate-spin" />
              正在加载用户
            </div>
          ) : users.length > 0 ? (
            users.map((user) => {
              const isSelf = currentUser?.id === user.id;
              return (
                <div
                  key={user.id}
                  className="admin-table-row grid grid-cols-1 gap-4 border-b border-slate-100/80 px-5 py-4 xl:grid-cols-[minmax(240px,1.5fr)_120px_120px_140px_180px] xl:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-black text-slate-900">{user.name}</p>
                      {isSelf && (
                        <span className="rounded-full border border-sky-100 bg-sky-50 px-2 py-0.5 text-[10px] font-black text-sky-700">
                          当前账号
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs font-medium text-slate-500">{user.email}</p>
                  </div>

                  <div className="text-sm font-bold text-slate-700">{roleLabel(user.role)}</div>

                  <span
                    className={cn(
                      'w-fit rounded-full px-2.5 py-1 text-[10px] font-black',
                      user.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600',
                    )}
                  >
                    {statusLabel(user.is_active)}
                  </span>

                  <div className="text-sm font-bold text-slate-600">{formatDate(user.created_at)}</div>

                  <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                    <Button variant="secondary" size="sm" onClick={() => openEditForm(user)} className="gap-2 bg-white/85">
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
            })
          ) : (
            <div className="flex h-[400px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
                <User size={24} />
              </div>
              <p className="text-sm font-black text-slate-600">没有找到匹配的用户</p>
              <p className="mt-1 text-xs font-medium text-slate-400">换个关键词，或者直接创建新账号</p>
            </div>
          )}
        </div>

        {total > ITEMS_PER_PAGE && (
          <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
        )}
      </Card>

      <AnimatePresence>
        {isFormOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/22 p-4 backdrop-blur-sm"
            onMouseDown={closeForm}
          >
            <motion.form
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.96 }}
              transition={{ duration: 0.22 }}
              onSubmit={handleSubmit}
              onMouseDown={(event) => event.stopPropagation()}
              className="admin-solid-panel w-full max-w-xl p-6"
            >
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="admin-section-kicker">{editingUser ? '编辑用户' : '新增用户'}</p>
                  <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                    {editingUser ? '调整用户资料' : '创建后台账号'}
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
                  label="名称"
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
                  <label className="mb-2 ml-1 block text-xs font-black uppercase tracking-[0.2em] text-slate-400">
                    角色
                  </label>
                  <select
                    value={form.role}
                    onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value as 'admin' | 'user' }))}
                    className="w-full rounded-[22px] border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 outline-none transition-all focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                  >
                    <option value="user">普通用户</option>
                    <option value="admin">管理员</option>
                  </select>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setForm((prev) => ({ ...prev, is_active: !prev.is_active }))}
                className="mt-5 flex w-full items-center justify-between rounded-[24px] border border-white/80 bg-white/70 px-5 py-4 text-left transition-all hover:bg-white"
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
                <div className="mt-5 rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/22 p-4 backdrop-blur-sm"
            onMouseDown={() => !isSaving && setDeletingUser(null)}
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.96 }}
              onMouseDown={(event) => event.stopPropagation()}
              className="admin-solid-panel w-full max-w-md p-6"
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
                <Trash2 size={22} />
              </div>
              <h3 className="text-xl font-black tracking-tight text-slate-900">删除用户</h3>
              <p className="mt-2 text-sm font-medium leading-6 text-slate-500">
                确认删除 {deletingUser.name}？删除后该账号将无法继续登录。
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
