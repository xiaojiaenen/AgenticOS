import React from 'react';
import {
 Area,
 AreaChart,
 Bar,
 BarChart,
 ResponsiveContainer,
 Tooltip,
 XAxis,
 YAxis,
} from 'recharts';
import { BarChart3, Clock, Loader2 } from 'lucide-react';
import { cn, formatDay, formatNumber } from '../../lib/utils';
import { ChartSkeleton } from '../ui/ChartSkeleton';
import { useIsGlassTheme } from '../liquid-glass';
import {
 AnalyticsData,
 getAnalytics,
} from '../../services/dashboardService';

interface ChatAnalyticsProps {
 timeRange: number;
}

export const ChatAnalytics: React.FC<ChatAnalyticsProps> = ({ timeRange }) => {
 const [data, setData] = React.useState<AnalyticsData | null>(null);
 const [loading, setLoading] = React.useState(false);
 const [error, setError] = React.useState<string | null>(null);
 const isGlass = useIsGlassTheme();

 const load = React.useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
   setData(await getAnalytics(timeRange));
  } catch (err) {
   setError(err instanceof Error ? err.message : '加载失败');
  } finally {
   setLoading(false);
  }
 }, [timeRange]);

 React.useEffect(() => { load(); }, [load]);

 if (loading && !data) {
  return (
   <div className="grid gap-5 lg:grid-cols-2">
    <div className={cn("rounded-lg border p-5 shadow-md", isGlass ? "bg-white/8 border-white/15" : "border-slate-200/80 bg-white/80")}>
     <div className={cn("mb-3 h-4 w-32 animate-pulse rounded", isGlass ? "bg-white/20" : "bg-slate-200")} />
     <ChartSkeleton variant="area" height={200} />
    </div>
    <div className={cn("rounded-lg border p-5 shadow-md", isGlass ? "bg-white/8 border-white/15" : "border-slate-200/80 bg-white/80")}>
     <div className={cn("mb-3 h-4 w-32 animate-pulse rounded", isGlass ? "bg-white/20" : "bg-slate-200")} />
     <ChartSkeleton variant="bar" height={200} />
    </div>
   </div>
  );
 }

 if (error) {
  return (
   <div className={cn("flex h-40 items-center justify-center rounded-lg border text-sm font-medium", isGlass ? "border-rose-600/30 bg-rose-900/20 text-rose-400" : "border-rose-200 bg-rose-50 text-rose-600")}>
    {error}
   </div>
  );
 }

 if (!data) return null;

 const timelineData = data.session_timeline.map((p) => ({
  ...p,
  label: formatDay(p.date),
 }));

 const hourlyData = data.hourly_distribution.map((p) => ({
  ...p,
  label: `${p.hour}:00`,
 }));

 const modeData = data.mode_distribution;

 return (
  <div className="space-y-5">
   <div className="grid gap-5 lg:grid-cols-2">
    {/* Session Timeline */}
    <div className={cn("rounded-lg border p-5 shadow-md", isGlass ? "bg-white/8 border-white/15" : "border-slate-200/80 bg-white/80")}>
     <div className="mb-4 flex items-center gap-2">
      <BarChart3 size={16} className={isGlass ? "text-white/40" : "text-slate-400"} />
      <h3 className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-700")}>会话趋势</h3>
     </div>
     <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={timelineData}>
       <defs>
        <linearGradient id="sessionGrad" x1="0" y1="0" x2="0" y2="1">
         <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.3} />
         <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
        </linearGradient>
       </defs>
       <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
       <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={35} />
       <Tooltip
        contentStyle={{ borderRadius: 12, border: isGlass ? '1px solid rgba(255,255,255,0.15)' : '1px solid #e2e8f0', fontSize: 12, background: isGlass ? 'rgba(0,0,0,0.8)' : '#fff' }}
        formatter={(value: number) => [`${value} 个会话`, '会话数']}
       />
       <Area type="monotone" dataKey="count" stroke="#0ea5e9" strokeWidth={2} fill="url(#sessionGrad)" />
      </AreaChart>
     </ResponsiveContainer>
    </div>

    {/* Hourly Distribution */}
    <div className={cn("rounded-lg border p-5 shadow-md", isGlass ? "bg-white/8 border-white/15" : "border-slate-200/80 bg-white/80")}>
     <div className="mb-4 flex items-center gap-2">
      <Clock size={16} className={isGlass ? "text-white/40" : "text-slate-400"} />
      <h3 className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-700")}>时段分布</h3>
     </div>
     <ResponsiveContainer width="100%" height={200}>
      <BarChart data={hourlyData}>
       <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} interval={2} />
       <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={35} />
       <Tooltip
        contentStyle={{ borderRadius: 12, border: isGlass ? '1px solid rgba(255,255,255,0.15)' : '1px solid #e2e8f0', fontSize: 12, background: isGlass ? 'rgba(0,0,0,0.8)' : '#fff' }}
        formatter={(value: number) => [`${value} 次`, '调用数']}
       />
       <Bar dataKey="count" radius={[4, 4, 0, 0]}>
        {hourlyData.map((entry, index) => (
         <rect
          key={index}
          fill={entry.count > Math.max(...hourlyData.map((d) => d.count)) * 0.7 ? '#0ea5e9' : '#cbd5e1'}
         />
        ))}
       </Bar>
      </BarChart>
     </ResponsiveContainer>
    </div>
   </div>

   {/* Mode Distribution */}
   {modeData.length > 0 && (
    <div className={cn("rounded-lg border p-5 shadow-md", isGlass ? "bg-white/8 border-white/15" : "border-slate-200/80 bg-white/80")}>
     <h3 className={cn("mb-4 text-sm font-semibold", isGlass ? "text-white" : "text-slate-700")}>模式使用分布</h3>
     <div className="flex flex-wrap gap-3">
      {modeData.map((item) => {
       const total = modeData.reduce((s, m) => s + m.count, 0);
       const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;
       return (
        <div key={item.mode} className={cn("flex items-center gap-2 rounded-xl border px-3 py-2", isGlass ? "bg-white/10 border-white/15" : "border-slate-200/80 bg-white")}>
         <div className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-800")}>{item.mode}</div>
         <div className={cn("text-xs font-medium", isGlass ? "text-gray-400" : "text-slate-500")}>{formatNumber(item.count)} ({pct}%)</div>
        </div>
       );
      })}
     </div>
    </div>
   )}
  </div>
 );
};
