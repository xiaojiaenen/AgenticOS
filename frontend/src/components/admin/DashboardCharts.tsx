import React from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Cpu, Hammer, Trophy } from 'lucide-react';
import { Card } from '../ui/Card';
import { DashboardDistributionItem, DashboardStats as DashboardStatsData, DashboardUserUsage } from '../../services/dashboardService';
import { cn } from '../../lib/utils';

interface DashboardChartsProps {
  data: DashboardStatsData;
}

const CHART_COLORS = ['#0f172a', '#0891b2', '#7c3aed', '#059669', '#f59e0b', '#e11d48', '#64748b', '#14b8a6'];

function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatDay(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(5);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function initials(name: string): string {
  return (name || 'U').slice(0, 1).toUpperCase();
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-[220px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white/35 text-sm font-bold text-slate-400">
      {label}
    </div>
  );
}

function DistributionLegend({ items }: { items: DashboardDistributionItem[] }) {
  return (
    <div className="mt-4 space-y-2">
      {items.slice(0, 5).map((item, index) => (
        <div key={item.name} className="flex items-center justify-between gap-3 text-xs font-bold">
          <span className="flex min-w-0 items-center gap-2 text-slate-600">
            <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} />
            <span className="truncate">{item.name}</span>
          </span>
          <span className="text-slate-900">{formatNumber(item.value)}</span>
        </div>
      ))}
    </div>
  );
}

function UserUsageRow({ user, index, maxTokens }: { user: DashboardUserUsage; index: number; maxTokens: number }) {
  const percentage = maxTokens > 0 ? Math.max(4, Math.round((user.total_tokens / maxTokens) * 100)) : 0;

  return (
    <div className="grid grid-cols-1 gap-4 border-b border-slate-100/80 px-5 py-4 last:border-b-0 lg:grid-cols-[minmax(220px,1.2fr)_120px_120px_120px_120px_150px] lg:items-center">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl border border-white/70 bg-gradient-to-br from-slate-50 to-cyan-50 text-sm font-black text-slate-700 shadow-sm">
          {initials(user.name)}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-black text-slate-400">#{index + 1}</span>
            <p className="truncate text-sm font-black text-slate-900">{user.name}</p>
          </div>
          <p className="mt-1 truncate text-xs font-medium text-slate-500">{user.email}</p>
        </div>
      </div>
      <div className="text-sm font-black text-slate-900">{formatNumber(user.total_tokens)}</div>
      <div className="text-sm font-bold text-slate-600">{formatNumber(user.llm_calls)}</div>
      <div className="text-sm font-bold text-slate-600">{formatNumber(user.tool_calls)}</div>
      <div className="text-sm font-bold text-slate-600">{formatNumber(user.sessions)}</div>
      <div className="h-2 rounded-full bg-slate-100">
        <div
          className={cn('h-2 rounded-full', index === 0 ? 'bg-slate-900' : index === 1 ? 'bg-cyan-500' : 'bg-violet-500')}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export const DashboardCharts = ({ data }: DashboardChartsProps) => {
  const topUsers = data.user_usage.slice(0, 8);
  const maxUserTokens = Math.max(...topUsers.map((user) => user.total_tokens), 0);
  const hasTrend = data.trend.some((item) => item.runs || item.tokens || item.tool_calls);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="p-6 xl:col-span-2">
          <div className="mb-6 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Usage Trend</p>
              <h3 className="mt-1 text-xl font-black tracking-tight text-slate-900">Token 与调用趋势</h3>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/60 px-3 py-2 text-xs font-black text-slate-500">
              最近 14 天
            </div>
          </div>
          <div className="h-80">
            {hasTrend ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.trend} margin={{ top: 12, right: 18, bottom: 4, left: 0 }}>
                  <defs>
                    <linearGradient id="tokensGradient" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="5%" stopColor="#0891b2" stopOpacity={0.38} />
                      <stop offset="95%" stopColor="#0891b2" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="runsGradient" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.22} />
                      <stop offset="95%" stopColor="#7c3aed" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 6" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={formatDay} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} tickFormatter={formatNumber} width={52} />
                  <Tooltip
                    formatter={(value: number, name: string) => [formatNumber(value), name === 'tokens' ? 'Token' : name === 'runs' ? '运行次数' : '工具调用']}
                    labelFormatter={(label) => `日期 ${label}`}
                    contentStyle={{ borderRadius: 18, border: '1px solid rgba(226,232,240,0.9)', boxShadow: '0 18px 40px rgba(15,23,42,0.12)', fontWeight: 700 }}
                    cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '4 6' }}
                  />
                  <Area type="monotone" dataKey="tokens" stroke="#0891b2" strokeWidth={3} fill="url(#tokensGradient)" activeDot={{ r: 6, strokeWidth: 0 }} />
                  <Area type="monotone" dataKey="runs" stroke="#7c3aed" strokeWidth={2.5} fill="url(#runsGradient)" activeDot={{ r: 5, strokeWidth: 0 }} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart label="暂无模型运行数据" />
            )}
          </div>
        </Card>

        <Card className="p-6">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-100 bg-white/70 text-slate-800">
              <Cpu size={20} />
            </div>
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Models</p>
              <h3 className="text-xl font-black tracking-tight text-slate-900">模型调用分布</h3>
            </div>
          </div>
          <div className="h-64">
            {data.model_distribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.model_distribution} cx="50%" cy="50%" innerRadius={58} outerRadius={88} paddingAngle={4} dataKey="value" stroke="rgba(255,255,255,0.85)" strokeWidth={3}>
                    {data.model_distribution.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [formatNumber(value), '调用次数']} contentStyle={{ borderRadius: 18, border: '1px solid rgba(226,232,240,0.9)', boxShadow: '0 18px 40px rgba(15,23,42,0.12)', fontWeight: 700 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart label="暂无模型调用" />
            )}
          </div>
          <DistributionLegend items={data.model_distribution} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="p-6">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-100 bg-white/70 text-slate-800">
              <Hammer size={20} />
            </div>
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Tools</p>
              <h3 className="text-xl font-black tracking-tight text-slate-900">工具使用排行</h3>
            </div>
          </div>
          <div className="h-72">
            {data.tool_distribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={data.tool_distribution} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 6" horizontal={false} />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} tickFormatter={formatNumber} />
                  <YAxis type="category" dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} width={86} />
                  <Tooltip formatter={(value: number) => [formatNumber(value), '调用次数']} contentStyle={{ borderRadius: 18, border: '1px solid rgba(226,232,240,0.9)', boxShadow: '0 18px 40px rgba(15,23,42,0.12)', fontWeight: 700 }} />
                  <Bar dataKey="value" radius={[0, 10, 10, 0]} barSize={16}>
                    {data.tool_distribution.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[(index + 2) % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart label="暂无工具调用" />
            )}
          </div>
        </Card>

        <Card className="overflow-hidden p-0 xl:col-span-2">
          <div className="flex items-center justify-between border-b border-white/70 p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-100 bg-white/70 text-slate-800">
                <Trophy size={20} />
              </div>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Users</p>
                <h3 className="text-xl font-black tracking-tight text-slate-900">用户资源消耗排行</h3>
              </div>
            </div>
          </div>
          <div className="hidden grid-cols-[minmax(220px,1.2fr)_120px_120px_120px_120px_150px] border-b border-slate-100 px-5 py-3 text-xs font-black uppercase tracking-widest text-slate-400 lg:grid">
            <span>用户</span>
            <span>Token</span>
            <span>模型调用</span>
            <span>工具调用</span>
            <span>Session</span>
            <span>占比</span>
          </div>
          {topUsers.length > 0 ? (
            topUsers.map((user, index) => (
              <UserUsageRow key={user.user_id} user={user} index={index} maxTokens={maxUserTokens} />
            ))
          ) : (
            <div className="p-6">
              <EmptyChart label="暂无用户使用数据" />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
