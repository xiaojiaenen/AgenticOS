import { motion } from 'motion/react';
import { Activity, Clock3, Sparkles, Users, Zap } from 'lucide-react';
import { formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

/**
 * 仪表盘统计卡片的统一视觉规范：AdminDashboard 顶部的快捷指标行与
 * 下方 KPI 行共用同一套类名，避免两排卡片风格割裂。
 * 颜色走 CSS 变量（--surface-1 / --border-subtle / --foreground），
 * 深色模式下自动翻转，不写死 bg-[var(--surface-1)]。
 */
export const STATIC_CARD =
  'admin-card group flex h-full flex-col px-4 py-4';

interface DashboardStatsProps {
 summary: DashboardSummary;
}

const KPI_ITEMS = [
 {
  key: 'sessions' as const,
  label: '总会话',
  icon: Users,
  getValue: (s: DashboardSummary) => formatNumber(s.total_sessions ?? 0),
  accent: 'text-sky-400',
  bg: 'bg-sky-500/20',
 },
 {
  key: 'active_users' as const,
  label: '活跃用户',
  icon: Activity,
  getValue: (s: DashboardSummary) => formatNumber(s.active_users ?? 0),
  getSub: (s: DashboardSummary) => `占 ${formatPercent(ratio(s.active_users ?? 0, s.total_users ?? 0))}`,
  accent: 'text-emerald-400',
  bg: 'bg-emerald-500/20',
 },
 {
  key: 'tokens' as const,
  label: 'Token 总量',
  icon: Sparkles,
  getValue: (s: DashboardSummary) => formatTokenNumber(s.total_tokens ?? 0),
  getSub: (s: DashboardSummary) => `输入 ${formatTokenNumber(s.input_tokens ?? 0)} / 输出 ${formatTokenNumber(s.output_tokens ?? 0)}`,
  accent: 'text-violet-400',
  bg: 'bg-violet-500/20',
 },
 {
  key: 'latency' as const,
  label: '平均耗时',
  icon: Clock3,
  getValue: (s: DashboardSummary) => formatLatency(s.avg_latency_ms ?? 0),
  accent: 'text-amber-400',
  bg: 'bg-amber-500/20',
 },
 {
  key: 'tools' as const,
  label: '工具调用',
  icon: Zap,
  getValue: (s: DashboardSummary) => formatNumber(s.tool_calls ?? 0),
  getSub: (s: DashboardSummary) => `协同比 ${formatPercent(ratio(s.tool_calls ?? 0, (s.tool_calls ?? 0) + (s.llm_calls ?? 0)))}`,
  accent: 'text-rose-400',
  bg: 'bg-rose-500/20',
 },
];

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
 const s = summary ?? ({} as DashboardSummary); return (
  <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
   {KPI_ITEMS.map((item, idx) => (
    <motion.div
     key={item.key}
     initial={{ opacity: 0, y: 10 }}
     animate={{ opacity: 1, y: 0 }}
     transition={{ duration: 0.35, delay: 0.05 + idx * 0.05, ease: [0.16, 1, 0.3, 1] }}
     className="h-full"
    >
     <div className={STATIC_CARD}>
      <div className="flex items-center justify-between gap-2">
       <span className="admin-muted text-[11px] font-semibold tracking-[0.08em]">{item.label}</span>
       <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${item.bg} ${item.accent} transition-transform duration-300 group-hover:scale-110`}>
        <item.icon size={15} />
       </div>
      </div>
      <p className="mt-2.5 admin-heading text-xl font-semibold tracking-tight lg:text-2xl">{item.getValue(s)}</p>
      {/* 副信息行占位固定高度：有无副信息的卡片保持等高 */}
      <p className="admin-muted mt-1 min-h-[14px] text-[11px] font-semibold">{item.getSub?.(s) ?? ''}</p>
     </div>
    </motion.div>
   ))}
  </section>
 );
};
