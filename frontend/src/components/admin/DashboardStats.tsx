import { motion } from 'motion/react';
import { Activity, Clock3, Sparkles, Users, Zap } from 'lucide-react';
import { CountUp } from '../ui/CountUp';
import { formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

/**
 * 仪表盘统计卡片的统一视觉规范：AdminDashboard 顶部的快捷指标行与
 * 下方 KPI 行共用同一套类名，避免两排卡片风格割裂。
 * 颜色走 CSS 变量（--surface-1 / --border-subtle / --foreground），
 * 深色模式下自动翻转，不写死 bg-[var(--surface-1)]。
 */
// 参考 opus-frontend-arena（模型生成的 admin dashboard）的卡片结构：
// 14px 圆角 + 20px padding + 1px 边框，hover 时边框提级 + 轻微上移（≤2px），
// 不做 scale 放大（模型生成里常见的 AI 味）。
export const STATIC_CARD =
 'admin-card group flex h-full flex-col rounded-[14px] px-5 py-5 transition-all duration-150 hover:-translate-y-0.5 hover:border-[var(--border-medium)] hover:shadow-md';

interface DashboardStatsProps {
 summary: DashboardSummary;
}

// KPI 值拆成 count + format 两段：CountUp 滚动原始数字，format 保持与
// 静态渲染同口径（formatNumber / formatTokenNumber 都是纯函数 of 数字）
const KPI_ITEMS = [
 {
  key: 'sessions' as const,
  label: '总会话',
  icon: Users,
  getCount: (s: DashboardSummary) => s.total_sessions ?? 0,
  format: formatNumber,
  accent: 'text-sky-400',
  bg: 'bg-sky-500/20',
 },
 {
  key: 'active_users' as const,
  label: '活跃用户',
  icon: Activity,
  getCount: (s: DashboardSummary) => s.active_users ?? 0,
  format: formatNumber,
  getSub: (s: DashboardSummary) => `占全部账号 ${formatPercent(ratio(s.active_users ?? 0, s.total_users ?? 0))}`,
  accent: 'text-emerald-400',
  bg: 'bg-emerald-500/20',
 },
 {
  key: 'tokens' as const,
  label: 'Token 总量',
  icon: Sparkles,
  getCount: (s: DashboardSummary) => s.total_tokens ?? 0,
  format: formatTokenNumber,
  getSub: (s: DashboardSummary) => `输入 ${formatTokenNumber(s.input_tokens ?? 0)} / 输出 ${formatTokenNumber(s.output_tokens ?? 0)}`,
  accent: 'text-violet-400',
  bg: 'bg-violet-500/20',
 },
 {
  key: 'latency' as const,
  label: '平均耗时',
  icon: Clock3,
  getCount: (s: DashboardSummary) => s.avg_latency_ms ?? 0,
  format: formatLatency,
  accent: 'text-amber-400',
  bg: 'bg-amber-500/20',
 },
 {
  key: 'tools' as const,
  label: '工具调用',
  icon: Zap,
  getCount: (s: DashboardSummary) => s.tool_calls ?? 0,
  format: formatNumber,
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
       <span className="admin-muted text-[10px] font-semibold uppercase tracking-[0.08em]">{item.label}</span>
       {/* 图标 chip 44px，语义 muted 底；不放大，只随卡片微微上移 */}
       <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] ${item.bg} ${item.accent}`}>
        <item.icon size={18} />
       </div>
      </div>
      {/* 大数字用等宽字体 + 收紧字距（-0.02em），金额/指标数字对齐 */}
      <p className="admin-heading mt-3 font-mono text-[1.875rem] font-semibold leading-none tracking-[-0.02em]">
        <CountUp value={item.getCount(s)} format={item.format} />
      </p>
      {/* 副信息：顶部 hairline 分隔，固定高度保持卡片等高 */}
      <p className="admin-muted mt-4 min-h-[16px] border-t border-[var(--border-subtle)] pt-2.5 text-[11px] font-medium">
        {item.getSub?.(s) ?? '—'}
      </p>
     </div>
    </motion.div>
   ))}
  </section>
 );
};
