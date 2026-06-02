import React, { useState, useEffect } from 'react';
import { Brain, Loader2, Search, Trash2, User, Users } from 'lucide-react';
import { getMemories, deleteMemory, MemoryItem } from '../../services/memoryService';
import { formatApiDate } from '../../lib/datetime';
import { getStoredUser } from '../../services/authService';
import { cn } from '../../lib/utils';

export const MemoryPanel: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleting, setDeleting] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const user = getStoredUser();
  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    loadMemories();
  }, []);

  const loadMemories = async () => {
    setLoading(true);
    try {
      // 管理员加载所有用户的记忆
      const response = await getMemories();
      setMemories(response.items);
    } catch (err) {
      console.error('Failed to load memories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (memoryId: number) => {
    setDeleting(memoryId);
    try {
      await deleteMemory(memoryId);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
      setMessage('记忆已删除');
    } catch (err) {
      console.error('Failed to delete memory:', err);
    } finally {
      setDeleting(null);
    }
  };

  const filteredMemories = searchQuery
    ? memories.filter((m) => m.content.toLowerCase().includes(searchQuery.toLowerCase()))
    : memories;

  const typeLabels: Record<string, string> = {
    fact: '事实',
    preference: '偏好',
    tech: '技术栈',
    project: '项目',
    conversation: '对话',
    context: '上下文',
  };

  const sourceLabels: Record<string, string> = {
    auto: '自动提取',
    tool: 'AI 主动保存',
    manual: '手动添加',
  };

  // 按用户分组（管理员视图）
  const groupedByUser = isAdmin
    ? filteredMemories.reduce((acc, m) => {
        const uid = m.user_id || 0;
        if (!acc[uid]) acc[uid] = [];
        acc[uid].push(m);
        return acc;
      }, {} as Record<number, MemoryItem[]>)
    : null;

  return (
    <div className="admin-page-stage space-y-4">
      <section className="admin-page-header">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">记忆管理</p>
            <h2 className="mt-1.5 text-xl font-black tracking-tight text-slate-950">
              {isAdmin ? '所有用户记忆' : '用户记忆'}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {isAdmin
                ? '管理员可查看和管理所有用户的记忆数据'
                : 'AI 会记住你的偏好和历史对话中的关键信息，用于个性化服务'}
            </p>
            {user && (
              <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                {isAdmin ? <Users size={14} /> : <User size={14} />}
                <span>当前用户：{user.name} ({user.email}){isAdmin ? ' · 管理员' : ''}</span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {message && (
              <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
                {message}
              </div>
            )}
            <div className="admin-kpi-pill">
              共 <span className="font-black text-slate-900">{memories.length}</span> 条
            </div>
          </div>
        </div>
      </section>

      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          placeholder="搜索记忆..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition-colors focus:border-purple-300 focus:ring-2 focus:ring-purple-100"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-slate-400" />
        </div>
      ) : filteredMemories.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-12 text-center">
          <Brain size={40} className="mx-auto mb-3 text-slate-300" />
          <p className="text-sm font-bold text-slate-500">
            {searchQuery ? '没有找到匹配的记忆' : '还没有记忆，AI 会在对话中自动学习'}
          </p>
        </div>
      ) : isAdmin && groupedByUser ? (
        // 管理员视图：按用户分组显示
        <div className="space-y-6">
          {Object.entries(groupedByUser).map(([uid, items]) => (
            <div key={uid}>
              <div className="mb-2 flex items-center gap-2">
                <User size={14} className="text-slate-400" />
                <span className="text-xs font-black uppercase tracking-[0.12em] text-slate-500">
                  用户 #{uid} · {items.length} 条记忆
                </span>
              </div>
              <div className="space-y-2">
                {items.map((memory) => (
                  <MemoryCard
                    key={memory.id}
                    memory={memory}
                    deleting={deleting}
                    onDelete={handleDelete}
                    showUser={false}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // 普通用户视图
        <div className="space-y-2">
          {filteredMemories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              deleting={deleting}
              onDelete={handleDelete}
              showUser={false}
            />
          ))}
        </div>
      )}
    </div>
  );
};

function MemoryCard({
  memory,
  deleting,
  onDelete,
  showUser,
}: {
  memory: MemoryItem;
  deleting: number | null;
  onDelete: (id: number) => void;
  showUser: boolean;
}) {
  const typeLabels: Record<string, string> = {
    fact: '事实',
    preference: '偏好',
    tech: '技术栈',
    project: '项目',
    conversation: '对话',
    context: '上下文',
  };

  const sourceLabels: Record<string, string> = {
    auto: '自动提取',
    tool: 'AI 保存',
    manual: '手动',
  };

  return (
    <div className="group flex items-start gap-3 rounded-2xl border border-slate-100 bg-white px-4 py-3 transition-colors hover:border-slate-200">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-700 leading-relaxed">{memory.content}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-purple-50 px-2 py-0.5 text-[10px] font-bold text-purple-600">
            {typeLabels[memory.memory_type] || memory.memory_type}
          </span>
          {memory.source && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
              {sourceLabels[memory.source] || memory.source}
            </span>
          )}
          {memory.tags?.map((tag) => (
            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
              {tag}
            </span>
          ))}
          {showUser && memory.user_id && (
            <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-bold text-sky-600">
              用户 #{memory.user_id}
            </span>
          )}
          {memory.created_at && (
            <span className="text-[10px] text-slate-400">{formatApiDate(memory.created_at)}</span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onDelete(memory.id)}
        disabled={deleting === memory.id}
        className="flex-shrink-0 rounded-lg p-1.5 text-slate-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
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
