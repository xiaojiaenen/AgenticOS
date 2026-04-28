import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Bot, Clock3, Loader2, MessageSquare, RefreshCw, Search, Trash2, User, Zap } from 'lucide-react';
import { Pagination } from './Pagination';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { AdminConversation, deleteConversation, listConversations } from '../../services/conversationService';
import { cn } from '../../lib/utils';

const ITEMS_PER_PAGE = 8;

function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatLatency(value: number): string {
  if (!value) return '0ms';
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

function initials(name?: string | null): string {
  return (name || 'U').slice(0, 1).toUpperCase();
}

export const ChatHistory = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<AdminConversation[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / ITEMS_PER_PAGE)), [total]);
  const pageTotals = useMemo(() => ({
    tokens: items.reduce((sum, item) => sum + item.total_tokens, 0),
    calls: items.reduce((sum, item) => sum + item.llm_calls, 0),
    tools: items.reduce((sum, item) => sum + item.tool_calls, 0),
  }), [items]);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await listConversations({
        search: searchQuery,
        offset: (currentPage - 1) * ITEMS_PER_PAGE,
        limit: ITEMS_PER_PAGE,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '对话数据加载失败');
    } finally {
      setIsLoading(false);
    }
  }, [currentPage, searchQuery]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadData();
    }, 180);
    return () => window.clearTimeout(timer);
  }, [loadData]);

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm('确认删除该对话及其统计记录？')) return;
    setDeletingId(sessionId);
    setError(null);
    try {
      await deleteConversation(sessionId);
      if (items.length === 1 && currentPage > 1) {
        setCurrentPage((page) => page - 1);
      } else {
        await loadData();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除对话失败');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.25em] text-slate-500">Conversation Ops</p>
          <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-900">对话管理</h2>
        </div>
        <Button variant="secondary" onClick={loadData} disabled={isLoading} className="gap-2 self-start md:self-auto">
          {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          刷新数据
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {[
          { label: '对话总数', value: total, icon: MessageSquare, tone: 'bg-sky-50 text-sky-700 border-sky-100' },
          { label: '当前页 Token', value: pageTotals.tokens, icon: Zap, tone: 'bg-violet-50 text-violet-700 border-violet-100' },
          { label: '当前页模型调用', value: pageTotals.calls, icon: Bot, tone: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
          { label: '当前页工具调用', value: pageTotals.tools, icon: Clock3, tone: 'bg-amber-50 text-amber-700 border-amber-100' },
        ].map((item) => (
          <Card key={item.label} className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-widest text-slate-400">{item.label}</p>
                <p className="mt-2 text-3xl font-black tracking-tight text-slate-900">{formatNumber(item.value)}</p>
              </div>
              <div className={cn('flex h-11 w-11 items-center justify-center rounded-2xl border', item.tone)}>
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
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索用户、邮箱、Session 或消息摘要"
              className="w-full rounded-2xl border border-white/70 bg-white/70 py-3.5 pl-11 pr-5 text-sm font-bold text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-zinc-300 focus:bg-white focus:ring-4 focus:ring-zinc-100/60"
            />
          </div>
          <div className="text-sm font-bold text-slate-500">
            共 <span className="text-slate-900">{total}</span> 条会话
          </div>
        </div>

        {error && (
          <div className="mx-5 mt-5 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        <div className="hidden grid-cols-[minmax(260px,1.2fr)_minmax(260px,1.4fr)_110px_110px_110px_120px_90px] border-b border-slate-100 px-5 py-3 text-xs font-black uppercase tracking-widest text-slate-400 xl:grid">
          <span>用户</span>
          <span>对话摘要</span>
          <span>Token</span>
          <span>模型调用</span>
          <span>工具调用</span>
          <span>更新时间</span>
          <span className="text-right">操作</span>
        </div>

        <div className="min-h-[430px]">
          {isLoading ? (
            <div className="flex h-[430px] items-center justify-center gap-3 text-sm font-bold text-slate-400">
              <Loader2 size={18} className="animate-spin" />
              正在加载对话
            </div>
          ) : items.length > 0 ? (
            items.map((item) => (
              <div key={item.session_id} className="grid grid-cols-1 gap-4 border-b border-slate-100/80 bg-white/55 px-5 py-4 transition-all hover:bg-white/80 xl:grid-cols-[minmax(260px,1.2fr)_minmax(260px,1.4fr)_110px_110px_110px_120px_90px] xl:items-center">
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl border border-white/70 bg-gradient-to-br from-slate-50 to-cyan-50 text-sm font-black text-slate-700 shadow-sm">
                    {initials(item.user_name)}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-black text-slate-900">{item.user_name || '未知用户'}</p>
                    <p className="mt-1 truncate text-xs font-medium text-slate-500">{item.user_email || item.session_id}</p>
                  </div>
                </div>

                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-slate-800">{item.summary || item.first_message || '无摘要'}</p>
                  <p className="mt-1 truncate text-xs font-medium text-slate-500">
                    {item.last_message || '暂无消息内容'} · {formatNumber(item.message_count)} 条消息
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(item.model_names.length ? item.model_names : ['未记录模型']).slice(0, 3).map((model) => (
                      <span key={model} className="rounded-full border border-slate-200 bg-white/70 px-2 py-0.5 text-[10px] font-black text-slate-500">
                        {model}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="text-sm font-black text-slate-900">{formatNumber(item.total_tokens)}</div>
                <div className="text-sm font-bold text-slate-600">{formatNumber(item.llm_calls)}</div>
                <div className="text-sm font-bold text-slate-600">{formatNumber(item.tool_calls)}</div>
                <div>
                  <p className="text-sm font-bold text-slate-600">{formatDate(item.updated_at)}</p>
                  <p className="mt-1 text-xs font-medium text-slate-400">{formatLatency(item.avg_latency_ms)}</p>
                </div>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(item.session_id)}
                    disabled={deletingId === item.session_id}
                    className="h-9 w-9 text-rose-500 hover:bg-rose-50"
                    title="删除对话"
                  >
                    {deletingId === item.session_id ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  </Button>
                </div>
              </div>
            ))
          ) : (
            <div className="flex h-[430px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
                <MessageSquare size={24} />
              </div>
              <p className="text-sm font-black text-slate-600">没有找到对话记录</p>
              <p className="mt-1 text-xs font-medium text-slate-400">新的登录对话会自动统计到这里</p>
            </div>
          )}
        </div>

        {total > ITEMS_PER_PAGE && (
          <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
        )}
      </Card>
    </div>
  );
};
