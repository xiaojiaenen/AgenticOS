import React from 'react';
import { Activity, Clock3, MessageSquare, MousePointerClick, Sparkles, Users } from 'lucide-react';
import { cn } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

interface DashboardStatsProps {
  summary: DashboardSummary;
}

function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatLatency(value: number): string {
  if (!value) return '0ms';
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
  const items = [
    {
      label: '总用户数',
      value: formatNumber(summary.total_users),
      meta: `${formatNumber(summary.active_users)} 个活跃账号`,
      icon: Users,
      tone: 'text-sky-700 bg-sky-50 border-sky-100',
    },
    {
      label: '总会话数',
      value: formatNumber(summary.total_sessions),
      meta: `${formatNumber(summary.total_runs)} 次模型运行`,
      icon: MessageSquare,
      tone: 'text-cyan-700 bg-cyan-50 border-cyan-100',
    },
    {
      label: 'Token 消耗',
      value: formatNumber(summary.total_tokens),
      meta: `输入 ${formatNumber(summary.input_tokens)} / 输出 ${formatNumber(summary.output_tokens)}`,
      icon: Sparkles,
      tone: 'text-violet-700 bg-violet-50 border-violet-100',
    },
    {
      label: '模型调用',
      value: formatNumber(summary.llm_calls),
      meta: `${formatNumber(summary.tool_calls)} 次工具调用`,
      icon: Activity,
      tone: 'text-emerald-700 bg-emerald-50 border-emerald-100',
    },
    {
      label: '工具使用',
      value: formatNumber(summary.tool_calls),
      meta: summary.tool_calls > 0 ? '已记录完整工具链路' : '暂时还没有工具调用',
      icon: MousePointerClick,
      tone: 'text-amber-700 bg-amber-50 border-amber-100',
    },
    {
      label: '平均耗时',
      value: formatLatency(summary.avg_latency_ms),
      meta: '单次模型运行平均耗时',
      icon: Clock3,
      tone: 'text-rose-700 bg-rose-50 border-rose-100',
    },
  ];

  return (
    <section className="overflow-hidden rounded-[36px] border border-white/60 bg-white/48 shadow-[0_24px_70px_rgba(15,23,42,0.08)] ring-1 ring-white/35 backdrop-blur-[24px]">
      <div className="grid grid-cols-1 divide-y divide-white/55 md:grid-cols-2 md:divide-x md:divide-y-0 2xl:grid-cols-3">
        {items.map((item) => (
          <div key={item.label} className="px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">{item.label}</p>
                <p className="mt-3 text-3xl font-black tracking-tight text-slate-950">{item.value}</p>
                <p className="mt-2 text-xs font-semibold leading-5 text-slate-500">{item.meta}</p>
              </div>
              <div className={cn('flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl border', item.tone)}>
                <item.icon size={22} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
