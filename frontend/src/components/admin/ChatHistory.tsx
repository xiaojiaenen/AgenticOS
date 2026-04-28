import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertCircle,
  Eye,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { Pagination } from './Pagination';
import { Button } from '../ui/Button';
import { formatApiDateTime } from '../../lib/datetime';
import {
  AdminConversation,
  AdminConversationDetail,
  deleteConversation,
  getConversationDetail,
  listConversations,
} from '../../services/conversationService';

const ITEMS_PER_PAGE = 12;

function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatLatency(value: number): string {
  if (!value) return '0ms';
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

function roleLabel(role?: string | null): string {
  if (role === 'user') return '用户';
  if (role === 'model' || role === 'assistant') return '模型';
  if (role === 'system') return '系统';
  return '消息';
}

function roleTone(role?: string | null): string {
  if (role === 'user') return 'border-sky-100 bg-sky-50 text-sky-700';
  if (role === 'model' || role === 'assistant') return 'border-emerald-100 bg-emerald-50 text-emerald-700';
  if (role === 'system') return 'border-amber-100 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-100 text-slate-600';
}

export const ChatHistory = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<AdminConversation[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [detailSessionId, setDetailSessionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / ITEMS_PER_PAGE)), [total]);
  const pageTotals = useMemo(
    () => ({
      tokens: items.reduce((sum, item) => sum + item.total_tokens, 0),
      calls: items.reduce((sum, item) => sum + item.llm_calls, 0),
      tools: items.reduce((sum, item) => sum + item.tool_calls, 0),
    }),
    [items],
  );

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

  const openDetail = async (sessionId: string) => {
    setDetailSessionId(sessionId);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const response = await getConversationDetail(sessionId);
      setDetail(response);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : '会话详情加载失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    if (detailLoading) return;
    setDetailSessionId(null);
    setDetail(null);
    setDetailError(null);
  };

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm('确认删除这条会话及其统计记录？')) return;
    setDeletingId(sessionId);
    setError(null);
    try {
      await deleteConversation(sessionId);
      if (detailSessionId === sessionId) {
        closeDetail();
      }
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
    <div className="admin-page-stage space-y-5">
      <section className="admin-page-header">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">聊天记录</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">会话列表</h2>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="admin-kpi-pill">
              共 <span className="font-black text-slate-900">{total}</span> 条会话
            </div>
            <div className="admin-kpi-pill">
              本页 Token <span className="font-black text-slate-900">{formatNumber(pageTotals.tokens)}</span>
            </div>
            <div className="admin-kpi-pill">
              模型/工具 <span className="font-black text-slate-900">{formatNumber(pageTotals.calls)} / {formatNumber(pageTotals.tools)}</span>
            </div>
            <Button variant="secondary" onClick={loadData} disabled={isLoading} className="gap-2">
              {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              刷新数据
            </Button>
          </div>
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <section className="admin-data-panel">
        <div className="admin-panel-toolbar">
          <div className="text-center lg:text-left">
            <p className="admin-section-kicker">会话目录</p>
            <h3 className="mt-2 text-lg font-black tracking-tight text-slate-900">按用户、摘要或 Session 检索</h3>
          </div>

          <div className="flex w-full flex-col gap-3 lg:w-auto lg:flex-row lg:items-center">
            <div className="relative w-full lg:w-[420px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索用户、邮箱、Session 或摘要"
                className="w-full rounded-[22px] border border-white/75 bg-white/72 py-3.5 pl-11 pr-5 text-sm font-semibold text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
              />
            </div>
          </div>
        </div>

        <div className="admin-table-head grid-cols-[minmax(220px,1.15fr)_minmax(280px,1.9fr)_90px_110px_120px_140px_130px]">
          <span>用户</span>
          <span>摘要</span>
          <span>消息数</span>
          <span>Token</span>
          <span>模型/工具</span>
          <span>更新时间</span>
          <span>操作</span>
        </div>

        <div className="min-h-[460px]">
          {isLoading ? (
            <div className="flex h-[460px] items-center justify-center gap-3 text-sm font-bold text-slate-400">
              <Loader2 size={18} className="animate-spin" />
              正在加载会话
            </div>
          ) : items.length > 0 ? (
            items.map((item, index) => (
              <motion.div
                key={item.session_id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: Math.min(index * 0.025, 0.16) }}
                whileHover={{ x: 2 }}
                className="admin-table-row grid grid-cols-1 gap-4 border-b border-slate-100/80 px-5 py-4 text-center xl:grid-cols-[minmax(220px,1.15fr)_minmax(280px,1.9fr)_90px_110px_120px_140px_130px] xl:items-center xl:gap-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-slate-900">{item.user_name || '未知用户'}</p>
                  <p className="mt-1 truncate text-xs font-medium text-slate-500">{item.user_email || item.session_id}</p>
                </div>

                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-slate-900">{item.summary || item.first_message || '暂无摘要'}</p>
                  <p className="mt-1 truncate text-xs font-medium text-slate-500">{item.last_message || '暂无最新消息'}</p>
                </div>

                <div className="text-sm font-black text-slate-900">{formatNumber(item.message_count)}</div>
                <div className="text-sm font-black text-slate-900">{formatNumber(item.total_tokens)}</div>
                <div className="text-sm font-bold text-slate-600">
                  {formatNumber(item.llm_calls)} / {formatNumber(item.tool_calls)}
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-slate-700">{formatApiDateTime(item.updated_at)}</p>
                  <p className="mt-1 text-xs font-medium text-slate-400">{formatLatency(item.avg_latency_ms)}</p>
                </div>

                <div className="flex flex-wrap justify-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => openDetail(item.session_id)}
                    className="gap-2 bg-white/85"
                  >
                    <Eye size={15} />
                    详情
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(item.session_id)}
                    disabled={deletingId === item.session_id}
                    className="h-9 w-9 text-rose-500 hover:bg-rose-50"
                    title="删除会话"
                  >
                    {deletingId === item.session_id ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  </Button>
                </div>
              </motion.div>
            ))
          ) : (
            <div className="flex h-[460px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
                <MessageSquare size={24} />
              </div>
              <p className="text-sm font-black text-slate-600">没有找到会话记录</p>
              <p className="mt-1 text-xs font-medium text-slate-400">新的会话会自动汇总到这里</p>
            </div>
          )}
        </div>

        {total > ITEMS_PER_PAGE && (
          <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
        )}
      </section>

      {typeof document !== 'undefined' && createPortal(
        <AnimatePresence>
          {detailSessionId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="admin-modal-shell"
            onMouseDown={closeDetail}
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }}
              transition={{ duration: 0.22 }}
              onMouseDown={(event) => event.stopPropagation()}
              className="admin-solid-panel admin-modal-panel flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden"
            >
              <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
                <div>
                  <p className="admin-section-kicker">会话详情</p>
                  <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                    {detail?.user_name || detail?.user_email || detailSessionId}
                  </h3>
                  <p className="mt-2 text-xs font-medium text-slate-500">{detail?.session_id || detailSessionId}</p>
                </div>
                <button
                  type="button"
                  onClick={closeDetail}
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="grid flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[340px_minmax(0,1fr)]">
                <div className="overflow-y-auto border-r border-slate-100 bg-white/55 p-6">
                  {detailLoading ? (
                    <div className="flex h-48 items-center justify-center gap-3 text-sm font-bold text-slate-400">
                      <Loader2 size={18} className="animate-spin" />
                      正在加载详情
                    </div>
                  ) : detailError ? (
                    <div className="rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                      {detailError}
                    </div>
                  ) : detail ? (
                    <div className="space-y-4">
                      <div className="rounded-[28px] border border-white/80 bg-white/80 p-5">
                        <p className="admin-section-kicker">摘要</p>
                        <p className="mt-3 text-sm font-medium leading-6 text-slate-600">{detail.summary || '暂无摘要'}</p>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-[22px] border border-white/80 bg-white/80 px-4 py-4">
                          <p className="text-[11px] font-black tracking-[0.16em] text-slate-400">消息数</p>
                          <p className="mt-2 text-2xl font-black text-slate-900">{formatNumber(detail.message_count)}</p>
                        </div>
                        <div className="rounded-[22px] border border-white/80 bg-white/80 px-4 py-4">
                          <p className="text-[11px] font-black tracking-[0.16em] text-slate-400">Token</p>
                          <p className="mt-2 text-2xl font-black text-slate-900">{formatNumber(detail.total_tokens)}</p>
                        </div>
                        <div className="rounded-[22px] border border-white/80 bg-white/80 px-4 py-4">
                          <p className="text-[11px] font-black tracking-[0.16em] text-slate-400">模型调用</p>
                          <p className="mt-2 text-2xl font-black text-slate-900">{formatNumber(detail.llm_calls)}</p>
                        </div>
                        <div className="rounded-[22px] border border-white/80 bg-white/80 px-4 py-4">
                          <p className="text-[11px] font-black tracking-[0.16em] text-slate-400">工具调用</p>
                          <p className="mt-2 text-2xl font-black text-slate-900">{formatNumber(detail.tool_calls)}</p>
                        </div>
                      </div>

                      <div className="rounded-[28px] border border-white/80 bg-white/80 p-5">
                        <p className="admin-section-kicker">会话信息</p>
                        <div className="mt-3 space-y-2 text-sm font-medium text-slate-600">
                          <p>用户：{detail.user_name || '-'}</p>
                          <p>邮箱：{detail.user_email || '-'}</p>
                          <p>创建时间：{formatApiDateTime(detail.created_at)}</p>
                          <p>更新时间：{formatApiDateTime(detail.updated_at)}</p>
                          <p>平均耗时：{formatLatency(detail.avg_latency_ms)}</p>
                          <p>模型：{detail.model_names.length > 0 ? detail.model_names.join(' / ') : '-'}</p>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="overflow-y-auto p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="admin-section-kicker">消息时间线</p>
                      <h4 className="mt-1 text-lg font-black text-slate-900">完整会话内容</h4>
                    </div>
                    {detail && (
                      <div className="rounded-full border border-white/80 bg-white/80 px-3 py-1 text-xs font-black text-slate-500">
                        {detail.messages.length} 条消息
                      </div>
                    )}
                  </div>

                  {detailLoading ? (
                    <div className="flex h-64 items-center justify-center gap-3 text-sm font-bold text-slate-400">
                      <Loader2 size={18} className="animate-spin" />
                      正在加载消息
                    </div>
                  ) : detailError ? (
                    <div className="rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                      {detailError}
                    </div>
                  ) : detail && detail.messages.length > 0 ? (
                    <div className="space-y-3">
                      {detail.messages.map((message) => (
                        <div key={message.id} className="rounded-[24px] border border-white/80 bg-white/82 p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-full border px-3 py-1 text-[11px] font-black ${roleTone(message.role)}`}>
                              {roleLabel(message.role)}
                            </span>
                            <span className="text-xs font-medium text-slate-400">{formatApiDateTime(message.created_at)}</span>
                          </div>
                          <pre className="mt-3 whitespace-pre-wrap break-words text-sm font-medium leading-6 text-slate-700">
                            {message.text || '该消息没有可展示的文本内容。'}
                          </pre>
                        </div>
                      ))}
                    </div>
                  ) : detail ? (
                    <div className="flex h-64 items-center justify-center rounded-[28px] border border-dashed border-slate-200 bg-white/50 text-sm font-bold text-slate-400">
                      这条会话还没有可展示的消息内容
                    </div>
                  ) : null}
                </div>
              </div>
            </motion.div>
          </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
};
