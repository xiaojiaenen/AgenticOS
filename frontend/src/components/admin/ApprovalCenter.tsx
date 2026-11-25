import React, { useCallback, useEffect, useState } from 'react';
import { Check, Clock, Globe, FileText, RefreshCw, ShieldAlert, X } from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { toast } from 'sonner';
import { toastError } from '../../lib/errors';

/**
 * 统一审批中心（战线 E-P1，系统改造总方案 8.5.4）。
 *
 * 聚合三类待办（原先分散在部署页 / 发布页 / 会话内，无统一视图与计数）：
 * - 网站部署审批（website_deploys）
 * - 作品发布审批（published_items）
 * - 智能体工具审批（agent tool approvals）
 * 本面板提供统一待办视图与计数角标；逐条决策沿用既有端点（部署/发布各自
 * 的审批 API），复杂操作跳转对应面板完成。
 */

type UnifiedPending = {
  counts: {
    website_deploys: number;
    published_items: number;
    tool_approvals: number;
    total: number;
  };
  website_deploys: Array<Record<string, unknown>>;
  published_items: Array<Record<string, unknown>>;
  tool_approvals: Array<Record<string, unknown>>;
};

const num = (v: unknown): string => (v == null ? '—' : String(v));

const timeOf = (v: unknown): string => {
  if (!v) return '—';
  try {
    return new Date(String(v)).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return String(v);
  }
};

export const ApprovalCenter: React.FC = () => {
  const [data, setData] = useState<UnifiedPending | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [decided, setDecided] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await apiFetch<UnifiedPending>('/api/v1/admin/approvals/pending');
      setData(body);
    } catch (err) {
      setError(toastError(err, '加载待审批列表失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const decidePublished = useCallback(
    async (itemId: unknown, decision: 'approved' | 'rejected') => {
      if (itemId == null) return;
      const key = `pub-${String(itemId)}`;
      setDecided((prev) => ({ ...prev, [key]: true }));
      try {
        await apiFetch(`/api/v1/admin/published-items/${String(itemId)}/decision`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: decision }),
        });
        toast.success(decision === 'approved' ? '发布已批准' : '发布已拒绝');
        void load();
      } catch (err) {
        setDecided((prev) => ({ ...prev, [key]: false }));
        toast.error(toastError(err, '审批提交失败'));
      }
    },
    [load],
  );

  const cardBase =
    'rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm';
  const btnBase =
    'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors active:scale-95 disabled:cursor-not-allowed disabled:opacity-60';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)]">审批中心</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            聚合网站部署、作品发布与智能体工具审批的待办事项
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

      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: '待办总数', value: data.counts.total },
            { label: '网站部署', value: data.counts.website_deploys },
            { label: '作品发布', value: data.counts.published_items },
            { label: '工具审批', value: data.counts.tool_approvals },
          ].map((c) => (
            <div key={c.label} className={cardBase}>
              <p className="text-xs text-[var(--muted-foreground)]">{c.label}</p>
              <p className="mt-1 text-2xl font-bold text-[var(--foreground)]">{c.value}</p>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-300/60 bg-rose-50/80 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="h-40 animate-pulse rounded-xl bg-[var(--surface-2)]" aria-busy="true" />
      )}

      {data && (
        <div className="space-y-4">
          {/* 网站部署 */}
          <section className={cardBase}>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <Globe size={15} /> 网站部署待审批
              <span className="rounded-full bg-[var(--surface-3)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">
                {data.counts.website_deploys}
              </span>
            </h2>
            {data.website_deploys.length === 0 ? (
              <p className="mt-3 text-xs text-[var(--muted-foreground)]">暂无待审批部署。</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {data.website_deploys.slice(0, 8).map((d, i) => (
                  <li
                    key={`deploy-${i}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="min-w-0 truncate font-medium text-[var(--foreground)]">
                        {num((d as Record<string, unknown>).project_slug)}
                      </span>
                      <span
                        className="min-w-0 truncate text-[var(--muted-foreground)]"
                        title={`会话 ${num((d as Record<string, unknown>).session_id)}`}
                      >
                        会话 {num((d as Record<string, unknown>).session_id).slice(0, 8)}…
                      </span>
                    </span>
                    <span className="text-[var(--muted-foreground)]">
                      申请于 {timeOf((d as Record<string, unknown>).created_at ?? (d as Record<string, unknown>).requested_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-[11px] text-[var(--muted-foreground)]">
              完整审批（预览/复审）请前往「部署」面板。
            </p>
          </section>

          {/* 作品发布 */}
          <section className={cardBase}>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <FileText size={15} /> 作品发布待审批
              <span className="rounded-full bg-[var(--surface-3)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">
                {data.counts.published_items}
              </span>
            </h2>
            {data.published_items.length === 0 ? (
              <p className="mt-3 text-xs text-[var(--muted-foreground)]">暂无待审批发布。</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {data.published_items.slice(0, 8).map((p) => {
                  const item = p as Record<string, unknown>;
                  const key = `pub-${String(item.id)}`;
                  return (
                    <li
                      key={key}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs"
                    >
                      <span className="min-w-0 truncate font-medium text-[var(--foreground)]">
                        {num(item.title)} · {num(item.kind)}
                      </span>
                      <span className="flex items-center gap-2 text-[var(--muted-foreground)]">
                        {timeOf(item.created_at)}
                        <button
                          type="button"
                          disabled={Boolean(decided[key])}
                          onClick={() => void decidePublished(item.id, 'approved')}
                          className={`${btnBase} bg-emerald-600 text-white hover:bg-emerald-700`}
                        >
                          <Check size={12} /> 批准
                        </button>
                        <button
                          type="button"
                          disabled={Boolean(decided[key])}
                          onClick={() => void decidePublished(item.id, 'rejected')}
                          className={`${btnBase} border border-rose-200 bg-[var(--surface-1)] text-rose-600 dark:border-rose-500/40`}
                        >
                          <X size={12} /> 拒绝
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* 工具审批 */}
          <section className={cardBase}>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <ShieldAlert size={15} /> 智能体工具审批
              <span className="rounded-full bg-[var(--surface-3)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">
                {data.counts.tool_approvals}
              </span>
            </h2>
            {data.tool_approvals.length === 0 ? (
              <p className="mt-3 text-xs text-[var(--muted-foreground)]">
                暂无等待审批的工具调用。用户在对应会话的审批面板处理。
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {data.tool_approvals.slice(0, 8).map((t) => {
                  const item = t as Record<string, unknown>;
                  return (
                    <li
                      key={`tool-${String(item.approval_id)}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs"
                    >
                      <span className="min-w-0 truncate font-mono font-medium text-[var(--foreground)]">
                        {num(item.tool_name)}
                      </span>
                      <span className="flex min-w-0 items-center gap-2 text-[var(--muted-foreground)]">
                        <Clock size={12} className="flex-shrink-0" />
                        <span className="flex-shrink-0">{timeOf(item.created_at)}</span>
                        {/* 会话 ID 截断展示（8 位前缀），hover title 看全量 —— 信息密度让位给工具名 */}
                        <span className="min-w-0 truncate" title={`会话 ${num(item.session_id)}`}>
                          会话 {num(item.session_id).slice(0, 8)}…
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
