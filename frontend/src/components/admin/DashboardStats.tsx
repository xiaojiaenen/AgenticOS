import React from 'react';
import { Activity, Clock3, MessageSquare, MousePointerClick, Sparkles, Users } from 'lucide-react';
import { Card } from '../ui/Card';
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
      tone: 'bg-sky-50 text-sky-700 border-sky-100',
    },
    {
      label: '会话总数',
      value: formatNumber(summary.total_sessions),
      meta: `${formatNumber(summary.total_runs)} 次模型运行`,
      icon: MessageSquare,
      tone: 'bg-cyan-50 text-cyan-700 border-cyan-100',
    },
    {
      label: 'Token 消耗',
      value: formatNumber(summary.total_tokens),
      meta: `输入 ${formatNumber(summary.input_tokens)} / 输出 ${formatNumber(summary.output_tokens)}`,
      icon: Sparkles,
      tone: 'bg-violet-50 text-violet-700 border-violet-100',
    },
    {
      label: '模型调用',
      value: formatNumber(summary.llm_calls),
      meta: `${formatNumber(summary.tool_calls)} 次工具调用`,
      icon: Activity,
      tone: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    },
    {
      label: '工具使用',
      value: formatNumber(summary.tool_calls),
      meta: summary.tool_calls > 0 ? '已记录工具链运行' : '暂无工具调用',
      icon: MousePointerClick,
      tone: 'bg-amber-50 text-amber-700 border-amber-100',
    },
    {
      label: '平均耗时',
      value: formatLatency(summary.avg_latency_ms),
      meta: '单次模型运行平均值',
      icon: Clock3,
      tone: 'bg-rose-50 text-rose-700 border-rose-100',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <Card key={item.label} className="group relative overflow-hidden p-5 transition-all hover:-translate-y-0.5 hover:shadow-md">
          <div className="absolute right-0 top-0 h-28 w-28 rounded-full bg-white/70 blur-3xl transition-opacity group-hover:opacity-80" />
          <div className="relative z-10 flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-slate-400">{item.label}</p>
              <p className="mt-3 text-3xl font-black tracking-tight text-slate-900">{item.value}</p>
              <p className="mt-2 text-xs font-bold text-slate-500">{item.meta}</p>
            </div>
            <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${item.tone}`}>
              <item.icon size={22} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};
