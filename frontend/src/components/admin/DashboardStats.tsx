import { motion } from 'motion/react';
import { Activity, Clock3, Sparkles, Users, Zap } from 'lucide-react';
import { formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

interface DashboardStatsProps {
 summary: DashboardSummary;
}

const KPI_ITEMS = [
 {
  key: 'sessions' as const,
  label: '总会话',
  icon: Users,
  getValue: (s: DashboardSummary) => formatNumber(s.total_sessions ?? 0),
  accent: 'text-sky-600',
  bg: 'bg-sky-50',
 },
 {
  key: 'active_users' as const,
  label: '活跃用户',
  icon: Activity,
  getValue: (s: DashboardSummary) => formatNumber(s.active_users ?? 0),
  getSub: (s: DashboardSummary) => `占 ${formatPercent(ratio(s.active_users ?? 0, s.total_users ?? 0))}`,
  accent: 'text-emerald-600',
  bg: 'bg-emerald-50',
 },
 {
  key: 'tokens' as const,
  label: 'Token 总量',
  icon: Sparkles,
  getValue: (s: DashboardSummary) => formatTokenNumber(s.total_tokens ?? 0),
  getSub: (s: DashboardSummary) => `输入 ${formatTokenNumber(s.input_tokens ?? 0)} / 输出 ${formatTokenNumber(s.output_tokens ?? 0)}`,
  accent: 'text-violet-600',
  bg: 'bg-violet-50',
 },
 {
  key: 'latency' as const,
  label: '平均耗时',
  icon: Clock3,
  getValue: (s: DashboardSummary) => formatLatency(s.avg_latency_ms ?? 0),
  accent: 'text-amber-600',
  bg: 'bg-amber-50',
 },
 {
  key: 'tools' as const,
  label: '工具调用',
  icon: Zap,
  getValue: (s: DashboardSummary) => formatNumber(s.tool_calls ?? 0),
  getSub: (s: DashboardSummary) => `协同比 ${formatPercent(ratio(s.tool_calls ?? 0, (s.tool_calls ?? 0) + (s.llm_calls ?? 0)))}`,
  accent: 'text-rose-600',
  bg: 'bg-rose-50',
 },
];

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
 const s = summary ?? ({} as DashboardSummary);

 return (
  <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
   {KPI_ITEMS.map((item, idx) => (
    <motion.div
     key={item.key}
     initial={{ opacity: 0, y: 10 }}
     animate={{ opacity: 1, y: 0 }}
     transition={{ duration: 0.35, delay: 0.05 + idx * 0.05, ease: [0.16, 1, 0.3, 1] }}
     className="admin-stat-card group rounded-lg border border-[var(--admin-card-border)] bg-[var(--admin-card-bg)] px-4 py-4 shadow-sm"
    >
     <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] font-semibold tracking-[0.08em] text-slate-400">{item.label}</span>
      <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${item.bg} ${item.accent} transition-transform duration-300 group-hover:scale-110`}>
       <item.icon size={15} />
      </div>
     </div>
     <p className="mt-2.5 text-xl font-semibold tracking-tight text-slate-950 lg:text-2xl">{item.getValue(s)}</p>
     {item.getSub && (
      <p className="mt-1 text-[11px] font-semibold text-slate-400">{item.getSub(s)}</p>
     )}
    </motion.div>
   ))}
  </section>
 );
};
