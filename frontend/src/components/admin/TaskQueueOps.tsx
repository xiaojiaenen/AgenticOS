import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Clock, Cpu, Database, ListFilter, RefreshCw, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { toastError } from '../../lib/errors';
import { apiV1, unwrap } from '../../services/openapiClient';

/**
 * 任务队列运维台（战线 E-P1，系统改造总方案 8.5.3）。
 *
 * 之前 tasks.py 只有单任务状态查询，后台无队列列表/失败任务/重试入口，
 * 队列健康只能看日志。本面板聚合：
 * - 队列深度 + 近期任务状态分布（GET /tasks/stats）
 * - 任务列表（提交时间倒序 + 状态过滤 + 任务名过滤，GET /tasks）
 * - 单任务重试（POST /tasks/{id}/retry，CAP_DANGEROUS）
 *
 * 任务元数据来自提交时登记的 Redis 注册表（task_queue.record_task_submission，
 * TTL 7 天、上限 500 条）；审计写入类日志投递任务不入索引（高频非作业）。
 */

type QueueTask = {
  task_id: string;
  name: string;
  submitted_at: number;
  user_id: number | null;
  kwargs: Record<string, unknown>;
  status: string;
  error: string | null;
  age_seconds: number | null;
};

type QueueListResponse = {
  items: QueueTask[];
  total_indexed: number;
};

type QueueStats = {
  broker: string;
  queue_depth: number | null;
  recent: Record<string, number>;
  recent_window: number;
};

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
  failed: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300',
  pending: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
  unknown: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-500/10 dark:text-zinc-300',
};

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  pending: '进行中',
  unknown: '未知',
};

const timeOf = (epochSeconds: unknown): string => {
  if (!epochSeconds) return '—';
  try {
    return new Date(Number(epochSeconds) * 1000).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return String(epochSeconds);
  }
};

const shortKwargs = (kwargs: Record<string, unknown>): string => {
  const entries = Object.entries(kwargs || {});
  if (!entries.length) return '—';
  return entries
    .map(([k, v]) => `${k}=${String(v).slice(0, 40)}`)
    .join(' · ')
    .slice(0, 120);
};

export const TaskQueueOps: React.FC = () => {
  const [list, setList] = useState<QueueListResponse | null>(null);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [nameFilter, setNameFilter] = useState<string>('');
  const [retrying, setRetrying] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (statusFilter) params.set('status_filter', statusFilter);
      if (nameFilter.trim()) params.set('name_filter', nameFilter.trim());
      // openapi-fetch 试点（2.2）：类型从 api-schema.ts 端到端对齐
      const [listBody, statsBody] = await Promise.all([
        unwrap(
          apiV1.GET('/api/v1/tasks', {
            params: { query: {
              limit: 100,
              ...(statusFilter ? { status_filter: statusFilter } : {}),
              ...(nameFilter.trim() ? { name_filter: nameFilter.trim() } : {}),
            } },
          }),
          '加载任务列表失败',
        ),
        unwrap(apiV1.GET('/api/v1/tasks/stats'), '加载队列统计失败'),
      ]);
      setList(listBody as unknown as QueueListResponse);
      setStats(statsBody as unknown as QueueStats);
    } catch (err) {
      setError(toastError(err, '加载任务队列数据失败'));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, nameFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const retry = useCallback(
    async (taskId: string) => {
      setRetrying((prev) => ({ ...prev, [taskId]: true }));
      try {
        const body = await unwrap(
          apiV1.POST('/api/v1/tasks/{task_id}/retry', {
            params: { path: { task_id: taskId } },
          }),
          '重试失败',
        );
        toast.success(`已重新投递 ${body.name}（新任务 ${body.task_id.slice(0, 8)}…）`);
        setConfirming(null);
        void load();
      } catch (err) {
        toast.error(toastError(err, '重试失败'));
      } finally {
        setRetrying((prev) => ({ ...prev, [taskId]: false }));
      }
    },
    [load],
  );

  const recentChips = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.recent).map(([status, count]) => ({
      status,
      count,
      label: STATUS_LABELS[status] ?? status,
      cls: STATUS_STYLES[status] ?? STATUS_STYLES.unknown,
    }));
  }, [stats]);

  const cardBase =
    'rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm';
  const chipBase = 'rounded-full px-2.5 py-1 text-[11px] font-semibold';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)]">任务队列</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            重计算任务（PPT 导出 / 网站构建 / 知识编译）的队列健康与重试
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* 顶栏：队列深度 + 状态分布 */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className={cardBase}>
            <p className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
              <Database size={12} /> 队列深度
            </p>
            <p className="mt-1 text-2xl font-bold text-[var(--foreground)]">
              {stats.queue_depth ?? '—'}
            </p>
          </div>
          {recentChips.map((c) => (
            <div key={c.status} className={cardBase}>
              <p className="text-xs text-[var(--muted-foreground)]">近期{c.label}</p>
              <p className="mt-1 text-2xl font-bold text-[var(--foreground)]">{c.count}</p>
              <span className={`mt-1 inline-block ${c.cls} ${chipBase}`}>{c.status}</span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-300/60 bg-rose-50/80 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading && !list && (
        <div className="h-40 animate-pulse rounded-xl bg-[var(--surface-2)]" aria-busy="true" />
      )}

      {list && (
        <div className={cardBase}>
          {/* 过滤栏 */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <ListFilter size={15} className="text-[var(--muted-foreground)]" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-2.5 py-1.5 text-sm text-[var(--foreground)]"
              aria-label="按状态过滤"
            >
              <option value="">全部状态</option>
              <option value="pending">进行中</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
              <option value="unknown">未知</option>
            </select>
            <input
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
              placeholder="按任务名过滤…"
              className="w-48 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-2.5 py-1.5 text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]"
              aria-label="按任务名过滤"
            />
            <span className="ml-auto text-xs text-[var(--muted-foreground)]">
              索引 {list.total_indexed} 条 · 显示 {list.items.length} 条
            </span>
          </div>

          {list.items.length === 0 ? (
            // 空态撑起视口剩余高度：卡片贴住页底而不是孤悬半空（重心失衡）
            <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 text-sm text-[var(--muted-foreground)]">
              <Cpu size={32} className="opacity-40" />
              <p>没有匹配的任务</p>
              <p className="text-xs opacity-70">注册表 TTL 7 天 · 仅记录重计算作业（PPT 导出 / 网站构建 / 知识编译）</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-xs text-[var(--muted-foreground)]">
                    <th className="py-2 pr-3 font-medium">任务</th>
                    <th className="py-2 pr-3 font-medium">状态</th>
                    <th className="py-2 pr-3 font-medium">提交时间</th>
                    <th className="py-2 pr-3 font-medium">归属</th>
                    <th className="py-2 pr-3 font-medium">参数</th>
                    <th className="py-2 font-medium text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((t) => (
                    <tr key={t.task_id} className="border-b border-[var(--border-subtle)]/60 last:border-0">
                      <td className="py-2.5 pr-3">
                        <p className="font-medium text-[var(--foreground)]">{t.name}</p>
                        <p className="mt-0.5 font-mono text-[11px] text-[var(--muted-foreground)]">
                          {t.task_id.slice(0, 14)}…
                        </p>
                      </td>
                      <td className="py-2.5 pr-3">
                        <span className={`${chipBase} ${STATUS_STYLES[t.status] ?? STATUS_STYLES.unknown}`}>
                          {STATUS_LABELS[t.status] ?? t.status}
                        </span>
                        {t.status === 'failed' && t.error && (
                          <p className="mt-1 max-w-56 truncate text-[11px] text-rose-600 dark:text-rose-400" title={t.error}>
                            {t.error}
                          </p>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-[var(--muted-foreground)]">
                        <span className="inline-flex items-center gap-1">
                          <Clock size={11} /> {timeOf(t.submitted_at)}
                        </span>
                        {t.age_seconds != null && (
                          <p className="mt-0.5">{t.age_seconds < 3600 ? `${Math.floor(t.age_seconds / 60)} 分钟前` : `${Math.floor(t.age_seconds / 3600)} 小时前`}</p>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-[var(--muted-foreground)]">
                        {t.user_id != null ? `用户 #${t.user_id}` : '系统'}
                      </td>
                      <td className="max-w-64 py-2.5 pr-3">
                        <p className="truncate font-mono text-[11px] text-[var(--muted-foreground)]" title={shortKwargs(t.kwargs)}>
                          {shortKwargs(t.kwargs)}
                        </p>
                      </td>
                      <td className="py-2.5 text-right">
                        {t.status === 'failed' || t.status === 'completed' ? (
                          confirming === t.task_id ? (
                            <span className="inline-flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => void retry(t.task_id)}
                                disabled={retrying[t.task_id]}
                                className="inline-flex items-center gap-1 rounded-full bg-rose-600 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-rose-700 active:scale-95 disabled:opacity-60"
                              >
                                <AlertTriangle size={12} />
                                {retrying[t.task_id] ? '投递中…' : '确认重投'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirming(null)}
                                className="rounded-full px-2 py-1.5 text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                              >
                                取消
                              </button>
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setConfirming(t.task_id)}
                              className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] active:scale-95"
                            >
                              <RotateCcw size={12} /> 重试
                            </button>
                          )
                        ) : (
                          <span className="text-xs text-[var(--muted-foreground)]">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
