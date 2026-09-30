/**
 * 记忆管理面板（admin 后台「记忆管理」Tab + 设置面板复用）。
 * TanStack Query 数据层 + shadcn Select + sonner toast。
 * 后端 API 不变（services/memoryService.ts）。
 */
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Brain, Loader2, Plus, Search, Trash2, User, Users } from 'lucide-react';
import { getMemories, deleteMemory, createMemory, type MemoryItem } from '../../services/memoryService';
import { formatApiDate } from '../../lib/datetime';
import { getStoredUser } from '../../services/authService';
import { cn } from '../../lib/utils';
import { Input } from '@/components/shadcn/input';
import { Button } from '@/components/shadcn/button';
import { Label } from '@/components/shadcn/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';

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

function MemoryCard({
  memory,
  deleting,
  onDelete,
}: {
  memory: MemoryItem;
  deleting: number | null;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="group flex items-start gap-3 rounded-xl border border-zinc-100 bg-white px-4 py-3 transition-colors hover:border-zinc-200">
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed text-zinc-700">{memory.content}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-600">
            {TYPE_LABELS[memory.memory_type] || memory.memory_type}
          </span>
          {memory.source && (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500">
              {SOURCE_LABELS[memory.source] || memory.source}
            </span>
          )}
          {memory.tags?.map((tag) => (
            <span key={tag} className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500">
              {tag}
            </span>
          ))}
          {memory.created_at && (
            <span className="text-[10px] text-zinc-400">{formatApiDate(memory.created_at)}</span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onDelete(memory.id)}
        disabled={deleting === memory.id}
        className="shrink-0 rounded-lg p-1.5 text-zinc-400 transition-all hover:bg-rose-50 hover:text-rose-500"
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

  const [searchQuery, setSearchQuery] = useState('');
  const [deleting, setDeleting] = useState<number | null>(null);

  // Create form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState('fact');
  const [newImportance, setNewImportance] = useState(0.7);

  const memoriesQuery = useQuery({
    queryKey: ['admin', 'memories'],
    queryFn: () => getMemories(),
  });
  const memories = memoriesQuery.data?.items ?? [];

  const deleteMutation = useMutation({
    mutationFn: (memoryId: number) => deleteMemory(memoryId),
    onSuccess: () => {
      toast.success('记忆已删除');
      setDeleting(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'memories'] });
    },
    onError: (err: Error) => {
      toast.error(err.message || '删除失败');
      setDeleting(null);
    },
  });

  const createMutation = useMutation({
    mutationFn: () => createMemory(newContent, newType, newImportance),
    onSuccess: () => {
      toast.success('记忆已保存');
      setNewContent('');
      setShowCreateForm(false);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'memories'] });
    },
    onError: (err: Error) => toast.error(err.message || '保存失败'),
  });

  const handleDelete = (memoryId: number) => {
    setDeleting(memoryId);
    deleteMutation.mutate(memoryId);
  };

  const filteredMemories = useMemo(
    () =>
      searchQuery
        ? memories.filter((m) => m.content.toLowerCase().includes(searchQuery.toLowerCase()))
        : memories,
    [memories, searchQuery],
  );

  // 按用户分组（管理员视图）
  const groupedByUser = useMemo(() => {
    if (!isAdmin) return null;
    return filteredMemories.reduce<Record<number, MemoryItem[]>>((acc, m) => {
      const uid = m.user_id || 0;
      if (!acc[uid]) acc[uid] = [];
      acc[uid].push(m);
      return acc;
    }, {});
  }, [isAdmin, filteredMemories]);

  return (
    <div className="admin-page-stage space-y-4">
      <section className="admin-page-header">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-indigo-600">记忆管理</p>
            <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-zinc-950">
              {isAdmin ? '所有用户记忆' : '用户记忆'}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {isAdmin
                ? '管理员可查看和管理所有用户的记忆数据'
                : 'AI 会记住你的偏好和历史对话中的关键信息，用于个性化服务'}
            </p>
            {user && (
              <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
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
            <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-500 shadow-sm">
              共 <span className="font-semibold text-zinc-900">{memories.length}</span> 条
            </span>
          </div>
        </div>
      </section>

      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
        <Input
          placeholder="搜索记忆..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Create Form */}
      {showCreateForm && !isAdmin && (
        <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="输入要记忆的内容..."
            rows={2}
            className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
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
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-zinc-400" />
        </div>
      ) : memoriesQuery.isError ? (
        <div
          className={cn(
            'rounded-2xl border border-dashed border-rose-200 bg-rose-50 px-4 py-12 text-center',
            'text-sm font-semibold text-rose-600',
          )}
        >
          记忆加载失败，请刷新重试
        </div>
      ) : filteredMemories.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-200 bg-zinc-50 px-4 py-12 text-center">
          <Brain size={40} className="mx-auto mb-3 text-zinc-300" />
          <p className="text-sm font-semibold text-zinc-500">
            {searchQuery ? '没有找到匹配的记忆' : '还没有记忆，AI 会在对话中自动学习'}
          </p>
        </div>
      ) : isAdmin && groupedByUser ? (
        // 管理员视图：按用户分组显示
        <div className="space-y-6">
          {Object.entries(groupedByUser).map(([uid, items]) => (
            <div key={uid}>
              <div className="mb-2 flex items-center gap-2">
                <User size={14} className="text-zinc-400" />
                <span className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                  用户 #{uid} · {items.length} 条记忆
                </span>
              </div>
              <div className="space-y-2">
                {items.map((memory) => (
                  <MemoryCard key={memory.id} memory={memory} deleting={deleting} onDelete={handleDelete} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // 普通用户视图
        <div className="space-y-2">
          {filteredMemories.map((memory) => (
            <MemoryCard key={memory.id} memory={memory} deleting={deleting} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
};
