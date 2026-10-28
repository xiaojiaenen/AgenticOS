import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, BarChart3, Coins, MessageSquare, Sparkles, Wrench } from 'lucide-react';
import { getMyUsage, type MyUsageData } from '../../services/dashboardService';
import { cn } from '../../lib/utils';
import { EmptyState } from '../ui/EmptyState';
import { ListSkeleton } from '../ui/Skeletons';
import { ErrorBanner } from '../admin/shared';

/**
 * 「我的用量」面板。
 *
 * 口径说明（界面上也要说清楚）：这里的数字**按人算** —— 谁发起的对话算谁的。
 * 后端还有一套按上游账号聚合的视图，但企业网关的账号是系统级共享池，
 * 按账号算出来的数字对任何个体都不成立，所以用户侧不展示、也不暴露账号信息。
 *
 * 趋势图用纯 CSS 画（flex + 高度百分比），不引图表库：柱状趋势在 14~30 根
 * 的粒度下 CSS 完全够用，少一个依赖就少一处体积与主题适配的负担。
 */

const RANGE_OPTIONS = [
  { days: 7, label: '近 7 天' },
  { days: 14, label: '近 14 天' },
  { days: 30, label: '近 30 天' },
];

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function formatFull(value: number): string {
  return value.toLocaleString('zh-CN');
}

function KpiCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3.5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-center gap-2 text-[var(--muted-foreground)]">
        <span className="flex size-6 items-center justify-center rounded-md bg-[var(--surface-2)] text-[var(--foreground)]">
          {icon}
        </span>
        <span className="text-[11px] font-medium tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight text-[var(--foreground)]">
        {value}
      </p>
      {hint ? <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

function UsageTrend({ data }: { data: MyUsageData }) {
  const points = data.daily;
  const max = Math.max(1, ...points.map((p) => p.tokens));

  return (
    <div>
      <div className="flex items-end gap-[3px] rounded-lg bg-[var(--surface-2)]/50 px-3 pb-2 pt-4" style={{ height: 132 }}>
        {points.map((point) => {
          const ratio = point.tokens / max;
          return (
            <div
              key={point.date}
              className="group relative flex-1"
              style={{ height: '100%' }}
            >
              <div
                className="absolute bottom-0 w-full rounded-t-[3px] bg-[var(--foreground)]/15 transition-all duration-300 group-hover:bg-[var(--foreground)]/30"
                style={{ height: `${Math.max(ratio * 100, point.tokens > 0 ? 4 : 1.5)}%` }}
              />
              {/* 悬停提示 */}
              <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1 text-[11px] shadow-lg opacity-0 transition-opacity group-hover:opacity-100">
                <span className="font-medium text-[var(--foreground)]">{formatFull(point.tokens)}</span>
                <span className="ml-1.5 text-[var(--muted-foreground)]">
                  {point.date.slice(5)} · {point.runs} 次
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-[var(--muted-foreground)]">
        <span>{points[0]?.date.slice(5) ?? ''}</span>
        <span>{points[points.length - 1]?.date.slice(5) ?? ''}</span>
      </div>
    </div>
  );
}

export const UsagePanel: React.FC = () => {
  const [days, setDays] = React.useState(14);

  const query = useQuery({
    queryKey: ['my-usage', days],
    queryFn: () => getMyUsage(days),
    staleTime: 60_000,
  });

  const data = query.data;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
            My Usage
          </p>
          <h3 className="mt-0.5 text-base font-semibold tracking-tight text-[var(--foreground)]">
            我的用量
          </h3>
        </div>
        <div
          className="flex shrink-0 items-center gap-0.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-0.5"
          role="group"
          aria-label="统计时间范围"
        >
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.days}
              type="button"
              onClick={() => setDays(option.days)}
              aria-pressed={days === option.days}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs font-medium transition-all',
                'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
                days === option.days
                  ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {query.isError ? (
        <ErrorBanner
          message="用量数据加载失败"
          onRetry={() => void query.refetch()}
        />
      ) : query.isLoading || !data ? (
        <ListSkeleton rows={3} columns={4} />
      ) : data.runs === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-1)]">
          <EmptyState
            icon={<Activity className="size-5" />}
            title="这段时间还没有用量记录"
            description="发起一次对话后，这里会显示你的 token 消耗与调用次数。"
          />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            <KpiCard
              icon={<Coins className="size-3.5" />}
              label="总 Token"
              value={formatTokens(data.total_tokens)}
              hint={`输入 ${formatTokens(data.input_tokens)} · 输出 ${formatTokens(data.output_tokens)}`}
            />
            <KpiCard
              icon={<MessageSquare className="size-3.5" />}
              label="对话次数"
              value={formatFull(data.runs)}
              hint={`${formatFull(data.llm_calls)} 次模型调用`}
            />
            <KpiCard
              icon={<Wrench className="size-3.5" />}
              label="工具调用"
              value={formatFull(data.tool_calls)}
              hint="按次累计"
            />
            <KpiCard
              icon={<Sparkles className="size-3.5" />}
              label="涉及模型"
              value={formatFull(data.models.length)}
              hint={data.models[0] ? `主要使用 ${data.models[0].name}` : undefined}
            />
          </div>

          {data.estimated_runs > 0 ? (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
              其中 {data.estimated_runs} 次对话的 token 为估算值（上游未回传精确用量），
              与实际计费可能有出入。
            </p>
          ) : null}

          <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <BarChart3 size={15} className="text-[var(--muted-foreground)]" />
              <h4 className="text-sm font-semibold text-[var(--foreground)]">每日消耗</h4>
            </div>
            <UsageTrend data={data} />
          </section>

          <div className="grid gap-3 lg:grid-cols-2">
            <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
              <h4 className="mb-3 text-sm font-semibold text-[var(--foreground)]">按模型</h4>
              {data.models.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--muted-foreground)]">暂无数据</p>
              ) : (
                <ul className="space-y-2.5">
                  {data.models.map((model) => {
                    const ratio = data.total_tokens > 0 ? model.tokens / data.total_tokens : 0;
                    return (
                      <li key={model.name}>
                        <div className="flex items-baseline justify-between gap-3 text-xs">
                          <span className="truncate font-medium text-[var(--foreground)]">
                            {model.name}
                          </span>
                          <span className="shrink-0 tabular-nums text-[var(--muted-foreground)]">
                            {formatFull(model.tokens)} · {model.runs} 次
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--surface-2)]">
                          <div
                            className="h-full rounded-full bg-[var(--foreground)]/25"
                            style={{ width: `${Math.max(ratio * 100, 2)}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
              <h4 className="mb-3 text-sm font-semibold text-[var(--foreground)]">最近会话</h4>
              {data.sessions.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--muted-foreground)]">暂无数据</p>
              ) : (
                <ul className="space-y-2">
                  {data.sessions.map((session) => (
                    <li
                      key={session.session_id}
                      className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-xs transition-colors hover:bg-[var(--surface-2)]"
                    >
                      <span className="truncate font-mono text-[11px] text-[var(--foreground)]">
                        {session.session_id}
                      </span>
                      <span className="shrink-0 tabular-nums text-[var(--muted-foreground)]">
                        {formatFull(session.tokens)} · {session.runs} 次
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
};
