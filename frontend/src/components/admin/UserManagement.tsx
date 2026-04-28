import React, { useEffect, useMemo, useState } from 'react';
import { Search, Shield, UserCheck, UserX } from 'lucide-react';
import { Pagination } from './Pagination';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { AdminUser, listUsers, updateUserStatus } from '../../services/userService';

const ITEMS_PER_PAGE = 8;

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString();
}

export const UserManagement = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / ITEMS_PER_PAGE)), [total]);

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
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load users');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [currentPage, searchQuery]);

  const handleToggleStatus = async (user: AdminUser) => {
    const nextActive = !user.is_active;
    setUsers((prev) => prev.map((item) => (item.id === user.id ? { ...item, is_active: nextActive } : item)));
    try {
      const updated = await updateUserStatus(user.id, nextActive);
      setUsers((prev) => prev.map((item) => (item.id === user.id ? updated : item)));
    } catch (err) {
      setUsers((prev) => prev.map((item) => (item.id === user.id ? user : item)));
      setError(err instanceof Error ? err.message : 'Failed to update user');
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">用户管理</h2>
      <Card className="flex flex-col p-0 overflow-hidden">
        <div className="p-8 flex-1">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
            <div className="relative w-full md:w-96">
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索用户昵称或邮箱"
                className="w-full pl-12 pr-5 py-3.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-zinc-400 focus:ring-4 focus:ring-zinc-100/50 transition-all font-medium text-sm"
              />
            </div>
            <div className="text-sm font-bold text-slate-500">共 {total} 个用户</div>
          </div>

          {error && (
            <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
              {error}
            </div>
          )}

          <div className="space-y-4">
            {isLoading ? (
              <div className="py-12 text-center text-slate-400 font-medium">正在加载用户...</div>
            ) : users.length > 0 ? (
              users.map((user) => (
                <div key={user.id} className="flex items-center justify-between p-5 bg-white border border-slate-100 rounded-2xl hover:border-zinc-300 hover:shadow-md transition-all group">
                  <div className="flex items-center gap-5 min-w-0">
                    <div className="w-12 h-12 bg-gradient-to-br from-slate-100 to-slate-200 rounded-2xl flex items-center justify-center text-slate-500 font-black shadow-inner">
                      {user.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-bold text-slate-800 text-base truncate">{user.name}</p>
                        {user.role === 'admin' && <Shield size={15} className="text-zinc-700" />}
                      </div>
                      <p className="text-xs text-slate-400 font-medium mt-0.5 truncate">
                        {user.email} · 注册时间 {formatDate(user.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                      user.is_active
                        ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
                        : 'bg-rose-50 text-rose-600 border-rose-100'
                    }`}>
                      {user.is_active ? '正常' : '禁用'}
                    </span>
                    <Button
                      variant={user.is_active ? 'danger' : 'secondary'}
                      size="sm"
                      onClick={() => handleToggleStatus(user)}
                    >
                      {user.is_active ? <UserX size={16} /> : <UserCheck size={16} />}
                      {user.is_active ? '禁用' : '启用'}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <div className="py-12 text-center text-slate-400 font-medium">没有找到匹配的用户</div>
            )}
          </div>
        </div>
        {total > ITEMS_PER_PAGE && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={setCurrentPage}
          />
        )}
      </Card>
    </div>
  );
};
