import React from 'react';
import { motion } from 'motion/react';
import {
  Activity,
  ArrowUpRight,
  Clock3,
  MessageSquare,
  MousePointerClick,
  Sparkles,
  Users,
} from 'lucide-react';
import { cn, formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

interface DashboardStatsProps {
  summary: DashboardSummary;
}


function MetricRail({
  label,
  value,
  percent,
  gradient,
  index = 0,
}: {
  label: string;
  value: string;
  percent: number;
  gradient: string;
  index?: number;
}) {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 180 + index * 80);
    return () => clearTimeout(timer);
  }, [index]);

  return (
    <div className="admin-stat-card group rounded-xl px-3.5 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold tracking-[0.12em] text-slate-500 group-hover:text-slate-700 transition-colors">{label}</span>
        <span className="text-sm font-bold text-slate-900">{value}</span>
      </div>
      <div className="admin-progress-bar mt-2.5">
        <div
          className={`admin-progress-fill ${gradient}`}
          style={{ width: mounted ? `${Math.max(percent, 6)}%` : '0%' }}
        />
      </div>
    </div>
  );
}

function SignalTile({
  label,
  value,
  meta,
  detail,
  icon: Icon,
  accent,
  delay = 0,
}: {
  label: string;
  value: string;
  meta: string;
  detail?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accent: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.16, 1, 0.3, 1] }}
      className={`admin-stat-card group rounded-2xl border border-white/50 px-4 py-4 shadow-md ${accent}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold tracking-[0.16em] text-slate-600">{label}</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">{value}</p>
          <p className="mt-1.5 text-xs font-semibold leading-5 text-slate-500">{meta}</p>
          {detail && (
            <p className="mt-1 text-[11px] font-medium leading-4 text-slate-400">{detail}</p>
          )}
        </div>
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-white/60 bg-white/60 text-slate-900 shadow-sm transition-all duration-300 group-hover:scale-110 group-hover:shadow-md group-hover:border-brand-200">
          <Icon size={18} />
        </div>
      </div>
    </motion.div>
  );
}

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
  const s = summary ?? {} as DashboardSummary;
  const activeRate = ratio(s.active_users ?? 0, s.total_users ?? 0);
  const toolAssistRate = ratio(s.tool_calls ?? 0, (s.tool_calls ?? 0) + (s.llm_calls ?? 0));
  const outputShare = ratio(s.output_tokens ?? 0, s.total_tokens ?? 1);
  const avgTokensPerSession = (s.total_sessions ?? 0) > 0 ? Math.round((s.total_tokens ?? 0) / s.total_sessions!) : 0;
  const avgRunsPerSession = (s.total_sessions ?? 0) > 0 ? ((s.total_runs ?? 0) / s.total_sessions!).toFixed(1) : '0.0';
  const quickSignals = [
    {
      label: '输入 Token',
      value: formatTokenNumber(s.input_tokens ?? 0),
    },
    {
      label: '输出 Token',
      value: formatTokenNumber(s.output_tokens ?? 0),
    },
    {
      label: '每用户会话',
      value: (s.total_users ?? 0) > 0 ? ((s.total_sessions ?? 0) / s.total_users!).toFixed(1) : '0.0',
    },
    {
      label: '每次运行工具',
      value: (s.total_runs ?? 0) > 0 ? ((s.tool_calls ?? 0) / s.total_runs!).toFixed(2) : '0.00',
    },
  ];

  const signalTiles = [
    {
      label: '模型调用',
      value: formatNumber(s.llm_calls ?? 0),
      meta: `工具协同 ${formatPercent(toolAssistRate)}`,
      detail: (s.total_sessions ?? 0) > 0 ? `每会话 ${((s.llm_calls ?? 0) / s.total_sessions!).toFixed(1)} 次推理` : undefined,
      icon: Activity,
      accent: 'bg-[linear-gradient(135deg,rgba(16,185,129,0.28),rgba(255,255,255,0.72),rgba(6,182,212,0.16))]',
    },
    {
      label: '平均耗时',
      value: formatLatency(s.avg_latency_ms ?? 0),
      meta: '按单次运行统计',
      detail: undefined,
      icon: Clock3,
      accent: 'bg-[linear-gradient(135deg,rgba(248,113,113,0.18),rgba(255,255,255,0.76),rgba(251,191,36,0.18))]',
    },
    {
      label: 'Token 总量',
      value: formatTokenNumber(s.total_tokens ?? 0),
      meta: `输入 ${formatTokenNumber(s.input_tokens ?? 0)} / 输出 ${formatTokenNumber(s.output_tokens ?? 0)}`,
      detail: (s.total_sessions ?? 0) > 0 ? `每会话平均 ${formatTokenNumber(avgTokensPerSession)} Token · 输出占比 ${formatPercent(outputShare)}` : undefined,
      icon: Sparkles,
      accent: 'bg-[linear-gradient(135deg,rgba(139,92,246,0.22),rgba(255,255,255,0.72),rgba(59,130,246,0.15))]',
    },
    {
      label: '工具调用',
      value: formatNumber(s.tool_calls ?? 0),
      meta: (s.tool_calls ?? 0) > 0 ? '已形成工具链路' : '暂未触发工具调用',
      detail: (s.total_sessions ?? 0) > 0 ? `每会话 ${((s.tool_calls ?? 0) / s.total_sessions!).toFixed(2)} 次 · 每次运行 ${((s.tool_calls ?? 0) / Math.max(s.total_runs ?? 0, 1)).toFixed(1)} 个` : undefined,
      icon: MousePointerClick,
      accent: 'bg-[linear-gradient(135deg,rgba(251,191,36,0.22),rgba(255,255,255,0.76),rgba(244,114,182,0.14))]',
    },
  ];

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      {/* Left: main stats — sky-blue tinted semi-transparent card */}
      <div className="rounded-2xl border border-white/50 bg-[linear-gradient(135deg,rgba(255,255,255,0.62),rgba(255,255,255,0.38),rgba(186,230,253,0.34))] p-5 shadow-md">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="admin-section-kicker">运行总览</p>
            <div className="mt-3 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/70 bg-[linear-gradient(135deg,rgba(14,165,233,0.15),rgba(255,255,255,0.78))] text-slate-900 shadow-sm">
                <MessageSquare size={20} />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-500">总会话规模</p>
                <p className="mt-1 text-5xl font-bold tracking-tight text-slate-950 lg:text-6xl">
                  {formatNumber(s.total_sessions ?? 0)}
                </p>
              </div>
            </div>
          </div>

          <div className="grid min-w-[220px] gap-2.5 sm:grid-cols-2 lg:grid-cols-1">
            <div className="admin-stat-card rounded-xl bg-white/68 px-4 py-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold tracking-[0.12em] text-slate-500">活跃用户</span>
                <Users size={16} className="text-cyan-600" />
              </div>
              <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{formatNumber(s.active_users ?? 0)}</p>
              <p className="mt-1.5 text-xs font-semibold text-slate-500">占全体用户 {formatPercent(activeRate)}</p>
            </div>
            <div className="admin-stat-card rounded-xl bg-white/68 px-4 py-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold tracking-[0.12em] text-slate-500">会话密度</span>
                <ArrowUpRight size={16} className="text-violet-600" />
              </div>
              <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{avgRunsPerSession}</p>
              <p className="mt-1.5 text-xs font-semibold text-slate-500">平均每个会话触发运行次数</p>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-2.5 lg:grid-cols-3">
          <MetricRail label="活跃覆盖" value={formatPercent(activeRate)} percent={activeRate} gradient="bg-gradient-to-r from-cyan-500 via-sky-500 to-blue-500" index={0} />
          <MetricRail label="输出占比" value={formatPercent(outputShare)} percent={outputShare} gradient="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-rose-400" index={1} />
          <MetricRail label="工具协同比" value={formatPercent(toolAssistRate)} percent={toolAssistRate} gradient="bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500" index={2} />
        </div>

        <div className="mt-3 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
          {quickSignals.map((item, index) => (
            <div
              key={item.label}
              className={cn(
                'admin-stat-card rounded-xl px-4 py-3.5',
                index < 2
                  ? 'bg-[linear-gradient(135deg,rgba(56,189,248,0.10),rgba(255,255,255,0.72))]'
                  : 'bg-[linear-gradient(135deg,rgba(196,181,253,0.12),rgba(255,255,255,0.72))]',
              )}
            >
              <p className="text-[11px] font-bold tracking-[0.12em] text-slate-500">{item.label}</p>
              <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{item.value}</p>
            </div>
          ))}
        </div>

        <div className="mt-3 grid gap-2.5 sm:grid-cols-3">
          <div className="admin-stat-card rounded-xl bg-[linear-gradient(135deg,rgba(56,189,248,0.16),rgba(255,255,255,0.72))] px-4 py-3.5">
            <p className="text-[11px] font-bold tracking-[0.12em] text-slate-500">总用户数</p>
            <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{formatNumber(s.total_users ?? 0)}</p>
          </div>
          <div className="admin-stat-card rounded-xl bg-[linear-gradient(135deg,rgba(196,181,253,0.20),rgba(255,255,255,0.72))] px-4 py-3.5">
            <p className="text-[11px] font-bold tracking-[0.12em] text-slate-500">运行次数</p>
            <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{formatNumber(s.total_runs ?? 0)}</p>
          </div>
          <div className="admin-stat-card rounded-xl bg-[linear-gradient(135deg,rgba(74,222,128,0.17),rgba(255,255,255,0.72))] px-4 py-3.5">
            <p className="text-[11px] font-bold tracking-[0.12em] text-slate-500">单会话 Token</p>
            <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{formatTokenNumber(avgTokensPerSession)}</p>
          </div>
        </div>
      </div>

      {/* Right: signal tiles — each with its own tinted background */}
      <div className="grid content-start gap-3 sm:grid-cols-2">
        {signalTiles.map((item, idx) => (
          <SignalTile key={item.label} label={item.label} value={item.value} meta={item.meta} icon={item.icon} accent={item.accent} delay={0.08 + idx * 0.06} />
        ))}
      </div>
    </section>
  );
};
