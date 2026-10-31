/**
 * 记忆管理面板（admin 后台「记忆管理」Tab + 设置面板复用）。
 *
 * 2026-10-31 改为**服务端分页**：此前一次拉全量（默认 200 条）+ 前端过滤，
 * 记忆多了既慢又没法定位某一条（用户找一条幻觉记忆只能肉眼翻）。
 * 后端 GET /memory 支持 limit/offset/q/total（见 test_memory_list_api.py）。
 *
 * 为什么管理员视图从「按用户分组」改成「用户筛选 + 平铺」：
 * 服务端分页下跨用户排序（user_id, created_at）的组会跨页断裂，
 * 分组视图必然只看到当页的半个组；要按人看就用筛选下拉，语义更准确。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Brain, Loader2, Plus, Search, Sparkles, Trash2, User, Users } from 'lucide-react';
import {
  getMemories,
  deleteMemory,
  batchDeleteMemories,
  dedupeMemories,
  createMemory,
  type MemoryItem,
} from '../../services/memoryService';
import { listUsers, type AdminUser } from '../../services/userService';
import { formatApiDate } from '../../lib/datetime';
import { getStoredUser } from '../../services/authService';
import { cn } from '../../lib/utils';
import { Input } from '@/components/shadcn/input';
import { Button } from '@/components/shadcn/button';
import { Label } from '@/components/shadcn/label';
import { EmptyState } from '@/components/ui/EmptyState';
import { ListSkeleton } from '@/components/ui/Skeletons';
import { Pagination } from '../admin/Pagination';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { toastError } from '../../lib/errors';

const MEMORY_TYPE_OPTIONS = [
  { value: 'fact', label: '事实' },
  { value: 'preference', label: '偏好' },
  { value: 'tech', label: '技术栈' },
  { value: 'project', label: '项目' },
] as const;

const TYPE_LABELS: Record<string, string> = {
  fact: '事实',
  preference: '偏好',
  tech: '技术栈',
  project: '项目',
  conversation: '对话',
  context: '上下文',
};

const SOURCE_LABELS: Record<string, string> = {
  auto: '自动提取',
  tool: 'AI 主动保存',
  manual: '手动添加',
};

/** 搜索防抖，避免每敲一个字打一次后端 */
function useDebounced(value: string, delayMs = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function MemoryCard({
  memory,
  deleting,
  onDelete,
  ownerLabel,
  selected,
  onToggleSelect,
}: {
  memory: MemoryItem;
  deleting: number | null;
  onDelete: (id: number) => void;
  /** 管理员视图：这条记忆属于谁 */
  ownerLabel?: string;
  /** 批量删除：是否已勾选 */
  selected?: boolean;
  onToggleSelect?: (id: number, checked: boolean) => void;
}) {
  return (
    <div className="group flex items-start gap-3 rounded-xl border border-zinc-100 bg-[var(--surface-1)] px-4 py-3 transition-colors hover:border-[var(--border-subtle)]">
      {onToggleSelect && (
        <input
          type="checkbox"
          checked={selected ?? false}
          onChange={(e) => onToggleSelect(memory.id, e.target.checked)}
          className="mt-1 size-4 shrink-0 cursor-pointer rounded border-[var(--border-strong)] accent-[var(--primary)]"
          aria-label={`选择记忆：${memory.content.slice(0, 20)}`}
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed text-zinc-700">{memory.content}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-700">
            {TYPE_LABELS[memory.memory_type] || memory.memory_type}
          </span>
          {memory.source && (
            <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]">
              {SOURCE_LABELS[memory.source] || memory.source}
            </span>
          )}
          {ownerLabel && (
            <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-500/15 dark:text-sky-300">
              <User size={10} />
              {ownerLabel}
            </span>
          )}
          {memory.tags?.map((tag) => (
            <span key={tag} className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]">
              {tag}
            </span>
          ))}
          {memory.created_at && (
            <span className="text-[10px] text-[var(--muted-foreground)]">{formatApiDate(memory.created_at)}</span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onDelete(memory.id)}
        disabled={deleting === memory.id}
        className="shrink-0 rounded-lg p-1.5 text-[var(--muted-foreground)] transition-all hover:bg-rose-50 hover:text-rose-500"
        aria-label="删除记忆"
      >
        {deleting === memory.id ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Trash2 size={14} />
        )}
      </button>
    </div>
  );
}

export const MemoryPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const user = getStoredUser();
  const isAdmin = user?.role === 'admin';

  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounced(searchInput);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  /** 管理员：按用户筛选（'all' = 全部用户） */
  const [userFilter, setUserFilter] = useState<string>('all');
  const [deleting, setDeleting] = useState<number | null>(null);

  // Create form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState('fact');
  const [newImportance, setNewImportance] = useState(0.7);

  // 管理员的用户筛选下拉需要用户名映射
  const usersQuery = useQuery({
    queryKey: ['admin', 'users-lite'],
    queryFn: () => listUsers({ limit: 500 }),
    enabled: isAdmin,
    staleTime: 5 * 60_000,
  });
  const userMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const u of usersQuery.data?.items ?? []) {
      map.set(u.id, `${u.name} (#${u.id})`);
    }
    return map;
  }, [usersQuery.data]);

  const userFilterId = userFilter === 'all' ? undefined : Number(userFilter);

  const memoriesQuery = useQuery({
    queryKey: ['memories', isAdmin ? 'all' : 'mine', userFilter, page, pageSize, searchQuery],
    queryFn: () =>
      getMemories({
        userId: userFilterId,
        limit: pageSize,
        offset: (page - 1) * pageSize,
        q: searchQuery,
      }),
    placeholderData: (prev) => prev, // 翻页时保留上一页数据，避免闪空白
  });
  const memories = memoriesQuery.data?.items ?? [];
  const total = memoriesQuery.data?.total ?? memoriesQuery.data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // 过滤条件变化后回到第一页
  useEffect(() => {
    setPage(1);
  }, [searchQuery, userFilter, pageSize]);

  // 当前页被删空（或总数缩水）时自动回退，不要让用户停在空页上
  useEffect(() => {
    if (!memoriesQuery.isSuccess) return;
    if (memories.length === 0 && page > 1) setPage((prev) => prev - 1);
  }, [memories.length, page, memoriesQuery.isSuccess]);

  const deleteMutation = useMutation({
    mutationFn: (memoryId: number) => deleteMemory(memoryId),
    onSuccess: () => {
      toast.success('记忆已删除');
      setDeleting(null);
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
    onError: (err: Error) => {
      toast.error(toastError(err, '删除失败'));
      setDeleting(null);
    },
  });

  const createMutation = useMutation({
    mutationFn: () => createMemory(newContent, newType, newImportance),
    onSuccess: () => {
      toast.success('记忆已保存');
      setNewContent('');
      setShowCreateForm(false);
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '保存失败')),
  });

  const handleDelete = (memoryId: number) => {
    setDeleting(memoryId);
    deleteMutation.mutate(memoryId);
  };

  // ── 批量删除 ──
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const batchDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => batchDeleteMemories(ids),
    onSuccess: (result) => {
      const skipped = result.missing.length;
      toast.success(
        skipped > 0 ? `已删除 ${result.deleted} 条，${skipped} 条跳过（不存在或无权限）` : `已删除 ${result.deleted} 条记忆`,
      );
      setSelectedIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '批量删除失败')),
  });

  const toggleSelect = (id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };
  const allSelected = memories.length > 0 && memories.every((m) => selectedIds.has(m.id));
  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allSelected) memories.forEach((m) => next.delete(m.id));
      else memories.forEach((m) => next.add(m.id));
      return next;
    });
  };
  const handleBatchDelete = () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!window.confirm(`确定删除选中的 ${ids.length} 条记忆吗？删除后不可恢复。`)) return;
    batchDeleteMutation.mutate(ids);
  };

  // ── 一键去重（清理历史遗留的重复记忆）──
  const dedupeMutation = useMutation({
    mutationFn: (target: number) => dedupeMemories(target || undefined),
    onSuccess: (result) => {
      toast.success(
        result.removed > 0
          ? `去重完成：合并 ${result.removed} 条重复记忆，保留 ${result.kept} 条`
          : '没有发现重复记忆',
      );
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
    onError: (err: Error) => {
      toast.error(toastError(err, '记忆去重失败'));
    },
  });
  const handleDedupe = (targetUserId: number) => {
    if (
      !window.confirm(
        '将对记忆做向量相似度聚类去重：语义相同（≥92% 相似）的记忆只保留一条，删除其余。此操作不可恢复，确定继续？',
      )
    ) {
      return;
    }
    dedupeMutation.mutate(targetUserId);
  };

  const ownerLabelOf = (memory: MemoryItem): string | undefined => {
    if (!isAdmin) return undefined;
    return userMap.get(memory.user_id || 0) ?? (memory.user_id ? `用户 #${memory.user_id}` : undefined);
  };

  return (
    <div className="admin-page-stage space-y-4">
      <section className="admin-page-header">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-700">记忆管理</p>
            <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-[var(--foreground)]">
              {isAdmin ? '所有用户记忆' : '用户记忆'}
            </h2>
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">
              {isAdmin
                ? '管理员可查看和管理所有用户的记忆数据'
                : 'AI 会记住你的偏好和历史对话中的关键信息，用于个性化服务'}
            </p>
            {user && (
              <div className="mt-2 flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                {isAdmin ? <Users size={14} /> : <User size={14} />}
                <span>
                  当前用户：{user.name} ({user.email})
                  {isAdmin ? ' · 管理员' : ''}
                </span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {!isAdmin && (
              <Button size="sm" className="gap-1.5" onClick={() => setShowCreateForm((prev) => !prev)}>
                <Plus size={14} />
                添加记忆
              </Button>
            )}
            {isAdmin && (
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => handleDedupe(userFilter === 'all' ? 0 : Number(userFilter))}
                disabled={dedupeMutation.isPending || (userFilter !== 'all' && !userFilter)}
                title={userFilter === 'all' ? '对所有用户的记忆去重' : '对所选用户的记忆去重'}
              >
                {dedupeMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                清理重复记忆
              </Button>
            )}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-medium text-[var(--muted-foreground)] shadow-sm">
              共 <span className="font-semibold text-[var(--foreground)]">{total}</span> 条
            </span>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[14rem] flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            placeholder="搜索记忆（按内容过滤，服务端执行）..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        {isAdmin && (
          <Select value={userFilter} onValueChange={setUserFilter}>
            <SelectTrigger className="w-[13rem]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部用户</SelectItem>
              {(usersQuery.data?.items ?? []).map((u: AdminUser) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.name} (#{u.id})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* 批量删除工具条：勾选后出现 */}
      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2.5 dark:border-sky-500/40 dark:bg-sky-500/10">
          <span className="text-sm font-medium text-sky-800 dark:text-sky-300">
            已选 {selectedIds.size} 条
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={toggleSelectAll}
            disabled={memories.length === 0}
          >
            {allSelected ? '取消全选（当页）' : '全选（当页）'}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={handleBatchDelete}
            disabled={batchDeleteMutation.isPending}
            className="gap-1.5"
          >
            {batchDeleteMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            批量删除
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
            取消选择
          </Button>
        </div>
      )}

      {/* Create Form */}
      {showCreateForm && !isAdmin && (
        <div className="space-y-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] p-4">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="输入要记忆的内容..."
            rows={2}
            className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm text-[var(--foreground)] outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
          />
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 space-y-1.5">
              <Label>类型</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MEMORY_TYPE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="memory-importance">重要程度</Label>
              <Input
                id="memory-importance"
                type="number"
                value={newImportance}
                onChange={(e) => setNewImportance(parseFloat(e.target.value))}
                min={0.1}
                max={1}
                step={0.1}
                className="w-24"
              />
            </div>
            <Button
              onClick={() => newContent.trim() && createMutation.mutate()}
              disabled={createMutation.isPending || !newContent.trim()}
              className="gap-1.5"
            >
              {createMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              保存
            </Button>
            <Button variant="outline" onClick={() => setShowCreateForm(false)}>
              取消
            </Button>
          </div>
        </div>
      )}

      {memoriesQuery.isLoading ? (
        <ListSkeleton rows={4} columns={3} />
      ) : memoriesQuery.isError ? (
        <div
          className={cn(
            'rounded-2xl border border-dashed border-rose-200 bg-rose-50 px-4 py-10 text-center dark:border-rose-500/40 dark:bg-rose-500/10',
            'text-sm font-semibold text-rose-600 dark:text-rose-300',
          )}
        >
          <p>记忆加载失败</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => void memoriesQuery.refetch()}
          >
            重新加载
          </Button>
        </div>
      ) : memories.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)]">
          <EmptyState
            icon={<Brain className="size-5" />}
            title={searchQuery ? '没有找到匹配的记忆' : '还没有记忆'}
            description={
              searchQuery
                ? '换个关键词试试，或清空搜索条件查看全部记忆。'
                : 'AI 会在对话中自动学习你的偏好，也可以手动新建一条记忆。'
            }
            action={
              searchQuery
                ? { label: '清除搜索条件', onClick: () => setSearchInput('') }
                : isAdmin
                  ? undefined
                  : { label: '新建记忆', onClick: () => setShowCreateForm(true) }
            }
          />
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {memories.map((memory) => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                deleting={deleting}
                onDelete={handleDelete}
                ownerLabel={ownerLabelOf(memory)}
                selected={selectedIds.has(memory.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            totalLabel={
              <span>
                共 <span className="font-semibold text-[var(--foreground)]">{total}</span> 条记忆
              </span>
            }
          />
        </>
      )}
    </div>
  );
};
