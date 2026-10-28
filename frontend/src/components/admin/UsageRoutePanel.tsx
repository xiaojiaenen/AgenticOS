import { AlertTriangle, Route as RouteIcon } from 'lucide-react';
import type { UsageRoutesData } from '../../services/dashboardService';

/**
 * 用量路由审计面板。
 *
 * 刻意和「用户用量」分开展示，因为两者的统计口径不同：
 * - token 归属永远是**发起请求的用户**（见 DashboardCharts 的用户负载）；
 * - 这个面板回答的是「流量实际落在哪个提供商 / 哪条账号 / 哪个模型上」，
 *   属于排障信息。把两者混成一张表，很容易被读成「某个共享账号用了多少」。
 */

const numberFormatter = new Intl.NumberFormat('zh-CN');

function formatNumber(value: number): string {
  return numberFormatter.format(Math.max(0, Math.round(value || 0)));
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return formatNumber(value);
}

function formatWhen(value: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const EmptyRow = ({ text }: { text: string }) => (
  <div className="px-3 py-6 text-center text-xs text-[var(--muted-foreground)]">{text}</div>
);

export const UsageRoutePanel = ({ data }: { data: UsageRoutesData }) => {
  const { totals, providers, accounts, models } = data;
  // 「配置没生效」的信号：有提供商配置，却有流量走了 .env 兜底或根本没记录路由
  const routeLeak = totals.env_fallback_runs > 0;

  const kpis = [
    { label: '总运行', value: formatNumber(totals.runs), hint: `近 ${data.days} 天` },
    {
      label: '走提供商配置',
      value: formatNumber(
        providers
          .filter((item) => item.provider_slug !== '__env__')
          .reduce((sum, item) => sum + item.runs, 0),
      ),
      hint: '已按配置路由',
    },
    {
      label: '环境变量兜底',
      value: formatNumber(totals.env_fallback_runs),
      hint: routeLeak ? '有流量没走提供商配置' : '无',
    },
    {
      label: '无路由信息',
      value: formatNumber(totals.legacy_runs),
      hint: '迁移前的历史数据',
    },
  ];

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <RouteIcon size={16} className="text-[var(--muted-foreground)]" />
            <h2 className="text-sm font-semibold tracking-tight text-[var(--foreground)]">
              用量路由审计
            </h2>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--muted-foreground)]">
            Token 归属按<strong className="font-semibold text-[var(--foreground)]">发起请求的用户</strong>
            统计（见「用户负载」）。这里只回答流量实际落在哪条路由上，账号是系统级共享池，
            按账号聚合的数字不能当作个人用量。
            {totals.estimated_runs > 0 && (
              <span className="ml-1">
                其中 {formatNumber(totals.estimated_runs)} 次运行的上游未回流 usage，token 为估算值。
              </span>
            )}
          </p>
        </div>
        {routeLeak && (
          <div className="flex items-center gap-1.5 rounded-md border border-amber-300/60 bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
            <AlertTriangle size={12} />
            {formatNumber(totals.env_fallback_runs)} 次运行走了 .env 兜底
          </div>
        )}
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((item) => (
          <div
            key={item.label}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 shadow-sm"
          >
            <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--muted-foreground)]">
              {item.label}
            </p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--foreground)]">
              {item.value}
            </p>
            <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">{item.hint}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
            <h3 className="text-xs font-semibold text-[var(--foreground)]">提供商</h3>
            <span className="text-[11px] text-[var(--muted-foreground)]">按运行次数</span>
          </div>
          <div className="divide-y divide-[var(--border-subtle)]">
            {providers.length === 0 ? (
              <EmptyRow text={`近 ${data.days} 天没有经过提供商的运行`} />
            ) : (
              providers.map((item) => (
                <div
                  key={`${item.provider_slug}-${item.provider_id ?? 'env'}`}
                  className="flex items-center justify-between gap-3 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-[var(--foreground)]">
                      {item.provider_name || item.provider_slug}
                      {item.provider_slug === '__env__' && (
                        <span className="ml-1.5 rounded border border-[var(--border-subtle)] px-1 py-0.5 text-[10px] font-normal text-[var(--muted-foreground)]">
                          环境变量
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                      {formatNumber(item.llm_calls)} 次模型调用 · {formatTokens(item.total_tokens)} tokens
                      {' · '}
                      {formatWhen(item.last_at)}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs font-semibold tabular-nums text-[var(--foreground)]">
                    {formatNumber(item.runs)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
            <h3 className="text-xs font-semibold text-[var(--foreground)]">共享账号池</h3>
            <span className="text-[11px] text-[var(--muted-foreground)]">排障用，非分摊依据</span>
          </div>
          <div className="divide-y divide-[var(--border-subtle)]">
            {accounts.length === 0 ? (
              <EmptyRow text="没有企业网关账号被使用（API Key 型提供商没有账号池）" />
            ) : (
              accounts.map((item) => (
                <div
                  key={`${item.credential_id}`}
                  className="flex items-center justify-between gap-3 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-[var(--foreground)]">
                      {item.account_label || `账号 #${item.credential_id}`}
                      <span className="ml-1.5 text-[10px] font-normal text-[var(--muted-foreground)]">
                        {item.provider_slug}
                      </span>
                    </p>
                    <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                      {formatNumber(item.llm_calls)} 次调用 · {formatWhen(item.last_at)}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs font-semibold tabular-nums text-[var(--foreground)]">
                    {formatNumber(item.runs)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-xs font-semibold text-[var(--foreground)]">实际调用的模型</h3>
          <span className="text-[11px] text-[var(--muted-foreground)]">取自网关实际发出的模型名</span>
        </div>
        <div className="divide-y divide-[var(--border-subtle)]">
          {models.length === 0 ? (
            <EmptyRow text={`近 ${data.days} 天没有模型调用记录`} />
          ) : (
            models.map((item) => (
              <div
                key={item.name}
                className="flex items-center justify-between gap-3 px-4 py-2.5"
              >
                <p className="min-w-0 truncate font-mono text-xs text-[var(--foreground)]">
                  {item.name}
                </p>
                <p className="shrink-0 text-[11px] text-[var(--muted-foreground)]">
                  {formatNumber(item.runs)} 次 · {formatTokens(item.total_tokens)} tokens
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
};
