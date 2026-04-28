import React from 'react';
import {
  Activity,
  ArrowUpRight,
  Clock3,
  MessageSquare,
  MousePointerClick,
  Sparkles,
  Users,
} from 'lucide-react';
import { DashboardSummary } from '../../services/dashboardService';

interface DashboardStatsProps {
  summary: DashboardSummary;
}

function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatTokenNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs <= 10000) return `${value}`;
  if (abs >= 1e12) return `${(value / 1e12).toFixed(abs >= 1e13 ? 0 : 1)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(abs >= 1e10 ? 0 : 1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(abs >= 1e4 ? 0 : 1)}K`;
  return `${value}`;
}

function formatLatency(value: number): string {
  if (!value) return '0 ms';
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${value} ms`;
}

function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

function ratio(value: number, total: number): number {
  if (!total) return 0;
  return Math.max(0, Math.min(100, (value / total) * 100));
}

function MetricRail({
  label,
  value,
  percent,
  gradient,
}: {
  label: string;
  value: string;
  percent: number;
  gradient: string;
}) {
  return (
    <div className="rounded-[22px] border border-white/70 bg-white/42 px-4 py-4 backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-black tracking-[0.18em] text-slate-500">{label}</span>
        <span className="text-sm font-black text-slate-900">{value}</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/55">
        <div className={`h-full rounded-full ${gradient}`} style={{ width: `${Math.max(percent, 6)}%` }} />
      </div>
    </div>
  );
}

function SignalTile({
  label,
  value,
  meta,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  meta: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accent: string;
}) {
  return (
    <div className={`relative overflow-hidden rounded-[28px] border border-white/70 px-5 py-5 shadow-[0_22px_48px_rgba(15,23,42,0.08)] ${accent}`}>
      <div className="absolute inset-x-0 top-0 h-px bg-white/70" />
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-black tracking-[0.18em] text-slate-600">{label}</p>
          <p className="mt-3 text-3xl font-black tracking-tight text-slate-950">{value}</p>
          <p className="mt-2 text-sm font-semibold leading-6 text-slate-600">{meta}</p>
        </div>
        <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-2xl border border-white/80 bg-white/55 text-slate-900">
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
}

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
  const activeRate = ratio(summary.active_users, summary.total_users);
  const toolAssistRate = ratio(summary.tool_calls, summary.tool_calls + summary.llm_calls);
  const outputShare = ratio(summary.output_tokens, summary.total_tokens);
  const avgTokensPerSession = summary.total_sessions > 0 ? Math.round(summary.total_tokens / summary.total_sessions) : 0;
  const avgRunsPerSession = summary.total_sessions > 0 ? (summary.total_runs / summary.total_sessions).toFixed(1) : '0.0';
  const quickSignals = [
    {
      label: '输入 Token',
      value: formatTokenNumber(summary.input_tokens),
    },
    {
      label: '输出 Token',
      value: formatTokenNumber(summary.output_tokens),
    },
    {
      label: '每用户会话',
      value: summary.total_users > 0 ? (summary.total_sessions / summary.total_users).toFixed(1) : '0.0',
    },
    {
      label: '每次运行工具',
      value: summary.total_runs > 0 ? (summary.tool_calls / summary.total_runs).toFixed(2) : '0.00',
    },
  ];

  const signalTiles = [
    {
      label: '模型调用',
      value: formatNumber(summary.llm_calls),
      meta: `工具协同 ${formatPercent(toolAssistRate)}`,
      icon: Activity,
      accent: 'bg-[linear-gradient(135deg,rgba(16,185,129,0.28),rgba(255,255,255,0.72),rgba(6,182,212,0.16))]',
    },
    {
      label: '平均耗时',
      value: formatLatency(summary.avg_latency_ms),
      meta: '按单次运行统计',
      icon: Clock3,
      accent: 'bg-[linear-gradient(135deg,rgba(248,113,113,0.18),rgba(255,255,255,0.76),rgba(251,191,36,0.18))]',
    },
    {
      label: 'Token 总量',
      value: formatTokenNumber(summary.total_tokens),
      meta: `输入 ${formatTokenNumber(summary.input_tokens)} / 输出 ${formatTokenNumber(summary.output_tokens)}`,
      icon: Sparkles,
      accent: 'bg-[linear-gradient(135deg,rgba(139,92,246,0.22),rgba(255,255,255,0.72),rgba(59,130,246,0.15))]',
    },
    {
      label: '工具调用',
      value: formatNumber(summary.tool_calls),
      meta: summary.tool_calls > 0 ? '已形成工具链路' : '暂未触发工具调用',
      icon: MousePointerClick,
      accent: 'bg-[linear-gradient(135deg,rgba(251,191,36,0.22),rgba(255,255,255,0.76),rgba(244,114,182,0.14))]',
    },
  ];

  return (
    <section className="relative overflow-hidden rounded-[38px] border border-white/65 bg-white/40 shadow-[0_30px_90px_rgba(15,23,42,0.1)] ring-1 ring-white/35 backdrop-blur-[28px]">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-14 top-0 h-48 w-48 rounded-full bg-cyan-300/35 blur-3xl" />
        <div className="absolute right-0 top-12 h-56 w-56 rounded-full bg-violet-300/25 blur-3xl" />
        <div className="absolute bottom-0 left-[24%] h-40 w-40 rounded-full bg-emerald-300/20 blur-3xl" />
      </div>

      <div className="relative grid gap-0 xl:items-start xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="self-start border-b border-white/55 px-5 py-5 xl:border-b-0 xl:border-r xl:px-6">
          <div className="rounded-[32px] border border-white/75 bg-[linear-gradient(135deg,rgba(255,255,255,0.78),rgba(255,255,255,0.42))] p-5 shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-2xl">
                <p className="admin-section-kicker">运行总览</p>
                <div className="mt-4 flex items-center gap-4">
                  <div className="flex h-14 w-14 items-center justify-center rounded-[22px] border border-white/75 bg-[linear-gradient(135deg,rgba(14,165,233,0.18),rgba(255,255,255,0.82))] text-slate-900 shadow-sm">
                    <MessageSquare size={24} />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-500">总会话规模</p>
                    <p className="mt-1 text-4xl font-black tracking-tight text-slate-950 lg:text-5xl">
                      {formatNumber(summary.total_sessions)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid min-w-[240px] gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <div className="rounded-[24px] border border-white/80 bg-white/55 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-black tracking-[0.18em] text-slate-500">活跃用户</span>
                    <Users size={18} className="text-cyan-700" />
                  </div>
                  <p className="mt-3 text-2xl font-black tracking-tight text-slate-950">
                    {formatNumber(summary.active_users)}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-slate-600">占全体用户 {formatPercent(activeRate)}</p>
                </div>

                <div className="rounded-[24px] border border-white/80 bg-white/55 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-black tracking-[0.18em] text-slate-500">会话密度</span>
                    <ArrowUpRight size={18} className="text-violet-700" />
                  </div>
                  <p className="mt-3 text-2xl font-black tracking-tight text-slate-950">{avgRunsPerSession}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-600">平均每个会话触发运行次数</p>
                </div>
              </div>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-3">
              <MetricRail
                label="活跃覆盖"
                value={formatPercent(activeRate)}
                percent={activeRate}
                gradient="bg-gradient-to-r from-cyan-500 via-sky-500 to-blue-500"
              />
              <MetricRail
                label="输出占比"
                value={formatPercent(outputShare)}
                percent={outputShare}
                gradient="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-rose-400"
              />
              <MetricRail
                label="工具协同比"
                value={formatPercent(toolAssistRate)}
                percent={toolAssistRate}
                gradient="bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500"
              />
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {quickSignals.map((item, index) => (
                <div
                  key={item.label}
                  className={index < 2
                    ? 'rounded-[22px] border border-white/80 bg-[linear-gradient(135deg,rgba(56,189,248,0.10),rgba(255,255,255,0.72))] px-4 py-3.5'
                    : 'rounded-[22px] border border-white/80 bg-[linear-gradient(135deg,rgba(196,181,253,0.12),rgba(255,255,255,0.72))] px-4 py-3.5'}
                >
                  <p className="text-xs font-black tracking-[0.18em] text-slate-500">{item.label}</p>
                  <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{item.value}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[24px] border border-white/80 bg-[linear-gradient(135deg,rgba(56,189,248,0.16),rgba(255,255,255,0.72))] px-4 py-4">
                <p className="text-xs font-black tracking-[0.18em] text-slate-500">总用户数</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatNumber(summary.total_users)}</p>
              </div>
              <div className="rounded-[24px] border border-white/80 bg-[linear-gradient(135deg,rgba(196,181,253,0.2),rgba(255,255,255,0.72))] px-4 py-4">
                <p className="text-xs font-black tracking-[0.18em] text-slate-500">运行次数</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatNumber(summary.total_runs)}</p>
              </div>
              <div className="rounded-[24px] border border-white/80 bg-[linear-gradient(135deg,rgba(74,222,128,0.18),rgba(255,255,255,0.72))] px-4 py-4">
                <p className="text-xs font-black tracking-[0.18em] text-slate-500">单会话 Token</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatTokenNumber(avgTokensPerSession)}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="grid content-start items-start gap-px bg-white/35 sm:auto-rows-max sm:grid-cols-2">
          {signalTiles.map((item) => (
            <div key={item.label} className="self-start p-2.5">
              <SignalTile
                label={item.label}
                value={item.value}
                meta={item.meta}
                icon={item.icon}
                accent={item.accent}
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
