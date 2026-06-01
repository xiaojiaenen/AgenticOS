import React, { useState, useEffect } from 'react';
import { Brain, Trash2, Search, Loader2 } from 'lucide-react';
import { getMemories, deleteMemory, MemoryItem } from '../../services/memoryService';

export const MemoryPanel: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    loadMemories();
  }, []);

  const loadMemories = async () => {
    setLoading(true);
    try {
      const response = await getMemories();
      setMemories(response.items);
    } catch (err) {
      console.error('Failed to load memories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (memoryId: string) => {
    setDeleting(memoryId);
    try {
      await deleteMemory(memoryId);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
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
    conversation: '对话',
    context: '上下文',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-100">
          <Brain size={20} className="text-purple-600" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-900">记忆管理</h3>
          <p className="text-sm text-slate-500">
            AI 会记住你的偏好和历史对话中的关键信息
          </p>
        </div>
      </div>

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
        <div className="flex items-center justify-center py-8">
          <Loader2 size={24} className="animate-spin text-slate-400" />
        </div>
      ) : filteredMemories.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center">
          <Brain size={32} className="mx-auto mb-2 text-slate-300" />
          <p className="text-sm text-slate-500">
            {searchQuery ? '没有找到匹配的记忆' : '还没有记忆，AI 会在对话中自动学习'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredMemories.map((memory) => (
            <div
              key={memory.id}
              className="group flex items-start gap-3 rounded-xl border border-slate-100 bg-white px-4 py-3 transition-colors hover:border-slate-200"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-700 leading-relaxed">{memory.content}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-purple-50 px-2 py-0.5 text-[10px] font-bold text-purple-600">
                    {typeLabels[memory.memory_type] || memory.memory_type}
                  </span>
                  {memory.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500"
                    >
                      {tag}
                    </span>
                  ))}
                  {memory.created_at && (
                    <span className="text-[10px] text-slate-400">
                      {new Date(memory.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(memory.id)}
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
          ))}
        </div>
      )}

      <div className="rounded-xl bg-slate-50 px-4 py-3">
        <p className="text-xs text-slate-500">
          共 {memories.length} 条记忆 · AI 在对话中自动提取关键信息
        </p>
      </div>
    </div>
  );
};
