/**
 * 聊天分析：TanStack Query 数据层 + shadcn 样式。
 * 后端 API 不变（services/dashboardService.ts 的 getAnalytics）。
 */
import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { BarChart3, Clock } from 'lucide-react';
import { formatDay, formatNumber } from '@/lib/utils';
import { ChartSkeleton } from '@/components/ui/ChartSkeleton';
import { AnalyticsData, getAnalytics } from '@/services/dashboardService';

interface ChatAnalyticsProps {
  timeRange: number;
}

export const ChatAnalytics: React.FC<ChatAnalyticsProps> = ({ timeRange }) => {
  const analyticsQuery = useQuery({
    queryKey: ['admin', 'analytics', timeRange],
    queryFn: () => getAnalytics(timeRange),
  });

  if (analyticsQuery.isPending) {
    return (
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="mb-3 h-4 w-32 animate-pulse rounded bg-zinc-200" />
          <ChartSkeleton variant="area" height={200} />
        </div>
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="mb-3 h-4 w-32 animate-pulse rounded bg-zinc-200" />
          <ChartSkeleton variant="bar" height={200} />
        </div>
      </div>
    );
  }

  if (analyticsQuery.isError) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-sm font-medium text-rose-600">
        {(analyticsQuery.error as Error).message || '加载失败'}
      </div>
    );
  }

  const data: AnalyticsData | undefined = analyticsQuery.data;
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
  const maxHourly = Math.max(...hourlyData.map((d) => d.count), 0);

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Session Timeline */}
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 size={16} className="text-zinc-400" />
            <h3 className="text-sm font-semibold text-zinc-700">会话趋势</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={timelineData}>
              <defs>
                <linearGradient id="sessionGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={35} />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: '1px solid #e4e4e7', fontSize: 12, background: '#fff' }}
                formatter={(value) => [`${value} 个会话`, '会话数']}
              />
              <Area type="monotone" dataKey="count" stroke="#4f46e5" strokeWidth={2} fill="url(#sessionGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Hourly Distribution */}
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Clock size={16} className="text-zinc-400" />
            <h3 className="text-sm font-semibold text-zinc-700">时段分布</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={hourlyData}>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={35} />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: '1px solid #e4e4e7', fontSize: 12, background: '#fff' }}
                formatter={(value) => [`${value} 次`, '调用数']}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {hourlyData.map((entry, index) => (
                  <rect
                    key={index}
                    fill={maxHourly > 0 && entry.count > maxHourly * 0.7 ? '#4f46e5' : '#d4d4d8'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Mode Distribution */}
      {modeData.length > 0 && (
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-zinc-700">模式使用分布</h3>
          <div className="flex flex-wrap gap-3">
            {modeData.map((item) => {
              const total = modeData.reduce((s, m) => s + m.count, 0);
              const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;
              return (
                <div
                  key={item.mode}
                  className="flex items-center gap-2 rounded-lg border border-zinc-200/80 bg-white px-3 py-2 shadow-sm"
                >
                  <div className="text-sm font-semibold text-zinc-800">{item.mode}</div>
                  <div className="text-xs font-medium text-zinc-500">
                    {formatNumber(item.count)} ({pct}%)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
