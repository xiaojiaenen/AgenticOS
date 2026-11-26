import { motion } from 'motion/react';
import { Activity, Clock3, Sparkles, Users, Zap } from 'lucide-react';
import { CountUp } from '../ui/CountUp';
import { formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

export const STATIC_CARD =
  'admin-card group flex h-full flex-col rounded-2xl px-5 py-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-strong)] hover:shadow-md';

interface DashboardStatsProps {
  summary: DashboardSummary;
}

const KPI_ITEMS = [
  {
    key: 'sessions' as const,
    label: '总会话',
    icon: Users,
    getCount: (s: DashboardSummary) => s.total_sessions ?? 0,
    format: formatNumber,
    tone: 'aos-tone-sky',
    stroke: '#0284c7',
    path: 'M2 18L14 14L26 15L38 8L50 10L62 4',
  },
  {
    key: 'active_users' as const,
    label: '活跃用户',
    icon: Activity,
    getCount: (s: DashboardSummary) => s.active_users ?? 0,
    format: formatNumber,
    getSub: (s: DashboardSummary) => `占全部账号 ${formatPercent(ratio(s.active_users ?? 0, s.total_users ?? 0))}`,
    tone: 'aos-tone-emerald',
    stroke: '#059669',
    path: 'M2 15L16 12L30 13L46 7L62 6',
  },
  {
    key: 'tokens' as const,
    label: 'Token 总量',
    icon: Sparkles,
    getCount: (s: DashboardSummary) => s.total_tokens ?? 0,
    format: formatTokenNumber,
    getSub: (s: DashboardSummary) => `输入 ${formatTokenNumber(s.input_tokens ?? 0)} / 输出 ${formatTokenNumber(s.output_tokens ?? 0)}`,
    tone: 'aos-tone-violet',
    stroke: '#7c3aed',
    path: 'M2 19L16 15L30 16L46 10L62 5',
  },
  {
    key: 'latency' as const,
    label: '平均耗时',
    icon: Clock3,
    getCount: (s: DashboardSummary) => s.avg_latency_ms ?? 0,
    format: formatLatency,
    tone: 'aos-tone-amber',
    stroke: '#ea580c',
    path: 'M2 7L16 10L30 9L46 14L62 16',
  },
  {
    key: 'tools' as const,
    label: '工具调用',
    icon: Zap,
    getCount: (s: DashboardSummary) => s.tool_calls ?? 0,
    format: formatNumber,
    getSub: (s: DashboardSummary) => `协同比 ${formatPercent(ratio(s.tool_calls ?? 0, (s.tool_calls ?? 0) + (s.llm_calls ?? 0)))}`,
    tone: 'aos-tone-rose',
    stroke: '#e11d48',
    path: 'M2 17L14 13L28 14L44 8L62 5',
  },
];

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
  const s = summary ?? ({} as DashboardSummary);
  return (
    <section className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 lg:grid-cols-5">
      {KPI_ITEMS.map((item, idx) => (
        <motion.div
          key={item.key}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.04 + idx * 0.045, ease: [0.16, 1, 0.3, 1] }}
          className="h-full"
        >
          <div className={STATIC_CARD}>
            <div className="flex items-center justify-between gap-2">
              <span className="admin-muted text-[11px] font-semibold uppercase tracking-[0.08em]">
                {item.label}
              </span>
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105 ${item.tone}`}>
                <item.icon size={16} />
              </div>
            </div>

            <div className="mt-3 flex items-end justify-between gap-2">
              <p className="admin-heading font-mono text-[1.75rem] font-semibold leading-none tracking-[-0.02em] tabular-nums">
                <CountUp value={item.getCount(s)} format={item.format} />
              </p>
              <svg width="56" height="22" viewBox="0 0 64 24" fill="none" className="shrink-0 opacity-85" aria-hidden="true">
                <path
                  className="aos-svg-sparkline"
                  d={item.path}
                  stroke={item.stroke}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <p className="admin-muted mt-4 min-h-[16px] border-t border-[var(--border-subtle)] pt-2.5 text-[11px] font-medium truncate">
              {item.getSub?.(s) ?? '实时统计'}
            </p>
          </div>
        </motion.div>
      ))}
    </section>
  );
};
