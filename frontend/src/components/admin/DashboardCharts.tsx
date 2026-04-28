import React from 'react';
import { motion } from 'motion/react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Activity, Cpu, Gauge, Hammer, Trophy, Waves } from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  DashboardDistributionItem,
  DashboardStats as DashboardStatsData,
  DashboardUserUsage,
} from '../../services/dashboardService';

interface DashboardChartsProps {
  data: DashboardStatsData;
}

const CHART_COLORS = ['#0f172a', '#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e', '#14b8a6', '#6366f1'];

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

function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match) {
    return `${Number(match[2])}/${Number(match[3])}`;
  }
  return value.slice(5);
}

function shortName(name: string): string {
  if (!name) return '未知';
  return name.length > 7 ? `${name.slice(0, 7)}…` : name;
}

function initials(name: string): string {
  return (name || 'U').slice(0, 1).toUpperCase();
}

function EmptyPanel({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-[220px] items-center justify-center rounded-[26px] border border-dashed border-white/65 bg-white/30 text-sm font-bold text-slate-500">
      {label}
    </div>
  );
}

function PanelHeader({
  icon: Icon,
  kicker,
  title,
  extra,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  kicker: string;
  title: string;
  extra?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-[16px] border border-white/80 bg-white/70 text-slate-900 shadow-sm">
          <Icon size={20} />
        </div>
        <div>
          <p className="admin-section-kicker">{kicker}</p>
          <h3 className="mt-1 text-[22px] font-black tracking-tight text-slate-950">{title}</h3>
        </div>
      </div>
      {extra}
    </div>
  );
}

function PanelShell({
  className,
  children,
  tone,
}: {
  className?: string;
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <section
      className={cn(
        'admin-data-panel relative',
        tone ?? 'bg-white/52',
        className,
      )}
    >
      <div className="relative h-full px-6 py-6">{children}</div>
    </section>
  );
}

function DistributionLegend({ items }: { items: DashboardDistributionItem[] }) {
  return (
    <div className="mt-4 space-y-2.5">
      {items.slice(0, 5).map((item, index) => (
        <div key={item.name} className="flex items-center justify-between gap-3 text-sm font-bold">
          <span className="flex min-w-0 items-center gap-2.5 text-slate-700">
            <span
              className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
              style={{ background: CHART_COLORS[index % CHART_COLORS.length] }}
            />
            <span className="truncate">{item.name}</span>
          </span>
          <span className="text-slate-950">{formatNumber(item.value)}</span>
        </div>
      ))}
    </div>
  );
}

function UserUsageRow({
  user,
  index,
  maxTokens,
}: {
  user: DashboardUserUsage;
  index: number;
  maxTokens: number;
}) {
  const percentage = maxTokens > 0 ? Math.max(8, Math.round((user.total_tokens / maxTokens) * 100)) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: Math.min(index * 0.03, 0.16) }}
      whileHover={{ x: 2 }}
      className="admin-table-row grid grid-cols-1 gap-4 border-b border-white/55 px-5 py-4 text-center last:border-b-0 lg:grid-cols-[minmax(210px,1.2fr)_110px_110px_110px_110px_120px] lg:items-center lg:gap-0"
    >
      <div className="flex min-w-0 items-center justify-center gap-4">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl border border-white/75 bg-white/65 text-sm font-black text-slate-800 shadow-sm">
          {initials(user.name)}
        </div>
        <div className="min-w-0">
          <div className="flex items-center justify-center gap-2">
            <span className="text-xs font-black text-slate-400">#{index + 1}</span>
            <p className="truncate text-sm font-black text-slate-900">{user.name}</p>
          </div>
          <p className="mt-1 truncate text-xs font-medium text-slate-500">{user.email}</p>
        </div>
      </div>
      <div className="text-sm font-black text-slate-900">{formatTokenNumber(user.total_tokens)}</div>
      <div className="text-sm font-bold text-slate-600">{formatNumber(user.llm_calls)}</div>
      <div className="text-sm font-bold text-slate-600">{formatNumber(user.tool_calls)}</div>
      <div className="text-sm font-bold text-slate-600">{formatLatency(user.avg_latency_ms)}</div>
      <div className="h-2 rounded-full bg-white/70">
        <div
          className={cn(
            'h-2 rounded-full',
            index === 0
              ? 'bg-gradient-to-r from-slate-900 to-slate-700'
              : index === 1
                ? 'bg-gradient-to-r from-cyan-500 to-sky-500'
                : 'bg-gradient-to-r from-violet-500 to-fuchsia-500',
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </motion.div>
  );
}

export const DashboardCharts = ({ data }: DashboardChartsProps) => {
  const trendData = data.trend.map((item) => ({
    ...item,
    avgTokens: item.runs > 0 ? Math.round(item.tokens / item.runs) : 0,
    toolPerRun: item.runs > 0 ? Number((item.tool_calls / item.runs).toFixed(2)) : 0,
  }));
  const pulseData = trendData.slice(-8);
  const latestPoint = trendData[trendData.length - 1];
  const hasTrend = trendData.some((item) => item.runs || item.tokens || item.tool_calls);
  const topUsers = data.user_usage.slice(0, 6);
  const maxUserTokens = Math.max(...topUsers.map((user) => user.total_tokens), 0);
  const topUsersChartData = topUsers.map((user) => ({
    name: shortName(user.name),
    tokens: user.total_tokens,
  }));
  const totalModelCalls = data.model_distribution.reduce((sum, item) => sum + item.value, 0);
  const totalToolCalls = data.tool_distribution.reduce((sum, item) => sum + item.value, 0);
  const callMix = [
    { name: '模型调用', value: data.summary.llm_calls },
    { name: '工具调用', value: data.summary.tool_calls },
  ].filter((item) => item.value > 0);
  const trendSignals = [
    {
      label: '峰值 Token',
      value: formatTokenNumber(Math.max(...trendData.map((item) => item.tokens), 0)),
    },
    {
      label: '峰值运行',
      value: formatNumber(Math.max(...trendData.map((item) => item.runs), 0)),
    },
    {
      label: '最新工具比',
      value: latestPoint ? `${latestPoint.toolPerRun.toFixed(2)}` : '0.00',
    },
    {
      label: '最新日 Token',
      value: latestPoint ? formatTokenNumber(latestPoint.tokens) : '0',
    },
  ];

  return (
    <div className="admin-page-stage space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_360px]">
        <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.62),rgba(255,255,255,0.38),rgba(186,230,253,0.34))]">
          <PanelHeader
            icon={Waves}
            kicker="趋势主视图"
            title="Token、运行与工具节奏"
            extra={
              <div className="rounded-full border border-white/80 bg-white/65 px-3 py-2 text-xs font-black text-slate-500">
                最近 {trendData.length || 14} 个统计点
              </div>
            }
          />

          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-[24px] border border-white/75 bg-white/55 px-4 py-4">
              <p className="text-xs font-black tracking-[0.18em] text-slate-400">累计 Token</p>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatTokenNumber(data.summary.total_tokens)}</p>
            </div>
            <div className="rounded-[24px] border border-white/75 bg-white/55 px-4 py-4">
              <p className="text-xs font-black tracking-[0.18em] text-slate-400">累计运行</p>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatNumber(data.summary.total_runs)}</p>
            </div>
            <div className="rounded-[24px] border border-white/75 bg-white/55 px-4 py-4">
              <p className="text-xs font-black tracking-[0.18em] text-slate-400">平均单次负载</p>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">
                {formatTokenNumber(Math.round(data.summary.total_tokens / Math.max(data.summary.total_runs, 1)))}
              </p>
            </div>
          </div>

          <div className="h-[300px]">
            {hasTrend ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={trendData} margin={{ top: 10, right: 18, bottom: 2, left: 0 }}>
                  <defs>
                    <linearGradient id="dashboardTokensGradient" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.42} />
                      <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.03} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.25)" strokeDasharray="4 7" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatDay}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    dy={10}
                  />
                  <YAxis
                    yAxisId="left"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    tickFormatter={formatTokenNumber}
                    width={56}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    tickFormatter={formatNumber}
                    width={36}
                  />
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      name === 'tokens' ? formatTokenNumber(value) : formatNumber(value),
                      name === 'tokens' ? 'Token' : name === 'runs' ? '运行次数' : name,
                    ]}
                    labelFormatter={(label) => `日期 ${label}`}
                    contentStyle={{
                      borderRadius: 18,
                      border: '1px solid rgba(226,232,240,0.9)',
                      background: 'rgba(255,255,255,0.96)',
                      boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                      fontWeight: 700,
                    }}
                  />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="tokens"
                    stroke="#0ea5e9"
                    strokeWidth={3}
                    fill="url(#dashboardTokensGradient)"
                    activeDot={{ r: 6, strokeWidth: 0 }}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="runs"
                    stroke="#7c3aed"
                    strokeWidth={3}
                    dot={false}
                    activeDot={{ r: 5, strokeWidth: 0, fill: '#7c3aed' }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <EmptyPanel label="暂时还没有可展示的趋势数据" />
            )}
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {trendSignals.map((item, index) => (
              <div
                key={item.label}
                className={cn(
                  'rounded-[22px] border border-white/75 px-4 py-3.5',
                  index < 2
                    ? 'bg-[linear-gradient(135deg,rgba(224,242,254,0.52),rgba(255,255,255,0.65))]'
                    : 'bg-[linear-gradient(135deg,rgba(233,213,255,0.28),rgba(255,255,255,0.65))]',
                )}
              >
                <p className="text-xs font-black tracking-[0.18em] text-slate-400">{item.label}</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{item.value}</p>
              </div>
            ))}
          </div>
        </PanelShell>

        <div className="grid gap-5">
          <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(224,242,254,0.48),rgba(255,255,255,0.36))]">
            <PanelHeader icon={Activity} kicker="运行脉冲" title="最近几天调用强度" />
            <div className="h-[220px]">
              {pulseData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={pulseData} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="4 7" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatDay}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#64748b', fontSize: 11, fontWeight: 700 }}
                    />
                    <YAxis hide />
                    <Tooltip
                      formatter={(value: number, name: string) => [formatNumber(value), name === 'runs' ? '运行次数' : '工具调用']}
                      labelFormatter={(label) => `日期 ${label}`}
                      contentStyle={{
                        borderRadius: 18,
                        border: '1px solid rgba(226,232,240,0.9)',
                        background: 'rgba(255,255,255,0.96)',
                        boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                        fontWeight: 700,
                      }}
                    />
                    <Bar dataKey="runs" radius={[10, 10, 0, 0]} fill="#0ea5e9" barSize={12} />
                    <Bar dataKey="tool_calls" radius={[10, 10, 0, 0]} fill="#8b5cf6" barSize={12} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyPanel label="暂无运行脉冲数据" />
              )}
            </div>
          </PanelShell>

          <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(233,213,255,0.34),rgba(255,255,255,0.36))]">
            <PanelHeader icon={Gauge} kicker="效率水位" title="单次运行负载走势" />
            <div className="h-[220px]">
              {hasTrend ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="4 7" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatDay}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#64748b', fontSize: 11, fontWeight: 700 }}
                    />
                    <YAxis hide />
                    <Tooltip
                      formatter={(value: number) => [formatTokenNumber(value), '平均 Token / 次']}
                      labelFormatter={(label) => `日期 ${label}`}
                      contentStyle={{
                        borderRadius: 18,
                        border: '1px solid rgba(226,232,240,0.9)',
                        background: 'rgba(255,255,255,0.96)',
                        boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                        fontWeight: 700,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="avgTokens"
                      stroke="#8b5cf6"
                      strokeWidth={3}
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 0, fill: '#8b5cf6' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyPanel label="暂无负载走势数据" />
              )}
            </div>
          </PanelShell>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,0.78fr)_minmax(0,0.62fr)_minmax(0,1fr)]">
        <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(186,230,253,0.22),rgba(255,255,255,0.34))]">
          <PanelHeader icon={Cpu} kicker="模型分布" title="模型调用构成" />
          <div className="h-[250px]">
            {data.model_distribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.model_distribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={92}
                    paddingAngle={4}
                    dataKey="value"
                    stroke="rgba(255,255,255,0.88)"
                    strokeWidth={3}
                  >
                    {data.model_distribution.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => [formatNumber(value), '调用次数']}
                    contentStyle={{
                      borderRadius: 18,
                      border: '1px solid rgba(226,232,240,0.9)',
                      background: 'rgba(255,255,255,0.96)',
                      boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                      fontWeight: 700,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyPanel label="暂时还没有模型调用数据" />
            )}
          </div>
          <div className="rounded-[24px] border border-white/75 bg-white/55 px-4 py-4 text-center">
            <p className="text-xs font-black tracking-[0.18em] text-slate-400">累计模型调用</p>
            <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatNumber(totalModelCalls)}</p>
          </div>
          <DistributionLegend items={data.model_distribution} />
        </PanelShell>

        <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(254,240,138,0.22),rgba(255,255,255,0.34))]">
          <PanelHeader icon={Activity} kicker="调用混合" title="模型与工具占比" />
          <div className="h-[250px]">
            {callMix.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={callMix}
                    cx="50%"
                    cy="50%"
                    innerRadius={72}
                    outerRadius={96}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="rgba(255,255,255,0.88)"
                    strokeWidth={3}
                  >
                    {callMix.map((entry, index) => (
                      <Cell key={entry.name} fill={index === 0 ? '#0f172a' : '#14b8a6'} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => [formatNumber(value), '调用次数']}
                    contentStyle={{
                      borderRadius: 18,
                      border: '1px solid rgba(226,232,240,0.9)',
                      background: 'rgba(255,255,255,0.96)',
                      boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                      fontWeight: 700,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyPanel label="暂时还没有调用混合数据" />
            )}
          </div>
          <div className="space-y-3">
            {callMix.map((item, index) => (
              <div key={item.name} className="rounded-[22px] border border-white/75 bg-white/55 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-bold text-slate-700">{item.name}</span>
                  <span className="text-base font-black text-slate-950">{formatNumber(item.value)}</span>
                </div>
                <div className="mt-3 h-2 rounded-full bg-white/75">
                  <div
                    className={index === 0 ? 'h-2 rounded-full bg-slate-900' : 'h-2 rounded-full bg-teal-500'}
                    style={{
                      width: `${Math.max(
                        8,
                        Math.round((item.value / Math.max(data.summary.llm_calls + data.summary.tool_calls, 1)) * 100),
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </PanelShell>

        <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(196,181,253,0.22),rgba(255,255,255,0.34))]">
          <PanelHeader icon={Hammer} kicker="工具分布" title="工具调用排行" />
          <div className="h-[332px]">
            {data.tool_distribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={data.tool_distribution} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.18)" strokeDasharray="4 7" horizontal={false} />
                  <XAxis
                    type="number"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    tickFormatter={formatTokenNumber}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    width={92}
                  />
                  <Tooltip
                    formatter={(value: number) => [formatNumber(value), '调用次数']}
                    contentStyle={{
                      borderRadius: 18,
                      border: '1px solid rgba(226,232,240,0.9)',
                      background: 'rgba(255,255,255,0.96)',
                      boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                      fontWeight: 700,
                    }}
                  />
                  <Bar dataKey="value" radius={[0, 12, 12, 0]} barSize={16}>
                    {data.tool_distribution.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[(index + 2) % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyPanel label="暂时还没有工具调用数据" />
            )}
          </div>
          <div className="rounded-[24px] border border-white/75 bg-white/55 px-4 py-4 text-center">
            <p className="text-xs font-black tracking-[0.18em] text-slate-400">累计工具调用</p>
            <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{formatNumber(totalToolCalls)}</p>
          </div>
        </PanelShell>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <PanelShell tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(125,211,252,0.22),rgba(255,255,255,0.36))]">
          <PanelHeader icon={Trophy} kicker="用户热区" title="高负载用户分布" />
          <div className="h-[340px]">
            {topUsersChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={topUsersChartData} margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.18)" strokeDasharray="4 7" horizontal={false} />
                  <XAxis
                    type="number"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    tickFormatter={formatNumber}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }}
                    width={84}
                  />
                  <Tooltip
                    formatter={(value: number) => [formatTokenNumber(value), 'Token']}
                    contentStyle={{
                      borderRadius: 18,
                      border: '1px solid rgba(226,232,240,0.9)',
                      background: 'rgba(255,255,255,0.96)',
                      boxShadow: '0 18px 40px rgba(15,23,42,0.12)',
                      fontWeight: 700,
                    }}
                  />
                  <Bar dataKey="tokens" radius={[0, 12, 12, 0]} barSize={18}>
                    {topUsersChartData.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyPanel label="暂时还没有用户使用数据" />
            )}
          </div>
        </PanelShell>

        <section className="admin-data-panel">
          <div className="border-b border-white/60 px-6 py-5">
            <PanelHeader icon={Trophy} kicker="用户排行" title="资源消耗前列用户" />
          </div>

          <div className="admin-table-head grid-cols-[minmax(210px,1.2fr)_110px_110px_110px_110px_120px] lg:grid xl:grid">
            <span>用户</span>
            <span>Token</span>
            <span>模型调用</span>
            <span>工具调用</span>
            <span>平均耗时</span>
            <span>占比</span>
          </div>

          {topUsers.length > 0 ? (
            topUsers.map((user, index) => (
              <UserUsageRow key={user.user_id} user={user} index={index} maxTokens={maxUserTokens} />
            ))
          ) : (
            <div className="p-6">
              <EmptyPanel label="暂时还没有用户使用数据" />
            </div>
          )}
        </section>
      </section>
    </div>
  );
};
