import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw, Save, Users } from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { toast } from 'sonner';
import { toastError } from '../../lib/errors';

/**
 * 用量成本看板 + 配额管理（战线 E-P1，系统改造总方案 8.5.2）。
 *
 * 之前 quota_service 只有环境变量口径、无 API/UI；UsagePanel 只挂在聊天侧栏，
 * 后台无成本/配额/超限用户视图。本面板聚合：
 * - 配额配置编辑（GET/PUT /admin/quota，0 = 关闭）
 * - 今日按用户用量 Top（GET /admin/quota/overview，超限高亮）
 * - 超限用户的运营放行 = 调整全局配额（按 app 维度限流属网站应用化，后置）
 */

type QuotaConfig = {
  source: string;
  daily_token_quota: number;
  updated_at: string | null;
};

type QuotaUserRow = {
  user_id: number | null;
  user_name: string;
  user_email: string | null;
  role: string | null;
  exempt: boolean;
  used_tokens: number;
  events: number;
  quota: number;
  ratio: number | null;
  exceeded: boolean;
};

type QuotaOverview = {
  config: QuotaConfig;
  today: string;
  per_user: QuotaUserRow[];
  exceeded_count: number;
};

const fmtTokens = (n: number | null | undefined): string => {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};

export const QuotaManagement: React.FC = () => {
  const [overview, setOverview] = useState<QuotaOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingQuota, setEditingQuota] = useState<string>('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await apiFetch<QuotaOverview>('/api/v1/admin/quota/overview?top=20');
      setOverview(body);
      setEditingQuota(String(body.config.daily_token_quota));
    } catch (err) {
      setError(toastError(err, '加载配额数据失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveQuota = useCallback(async () => {
    const value = Number(editingQuota);
    if (!Number.isFinite(value) || value < 0) {
      toast.error('配额必须是不小于 0 的整数（0 = 关闭）');
      return;
    }
    setSaving(true);
    try {
      await apiFetch('/api/v1/admin/quota', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ daily_token_quota: Math.round(value) }),
      });
      toast.success(value === 0 ? '配额已关闭（不限制）' : `每日配额已调整为 ${value.toLocaleString()}`);
      void load();
    } catch (err) {
      toast.error(toastError(err, '配额保存失败'));
    } finally {
      setSaving(false);
    }
  }, [editingQuota, load]);

  const cardBase =
    'rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)]">用量与配额</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            每日 Token 配额配置与今日用量分布（超限用户运营视图）
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

      {error && (
        <div className="rounded-xl border border-rose-300/60 bg-rose-50/80 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading && !overview && (
        <div className="h-40 animate-pulse rounded-xl bg-[var(--surface-2)]" aria-busy="true" />
      )}

      {overview && (
        <>
          {/* 配置编辑 */}
          <div className={cardBase}>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                  每用户每日 Token 配额
                </label>
                <input
                  type="number"
                  min={0}
                  value={editingQuota}
                  onChange={(e) => setEditingQuota(e.target.value)}
                  className="mt-1.5 w-52 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2 text-sm text-[var(--foreground)]"
                  aria-label="每日 Token 配额"
                />
                <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                  0 = 关闭配额 · 当前生效来源：{overview.config.source === 'database' ? '数据库（后台配置）' : '环境变量'}
                  {overview.config.updated_at && ` · 更新于 ${new Date(overview.config.updated_at).toLocaleString('zh-CN', { hour12: false })}`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void saveQuota()}
                disabled={saving || editingQuota === String(overview.config.daily_token_quota)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] transition-colors active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Save size={14} />
                {saving ? '保存中…' : '保存'}
              </button>
              <div className="ml-auto text-right">
                <p className="text-xs text-[var(--muted-foreground)]">今日超限用户</p>
                <p className={`mt-0.5 text-2xl font-bold ${overview.exceeded_count > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--foreground)]'}`}>
                  {overview.exceeded_count}
                </p>
              </div>
            </div>
          </div>

          {/* 按用户用量 */}
          <div className={cardBase}>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <Users size={15} /> 今日用量 Top（{overview.today}）
            </h2>
            {overview.per_user.length === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">今日暂无用量记录</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)] text-xs text-[var(--muted-foreground)]">
                      <th className="py-2 pr-3 font-medium">用户</th>
                      <th className="py-2 pr-3 font-medium">角色</th>
                      <th className="py-2 pr-3 font-medium">今日用量</th>
                      <th className="py-2 pr-3 font-medium">占配额</th>
                      <th className="py-2 pr-3 font-medium">调用次数</th>
                      <th className="py-2 font-medium">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.per_user.map((u) => (
                      <tr
                        key={`${u.user_id}`}
                        className={`border-b border-[var(--border-subtle)]/60 last:border-0 ${
                          u.exceeded
                            ? // 超限行：左侧 rose 强调条 + 底色（暗色下也要一眼可辨）
                              'bg-rose-50/70 dark:bg-rose-500/10 shadow-[inset_3px_0_0_0_var(--color-rose-500)]'
                            : ''
                        }`}
                      >
                        <td className="py-2.5 pr-3">
                          <p className="font-medium text-[var(--foreground)]">{u.user_name}</p>
                          {u.user_email && (
                            <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">{u.user_email}</p>
                          )}
                        </td>
                        <td className="py-2.5 pr-3 text-xs text-[var(--muted-foreground)]">
                          {u.role ?? '—'}
                          {u.exempt && <span className="ml-1 text-[10px] text-emerald-600 dark:text-emerald-400">豁免</span>}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-[13px] text-[var(--foreground)]">
                          {fmtTokens(u.used_tokens)}
                        </td>
                        <td className="py-2.5 pr-3">
                          {u.ratio != null ? (
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--surface-2)]">
                                <div
                                  className={`h-full rounded-full ${u.ratio >= 1 ? 'bg-rose-500' : u.ratio >= 0.8 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                  style={{ width: `${Math.min(u.ratio * 100, 100)}%` }}
                                />
                              </div>
                              <span
                                className={`text-[11px] font-semibold ${
                                  u.ratio >= 1
                                    ? 'text-rose-600 dark:text-rose-300'
                                    : u.ratio >= 0.8
                                      ? 'text-amber-600 dark:text-amber-300'
                                      : 'text-[var(--muted-foreground)]'
                                }`}
                              >
                                {Math.round(u.ratio * 100)}%
                              </span>
                            </div>
                          ) : (
                            <span className="text-xs text-[var(--muted-foreground)]">—</span>
                          )}
                        </td>
                        <td className="py-2.5 pr-3 text-xs text-[var(--muted-foreground)]">{u.events}</td>
                        <td className="py-2.5">
                          {u.exceeded ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
                              <AlertTriangle size={11} /> 已超限
                            </span>
                          ) : u.exempt ? (
                            <span className="text-[11px] text-[var(--muted-foreground)]">不受限</span>
                          ) : (
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400">正常</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
