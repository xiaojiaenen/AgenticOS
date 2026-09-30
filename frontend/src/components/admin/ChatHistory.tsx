/**
 * 聊天记录：TanStack Query 数据层（列表 useQuery + 详情 useInfiniteQuery）
 * + TanStack Table + shadcn Dialog/AlertDialog。
 * 后端 API 不变（services/conversationService.ts）。
 */
import * as React from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  BrainCircuit,
  Eye,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Trash2,
  Wrench,
} from 'lucide-react';
import { DataTable } from './data-table';
import { Pagination } from './Pagination';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { formatApiDateTime } from '@/lib/datetime';
import { cn } from '@/lib/utils';
import {
  AdminConversation,
  AdminConversationDetail,
  AdminConversationDetailMessage,
  deleteConversation,
  getConversationDetail,
  listConversations,
} from '@/services/conversationService';
import { ChatAnalytics } from './ChatAnalytics';

const ITEMS_PER_PAGE = 12;
const DETAIL_MESSAGES_PAGE_SIZE = 20;

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
  if (role === 'tool') return '工具';
  if (role === 'system') return '系统';
  return '消息';
}

function roleTone(role?: string | null): string {
  if (role === 'user') return 'border-indigo-100 bg-indigo-50 text-indigo-700';
  if (role === 'model' || role === 'assistant') return 'border-emerald-100 bg-emerald-50 text-emerald-700';
  if (role === 'tool') return 'border-violet-100 bg-violet-50 text-violet-700';
  if (role === 'system') return 'border-amber-100 bg-amber-50 text-amber-700';
  return 'border-zinc-200 bg-zinc-100 text-zinc-600';
}

function formatJson(value?: Record<string, unknown> | null): string {
  if (!value || Object.keys(value).length === 0) return '{}';
  return JSON.stringify(value, null, 2);
}

function AdminMarkdown({ text }: { text: string }) {
  return (
    <div className="prose prose-sm prose-slate max-w-none prose-p:my-2 prose-pre:my-3 prose-pre:whitespace-pre-wrap prose-pre:break-words prose-code:break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          pre: ({ children }) => (
            <pre className="visible-scrollbar overflow-x-auto rounded-lg border border-zinc-200/70 bg-zinc-950/95 p-4 text-zinc-100 shadow-none">
              {children}
            </pre>
          ),
          code: ({ children, className }) => (
            <code className={className ? `${className} font-mono` : 'rounded-md bg-zinc-100 px-1 py-0.5 font-mono text-zinc-700'}>
              {children}
            </code>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function ToolCallBlock({ message }: { message: AdminConversationDetailMessage }) {
  const toolCalls = message.tool_calls || [];
  const toolResults = message.tool_results || [];
  if (toolCalls.length === 0 && toolResults.length === 0 && !message.reasoning_text) return null;

  return (
    <div className="mt-3 space-y-3">
      {message.reasoning_text && (
        <details className="group rounded-lg border border-zinc-200/80 bg-zinc-50/80 px-4 py-3 [&_summary::-webkit-details-marker]:hidden">
          <summary className="flex cursor-pointer select-none items-center gap-2 text-xs font-semibold tracking-wide text-zinc-500">
            <BrainCircuit size={14} />
            思考过程
          </summary>
          <div className="mt-3 whitespace-pre-wrap break-words border-t border-zinc-200/70 pt-3 text-sm font-medium leading-6 text-zinc-500">
            {message.reasoning_text}
          </div>
        </details>
      )}

      {toolCalls.map((tool) => (
        <details
          key={`${message.id}-call-${tool.id || tool.name}`}
          open
          className="group rounded-lg border border-indigo-100 bg-indigo-50/55 px-4 py-3 [&_summary::-webkit-details-marker]:hidden"
        >
          <summary className="flex cursor-pointer select-none items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <Wrench size={14} className="text-indigo-700" />
              <span className="truncate font-mono text-xs font-semibold uppercase tracking-wide text-indigo-800">
                {tool.name}
              </span>
            </span>
            <span className="rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-indigo-600">调用参数</span>
          </summary>
          <pre className="visible-scrollbar mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-white p-3 text-xs font-medium leading-5 text-zinc-600">
            {formatJson(tool.arguments)}
          </pre>
        </details>
      ))}

      {toolResults.map((result) => {
        const isError = result.status === 'error';
        return (
          <details
            key={`${message.id}-result-${result.tool_call_id || result.name || result.result.slice(0, 12)}`}
            open
            className={cn(
              'group rounded-lg border px-4 py-3 [&_summary::-webkit-details-marker]:hidden',
              isError ? 'border-rose-100 bg-rose-50/70' : 'border-violet-100 bg-violet-50/60',
            )}
          >
            <summary className="flex cursor-pointer select-none items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2">
                <Wrench size={14} className={isError ? 'text-rose-700' : 'text-violet-700'} />
                <span className={cn('truncate text-xs font-semibold tracking-wide', isError ? 'text-rose-800' : 'text-violet-800')}>
                  {result.name || result.tool_call_id || '工具返回结果'}
                </span>
              </span>
              <span className={cn('rounded-full bg-white px-2 py-1 text-[10px] font-semibold', isError ? 'text-rose-600' : 'text-violet-600')}>
                {isError ? '失败' : '结果'}
              </span>
            </summary>
            <pre className="visible-scrollbar mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-white p-3 text-xs font-medium leading-5 text-zinc-700">
              {result.result || '工具没有返回可展示内容。'}
            </pre>
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 会话详情弹窗
// ---------------------------------------------------------------------------

function ConversationDetailDialog({
  sessionId,
  onClose,
}: {
  sessionId: string;
  onClose: () => void;
}) {
  const detailQuery = useInfiniteQuery({
    queryKey: ['admin', 'conversation', sessionId],
    queryFn: ({ pageParam }) =>
      getConversationDetail(sessionId, {
        messagesOffset: pageParam,
        messagesLimit: DETAIL_MESSAGES_PAGE_SIZE,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.messages.length, 0);
      return loaded < lastPage.message_count ? loaded : undefined;
    },
  });

  const detail = detailQuery.data?.pages[0] ?? null;
  const messages: AdminConversationDetailMessage[] =
    detailQuery.data?.pages.flatMap((page) => page.messages) ?? [];

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[90vh] w-[min(1200px,calc(100vw-32px))] max-w-none flex-col overflow-hidden sm:max-w-none">
        <DialogHeader>
          <DialogTitle className="text-left">
            {detail?.user_name || detail?.user_email || sessionId}
          </DialogTitle>
          <DialogDescription className="text-left">
            会话详情 · {detail?.session_id || sessionId}
          </DialogDescription>
        </DialogHeader>

        <div className="grid flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[340px_minmax(0,1fr)]">
          <div className="overflow-y-auto border-zinc-100 p-4 xl:border-r">
            {detailQuery.isLoading ? (
              <div className="flex h-48 items-center justify-center gap-3 text-sm font-medium text-zinc-400">
                <Loader2 size={18} className="animate-spin" />
                正在加载详情
              </div>
            ) : detailQuery.isError ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {(detailQuery.error as Error).message || '会话详情加载失败'}
              </div>
            ) : detail ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">摘要</p>
                  <p className="mt-2 text-sm font-medium leading-6 text-zinc-600">
                    {detail.summary || '暂无摘要'}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: '消息数', value: formatNumber(detail.message_count) },
                    { label: 'Token', value: formatNumber(detail.total_tokens) },
                    { label: '模型调用', value: formatNumber(detail.llm_calls) },
                    { label: '工具调用', value: formatNumber(detail.tool_calls) },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-zinc-200 bg-zinc-50/60 px-3.5 py-3">
                      <p className="text-[11px] font-semibold tracking-wide text-zinc-400">{item.label}</p>
                      <p className="mt-1.5 text-xl font-semibold text-zinc-900">{item.value}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">会话信息</p>
                  <div className="mt-2.5 space-y-2 text-sm font-medium text-zinc-600">
                    <p>用户：{detail.user_name || '-'}</p>
                    <p>邮箱：{detail.user_email || '-'}</p>
                    {detail.agent_profile_name && (
                      <p>
                        智能体：
                        <span className="inline-block rounded-full border border-indigo-200/70 bg-indigo-50/80 px-2.5 py-0.5 text-xs font-medium text-indigo-600">
                          {detail.agent_profile_name}
                        </span>
                      </p>
                    )}
                    <p>创建时间：{formatApiDateTime(detail.created_at)}</p>
                    <p>更新时间：{formatApiDateTime(detail.updated_at)}</p>
                    <p>平均耗时：{formatLatency(detail.avg_latency_ms)}</p>
                    <p>模型：{detail.model_names.length > 0 ? detail.model_names.join(' / ') : '-'}</p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div className="overflow-y-auto p-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">消息时间线</p>
                <h4 className="mt-1 text-base font-semibold text-zinc-900">完整会话内容</h4>
              </div>
              <div className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-500">
                已加载 {messages.length} / {detail?.message_count ?? 0} 条
              </div>
            </div>

            {detailQuery.isLoading ? (
              <div className="flex h-64 items-center justify-center gap-3 text-sm font-medium text-zinc-400">
                <Loader2 size={18} className="animate-spin" />
                正在加载消息
              </div>
            ) : detailQuery.isError ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {(detailQuery.error as Error).message || '会话详情加载失败'}
              </div>
            ) : messages.length > 0 ? (
              <div className="space-y-3">
                {messages.map((message) => (
                  <div key={message.id} className="rounded-lg border border-zinc-200 bg-white p-3.5 shadow-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${roleTone(message.role)}`}>
                        {roleLabel(message.role)}
                      </span>
                      <span className="text-xs font-medium text-zinc-400">
                        {formatApiDateTime(message.created_at)}
                      </span>
                    </div>
                    {message.text ? (
                      <AdminMarkdown text={message.text} />
                    ) : message.tool_results && message.tool_results.length > 0 ? null : (
                      <p className="mt-3 text-sm font-medium leading-6 text-zinc-400">
                        该消息没有可展示的文本内容。
                      </p>
                    )}
                    <ToolCallBlock message={message} />
                  </div>
                ))}
                {detailQuery.hasNextPage && (
                  <div className="pt-2 text-center">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void detailQuery.fetchNextPage()}
                      disabled={detailQuery.isFetchingNextPage}
                      className="gap-2"
                    >
                      {detailQuery.isFetchingNextPage ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : null}
                      加载更多消息
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-white/80 text-sm font-medium text-zinc-400">
                这条会话还没有可展示的消息内容
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const ChatHistory = () => {
  const queryClient = useQueryClient();

  const [currentPage, setCurrentPage] = React.useState(1);
  const [searchInput, setSearchInput] = React.useState('');
  const [searchQuery, setSearchQuery] = React.useState('');
  const [showAnalytics, setShowAnalytics] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  const [detailSessionId, setDetailSessionId] = React.useState<string | null>(null);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(searchInput);
      setCurrentPage(1);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const conversationsQuery = useQuery({
    queryKey: ['admin', 'conversations', currentPage, searchQuery],
    queryFn: () =>
      listConversations({
        search: searchQuery,
        offset: (currentPage - 1) * ITEMS_PER_PAGE,
        limit: ITEMS_PER_PAGE,
      }),
    placeholderData: (prev) => prev,
  });

  const items = conversationsQuery.data?.items ?? [];
  const total = conversationsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteConversation(sessionId),
    onSuccess: () => {
      toast.success('会话已删除');
      setDeletingId(null);
      if (detailSessionId !== null) setDetailSessionId(null);
      if (items.length === 1 && currentPage > 1) {
        setCurrentPage((page) => page - 1);
      } else {
        void queryClient.invalidateQueries({ queryKey: ['admin', 'conversations'] });
      }
    },
    onError: (err: Error) => {
      toast.error(err.message || '删除对话失败');
      setDeletingId(null);
    },
  });

  const pageTotals = {
    tokens: items.reduce((sum, item) => sum + item.total_tokens, 0),
    calls: items.reduce((sum, item) => sum + item.llm_calls, 0),
    tools: items.reduce((sum, item) => sum + item.tool_calls, 0),
  };

  const columns = React.useMemo<ColumnDef<AdminConversation, unknown>[]>(
    () => [
      {
        id: 'user',
        header: '用户',
        cell: ({ row }) => {
          const item = row.original;
          return (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-900">
                {item.user_name || '未知用户'}
              </p>
              <p className="mt-0.5 truncate text-xs font-medium text-zinc-500">
                {item.user_email || item.session_id}
              </p>
              {item.agent_profile_name && (
                <span className="mt-1 inline-block max-w-full truncate rounded-full border border-indigo-200/70 bg-indigo-50/80 px-2.5 py-0.5 text-[11px] font-medium text-indigo-600">
                  {item.agent_profile_name}
                </span>
              )}
            </div>
          );
        },
      },
      {
        id: 'summary',
        header: '摘要',
        enableSorting: false,
        cell: ({ row }) => {
          const item = row.original;
          return (
            <div className="min-w-0">
              <p className="max-w-[320px] truncate text-sm font-semibold text-zinc-900">
                {item.summary || item.first_message || '暂无摘要'}
              </p>
              <p className="mt-0.5 max-w-[320px] truncate text-xs font-medium text-zinc-500">
                {item.last_message || '暂无最新消息'}
              </p>
            </div>
          );
        },
      },
      {
        accessorKey: 'message_count',
        header: '消息数',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-900">{formatNumber(Number(getValue()))}</span>
        ),
      },
      {
        accessorKey: 'total_tokens',
        header: 'Token',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-900">{formatNumber(Number(getValue()))}</span>
        ),
      },
      {
        id: 'calls',
        header: '模型/工具',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm font-medium text-zinc-600">
            {formatNumber(row.original.llm_calls)} / {formatNumber(row.original.tool_calls)}
          </span>
        ),
      },
      {
        accessorKey: 'updated_at',
        header: '更新时间',
        cell: ({ row }) => (
          <div>
            <p className="text-sm font-medium text-zinc-700">{formatApiDateTime(row.original.updated_at)}</p>
            <p className="mt-0.5 text-xs font-medium text-zinc-400">{formatLatency(row.original.avg_latency_ms)}</p>
          </div>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const item = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setDetailSessionId(item.session_id)}
              >
                <Eye size={14} />
                详情
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setDeletingId(item.session_id)}
                className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                title="删除会话"
              >
                <Trash2 size={15} />
              </Button>
            </div>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="聊天记录"
        title="会话列表"
        actions={
          <>
            <KpiPill label="共" value={total} />
            <KpiPill label="Token" value={formatNumber(pageTotals.tokens)} />
            <KpiPill
              label="模型/工具"
              value={`${formatNumber(pageTotals.calls)}/${formatNumber(pageTotals.tools)}`}
            />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void conversationsQuery.refetch()}
              disabled={conversationsQuery.isFetching}
            >
              {conversationsQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
          </>
        }
      />

      {conversationsQuery.isError ? (
        <ErrorBanner
          message={(conversationsQuery.error as Error).message || '对话数据加载失败'}
        />
      ) : null}

      {/* Analytics toggle */}
      <div className="flex items-center gap-2">
        <Button
          variant={showAnalytics ? 'default' : 'outline'}
          size="sm"
          onClick={() => setShowAnalytics((prev) => !prev)}
        >
          {showAnalytics ? '隐藏分析' : '数据分析'}
        </Button>
      </div>

      {showAnalytics && <ChatAnalytics timeRange={14} />}

      <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
        <div className="flex flex-col gap-2.5 border-b border-zinc-200/80 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-indigo-600">
              会话目录
            </p>
            <h3 className="mt-1 text-base font-semibold tracking-tight text-zinc-900">
              按用户、摘要或 Session 检索
            </h3>
          </div>
          <div className="relative lg:w-[380px]">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
              size={16}
            />
            <Input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="搜索用户、邮箱、Session 或摘要"
              className="pl-9"
            />
          </div>
        </div>

        <DataTable
          columns={columns}
          data={items}
          isLoading={conversationsQuery.isLoading}
          skeletonRows={8}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg border border-zinc-200 bg-white text-zinc-400 shadow-sm">
                <MessageSquare size={20} />
              </div>
              <p className="text-sm font-semibold text-zinc-600">没有找到会话记录</p>
              <p className="mt-1 text-xs font-medium text-zinc-400">新的会话会自动汇总到这里</p>
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

      {detailSessionId && (
        <ConversationDetailDialog
          sessionId={detailSessionId}
          onClose={() => setDetailSessionId(null)}
        />
      )}

      <AlertDialog open={deletingId !== null} onOpenChange={(next) => !next && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除会话</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除这条会话及其统计记录？该操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingId) deleteMutation.mutate(deletingId);
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

// 保留类型引用，避免未使用告警
export type { AdminConversationDetail };
