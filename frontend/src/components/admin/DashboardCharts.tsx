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
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { cn, formatNumber, formatTokenNumber, formatLatency, formatDay, shortName, initials, CHART_COLORS } from '../../lib/utils';
import {
 DashboardDistributionItem,
 DashboardStats as DashboardStatsData,
 DashboardUserUsage,
} from '../../services/dashboardService';
import { useIsGlassTheme } from '../liquid-glass';

interface DashboardChartsProps {
 data: DashboardStatsData;
}


function EmptyPanel({ label }: { label: string }) {
 const isGlass = useIsGlassTheme();
 return (
  <div className={cn(
   "flex h-full min-h-[200px] items-center justify-center rounded-lg border border-dashed text-sm font-medium",
   isGlass ? "border-white/20 bg-white/5 text-gray-400" : "border-slate-200/80 bg-white/30 text-slate-500"
  )}>
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
 const isGlass = useIsGlassTheme();
 return (
  <div className="mb-5 flex items-start justify-between gap-4">
   <div className="flex items-center gap-3">
    <div className={cn(
     "flex h-11 w-11 items-center justify-center rounded-lg shadow-sm",
     isGlass ? "bg-white/10 text-white border border-white/15" : "border border-slate-200 bg-white text-slate-900"
    )}>
     <Icon size={20} />
    </div>
    <div>
     <p className={cn("admin-section-kicker", isGlass && "text-gray-400")}>{kicker}</p>
     <h3 className={cn("mt-1 text-[22px] font-semibold tracking-tight", isGlass ? "text-white" : "text-slate-950")}>{title}</h3>
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
 delay = 0,
}: {
 className?: string;
 children: React.ReactNode;
 tone?: string;
 delay?: number;
}) {
 const isGlass = useIsGlassTheme();

 if (isGlass) {
  return (
   <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.45, delay, ease: [0.16, 1, 0.3, 1] }}
   >
    <LiquidGlass
     {...glassPresets.card}
     tint="rgba(255,255,255,0.06)"
     radius={12}
     className={className}
     style={{ height: '100%' }}
    >
     <div className="relative h-full px-5 py-5">{children}</div>
    </LiquidGlass>
   </motion.div>
  );
 }

 return (
  <motion.section
   initial={{ opacity: 0, y: 20 }}
   animate={{ opacity: 1, y: 0 }}
   transition={{ duration: 0.45, delay, ease: [0.16, 1, 0.3, 1] }}
   className={cn(
    'admin-chart-panel',
    tone ?? 'bg-white/80',
    className,
   )}
  >
   <div className="relative h-full px-5 py-5">{children}</div>
  </motion.section>
 );
}

function DistributionLegend({ items }: { items: DashboardDistributionItem[] }) {
 const isGlass = useIsGlassTheme();
 return (
  <div className="mt-4 space-y-2.5">
   {items.slice(0, 5).map((item, index) => (
    <div key={item.name} className="flex items-center justify-between gap-3 text-sm font-medium">
     <span className={cn("flex min-w-0 items-center gap-2.5", isGlass ? "text-gray-300" : "text-slate-700")}>
      <span
       className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
       style={{ background: CHART_COLORS[index % CHART_COLORS.length] }}
      />
      <span className="truncate">{item.name}</span>
     </span>
     <span className={isGlass ? "text-white" : "text-slate-950"}>{formatNumber(item.value)}</span>
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
 const isGlass = useIsGlassTheme();
 const percentage = maxTokens > 0 ? Math.max(8, Math.round((user.total_tokens / maxTokens) * 100)) : 0;

 return (
  <motion.div
   initial={{ opacity: 0, y: 8 }}
   animate={{ opacity: 1, y: 0 }}
   transition={{ duration: 0.22, delay: Math.min(index * 0.03, 0.16) }}
   whileHover={{ x: 2 }}
   className={cn("admin-table-row grid grid-cols-1 gap-4 border-b px-5 py-4 text-center last:border-b-0 lg:grid-cols-[minmax(210px,1.2fr)_110px_110px_110px_110px_120px] lg:items-center lg:gap-0",
     isGlass ? "border-white/10" : "border-slate-200/60"
   )}
  >
   <div className="flex min-w-0 items-center justify-center gap-4">
    <div className={cn("flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-sm font-semibold shadow-sm",
      isGlass ? "border border-white/20 bg-white/10 text-white" : "border border-slate-200 bg-white/80 text-slate-800"
    )}>
     {initials(user.name)}
    </div>
    <div className="min-w-0">
     <div className="flex items-center justify-center gap-2">
      <span className={cn("text-xs font-semibold", isGlass ? "text-gray-400" : "text-slate-400")}>#{index + 1}</span>
      <p className={cn("truncate text-sm font-semibold", isGlass ? "text-white" : "text-slate-900")}>{user.name}</p>
     </div>
     <p className={cn("mt-1 truncate text-xs font-medium", isGlass ? "text-gray-400" : "text-slate-500")}>{user.email}</p>
    </div>
   </div>
   <div className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-900")}>{formatTokenNumber(user.total_tokens)}</div>
   <div className={cn("text-sm font-medium", isGlass ? "text-gray-300" : "text-slate-600")}>{formatNumber(user.llm_calls)}</div>
   <div className={cn("text-sm font-medium", isGlass ? "text-gray-300" : "text-slate-600")}>{formatNumber(user.tool_calls)}</div>
   <div className={cn("text-sm font-medium", isGlass ? "text-gray-300" : "text-slate-600")}>{formatLatency(user.avg_latency_ms)}</div>
   <div className={cn("h-2 rounded-full", isGlass ? "bg-white/20" : "bg-white")}>
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
 const isGlass = useIsGlassTheme();
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
   <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_340px]">
    <PanelShell delay={0.05} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.62),rgba(255,255,255,0.38),rgba(186,230,253,0.34))]">
     <PanelHeader
      icon={Waves}
      kicker="趋势主视图"
      title="Token、运行与工具节奏"
      extra={
       <div className="rounded-full border border-slate-200 bg-white/80 px-3 py-2 text-xs font-semibold text-slate-500">
        最近 {trendData.length || 14} 个统计点
       </div>
      }
     />

     <div className="mb-4 grid gap-3 sm:grid-cols-4">
      {trendSignals.map((item) => (
       <LiquidGlass
        key={item.label}
        {...glassPresets.control}
        tint="rgba(255,255,255,0.04)"
        radius={12}
        style={{ padding: '10px 12px' }}
       >
        <p className={cn("text-[10px] font-semibold tracking-[0.08em]", isGlass ? "text-gray-400" : "text-slate-400")}>{item.label}</p>
        <p className={cn("mt-1 text-base font-semibold tracking-tight", isGlass ? "text-white" : "text-slate-950")}>{item.value}</p>
       </LiquidGlass>
      ))}
     </div>

     <div className="h-[320px]">
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
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
          dy={10}
         />
         <YAxis
          yAxisId="left"
          axisLine={false}
          tickLine={false}
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
          tickFormatter={formatTokenNumber}
          width={56}
         />
         <YAxis
          yAxisId="right"
          orientation="right"
          axisLine={false}
          tickLine={false}
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
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
      {trendSignals.map((item) => (
       <LiquidGlass
        key={item.label}
        {...glassPresets.control}
        tint="rgba(255,255,255,0.04)"
        radius={12}
        style={{ padding: '14px 16px' }}
       >
        <p className={cn("text-xs font-semibold tracking-[0.08em]", isGlass ? "text-gray-400" : "text-slate-400")}>{item.label}</p>
        <p className={cn("mt-2 text-2xl font-semibold tracking-tight", isGlass ? "text-white" : "text-slate-950")}>{item.value}</p>
       </LiquidGlass>
      ))}
     </div>
    </PanelShell>

    <div className="grid gap-5">
     <PanelShell delay={0.12} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(224,242,254,0.48),rgba(255,255,255,0.36))]">
      <PanelHeader icon={Activity} kicker="运行脉冲" title="最近几天调用强度" />
      <div className="h-[240px]">
       {pulseData.length > 0 ? (
        <ResponsiveContainer width="100%" height="100%">
         <BarChart data={pulseData} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="4 7" vertical={false} />
          <XAxis
           dataKey="date"
           tickFormatter={formatDay}
           axisLine={false}
           tickLine={false}
           tick={{ fill: '#475569', fontSize: 11, fontWeight: 700 }}
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

     <PanelShell delay={0.18} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(233,213,255,0.34),rgba(255,255,255,0.36))]">
      <PanelHeader icon={Gauge} kicker="效率水位" title="单次运行负载走势" />
      <div className="h-[240px]">
       {hasTrend ? (
        <ResponsiveContainer width="100%" height="100%">
         <LineChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="4 7" vertical={false} />
          <XAxis
           dataKey="date"
           tickFormatter={formatDay}
           axisLine={false}
           tickLine={false}
           tick={{ fill: '#475569', fontSize: 11, fontWeight: 700 }}
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
    <PanelShell delay={0.24} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(186,230,253,0.22),rgba(255,255,255,0.34))]">
     <PanelHeader icon={Cpu} kicker="模型分布" title="模型调用构成" />
     <div className="h-[260px]">
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
     <LiquidGlass
      {...glassPresets.control}
      tint="rgba(255,255,255,0.04)"
      radius={12}
      style={{ padding: '16px', textAlign: 'center' }}
     >
      <p className={cn("text-xs font-semibold tracking-[0.08em]", isGlass ? "text-gray-400" : "text-slate-400")}>累计模型调用</p>
      <p className={cn("mt-2 text-2xl font-semibold tracking-tight", isGlass ? "text-white" : "text-slate-950")}>{formatNumber(totalModelCalls)}</p>
     </LiquidGlass>
     <DistributionLegend items={data.model_distribution} />
    </PanelShell>

    <PanelShell delay={0.30} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(254,240,138,0.22),rgba(255,255,255,0.34))]">
     <PanelHeader icon={Activity} kicker="调用混合" title="模型与工具占比" />
     <div className="h-[260px]">
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
       <LiquidGlass
        key={item.name}
        {...glassPresets.control}
        tint="rgba(255,255,255,0.04)"
        radius={12}
        style={{ padding: '12px 16px' }}
       >
        <div className="flex items-center justify-between gap-3">
         <span className={cn("text-sm font-medium", isGlass ? "text-gray-300" : "text-slate-700")}>{item.name}</span>
         <span className={cn("text-base font-semibold", isGlass ? "text-white" : "text-slate-950")}>{formatNumber(item.value)}</span>
        </div>
        <div className="admin-progress-bar mt-3">
         <div
          className={cn('admin-progress-fill', index === 0 ? 'bg-slate-900' : 'bg-teal-500')}
          style={{
           width: `${Math.max(
            8,
            Math.round((item.value / Math.max(data.summary.llm_calls + data.summary.tool_calls, 1)) * 100),
           )}%`,
          }}
         />
        </div>
       </LiquidGlass>
      ))}
     </div>
    </PanelShell>

    <PanelShell delay={0.36} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(196,181,253,0.22),rgba(255,255,255,0.34))]">
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
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
          tickFormatter={formatTokenNumber}
         />
         <YAxis
          type="category"
          dataKey="name"
          axisLine={false}
          tickLine={false}
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
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
     <LiquidGlass
      {...glassPresets.control}
      tint="rgba(255,255,255,0.04)"
      radius={12}
      style={{ padding: '16px', textAlign: 'center' }}
     >
      <p className={cn("text-xs font-semibold tracking-[0.08em]", isGlass ? "text-gray-400" : "text-slate-400")}>累计工具调用</p>
      <p className={cn("mt-2 text-2xl font-semibold tracking-tight", isGlass ? "text-white" : "text-slate-950")}>{formatNumber(totalToolCalls)}</p>
     </LiquidGlass>
    </PanelShell>
   </section>

   <section className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
    <PanelShell delay={0.42} tone="bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(125,211,252,0.22),rgba(255,255,255,0.36))]">
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
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
          tickFormatter={formatNumber}
         />
         <YAxis
          type="category"
          dataKey="name"
          axisLine={false}
          tickLine={false}
          tick={{ fill: '#475569', fontSize: 12, fontWeight: 700 }}
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

    <section className={cn("admin-data-panel", isGlass && "border border-white/10 bg-white/5 rounded-xl")}>
     <div className={cn("border-b px-5 py-4", isGlass ? "border-white/10" : "border-slate-200/60")}>
      <PanelHeader icon={Trophy} kicker="用户排行" title="资源消耗前列用户" />
     </div>

     <div className={cn("admin-table-head grid-cols-[minmax(210px,1.2fr)_110px_110px_110px_110px_120px] lg:grid xl:grid",
       isGlass && "text-gray-300"
     )}>
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
      <div className="p-4">
       <EmptyPanel label="暂时还没有用户使用数据" />
      </div>
     )}
    </section>
   </section>
  </div>
 );
};
