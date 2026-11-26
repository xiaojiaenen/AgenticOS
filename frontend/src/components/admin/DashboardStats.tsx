import { motion } from 'motion/react';
import { Activity, Clock3, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import { CountUp } from '../ui/CountUp';
import { formatNumber, formatTokenNumber, formatLatency, formatPercent, ratio } from '../../lib/utils';
import { DashboardSummary } from '../../services/dashboardService';

interface DashboardStatsProps {
  summary: DashboardSummary;
}

/**
 * 1:1 复刻 agenticos.html 截图 5 的 4 列 KPI 卡片：
 * 顶行左色块微图标 + 右胶囊指标，中行灰标，底行左等宽大字 + 右彩色动态 SVG 折线
 */
const KPI_ITEMS = [
  {
    key: 'sessions' as const,
    label: '会话执行总数',
    icon: Activity,
    getCount: (s: DashboardSummary) => s.total_sessions ?? 0,
    format: formatNumber,
    getBadge: (s: DashboardSummary) => `活跃 ${formatNumber(s.active_users ?? 0)} 人`,
    badgeGreen: true,
    tone: 'aos-tone-amber',
    stroke: '#EA580C',
    path: 'M2 20L14 15L26 17L38 9L50 11L62 4',
  },
  {
    key: 'tools' as const,
    label: '工具协同调用',
    icon: ShieldCheck,
    getCount: (s: DashboardSummary) => s.tool_calls ?? 0,
    format: formatNumber,
    getBadge: (s: DashboardSummary) =>
      `协同比 ${formatPercent(ratio(s.tool_calls ?? 0, (s.tool_calls ?? 0) + (s.llm_calls ?? 0)))}`,
    badgeGreen: false,
    tone: 'aos-tone-emerald',
    stroke: '#059669',
    path: 'M2 14L16 12L30 13L46 8L62 7',
  },
  {
    key: 'latency' as const,
    label: '平均响应延迟',
    icon: Zap,
    getCount: (s: DashboardSummary) => s.avg_latency_ms ?? 0,
    format: formatLatency,
    getBadge: () => '实时监控',
    badgeGreen: false,
    tone: 'aos-tone-sky',
    stroke: '#0284C7',
    path: 'M2 7L16 10L30 9L46 15L62 17',
  },
  {
    key: 'tokens' as const,
    label: '累计 Token 消耗',
    icon: Sparkles,
    getCount: (s: DashboardSummary) => s.total_tokens ?? 0,
    format: formatTokenNumber,
    getBadge: () => '配额健康',
    badgeGreen: false,
    tone: 'aos-tone-violet',
    stroke: '#7C3AED',
    path: 'M2 18L16 14L30 15L46 10L62 6',
  },
];

export const DashboardStats = ({ summary }: DashboardStatsProps) => {
  const s = summary ?? ({} as DashboardSummary);
  return (
    <section className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
      {KPI_ITEMS.map((item, idx) => (
        <motion.div
          key={item.key}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: idx * 0.05, ease: [0.22, 1, 0.36, 1] }}
          className="aos-glass-surface aos-surface-interactive rounded-2xl p-4"
        >
          <div className="flex items-center justify-between gap-2">
            <span className={`aos-icon-badge h-9 w-9 ${item.tone}`}>
              <item.icon size={16} />
            </span>
            <span
              className={`rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] font-medium ${
                item.badgeGreen ? 'text-emerald-600 dark:text-emerald-400' : 'text-[var(--muted-foreground)]'
              }`}
            >
              {item.getBadge(s)}
            </span>
          </div>

          <div className="mt-3 text-xs text-[var(--muted-foreground)]">{item.label}</div>

          <div className="mt-1 flex items-end justify-between gap-2">
            <div className="text-2xl font-bold tabular-nums text-[var(--foreground)]">
              <CountUp value={item.getCount(s)} format={item.format} />
            </div>
            <svg width="64" height="24" viewBox="0 0 64 24" fill="none" className="shrink-0" aria-hidden="true">
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
        </motion.div>
      ))}
    </section>
  );
};

// Keep Clock3 import usage clean if referenced elsewhere
export const _ADMIN_KPI_ICON_REF = Clock3;
