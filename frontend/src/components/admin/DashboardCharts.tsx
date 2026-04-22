import React from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { Card } from '../ui/Card';

const usageData = [
  { name: '周一', calls: 4000, users: 240 },
  { name: '周二', calls: 3000, users: 139 },
  { name: '周三', calls: 2000, users: 980 },
  { name: '周四', calls: 2780, users: 390 },
  { name: '周五', calls: 1890, users: 480 },
  { name: '周六', calls: 2390, users: 380 },
  { name: '周日', calls: 3490, users: 430 },
];

const modelData = [
  { name: 'GPT-5.4', value: 400 },
  { name: 'DeepSeek Chat', value: 300 },
  { name: 'Ollama (Llama3)', value: 300 },
  { name: 'Qwen 3', value: 200 },
];

const COLORS = ['#18181b', '#52525b', '#a1a1aa', '#e4e4e7'];

export const DashboardCharts = () => {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      {/* 折线图：API 调用趋势 */}
      <Card className="lg:col-span-2 p-6 hover:shadow-md transition-shadow">
        <h3 className="text-lg font-bold text-slate-800 mb-6">API 调用趋势</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={usageData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} dy={10} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} dx={-10} />
              <Tooltip 
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)' }}
                cursor={{ stroke: '#cbd5e1', strokeWidth: 1, strokeDasharray: '5 5' }}
              />
              <Line type="monotone" dataKey="calls" stroke="#18181b" strokeWidth={4} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 8 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* 饼图：模型使用占比 */}
      <Card className="p-6 hover:shadow-md transition-shadow">
        <h3 className="text-lg font-bold text-slate-800 mb-6">模型使用分布</h3>
        <div className="h-72 w-full flex flex-col items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={modelData}
                cx="50%"
                cy="45%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
                stroke="none"
              >
                {modelData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)' }}
              />
              <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: '12px', color: '#64748b' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
};
