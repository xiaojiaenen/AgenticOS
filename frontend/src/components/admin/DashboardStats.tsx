import React from 'react';
import { Users, MessageSquare, Server, Activity } from 'lucide-react';
import { Card } from '../ui/Card';

export const DashboardStats = () => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <Card className="p-6 relative overflow-hidden group hover:shadow-md transition-shadow">
        <div className="absolute top-0 right-0 w-32 h-32 bg-zinc-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 group-hover:opacity-70 transition-opacity"></div>
        <div className="flex items-center gap-4 mb-4 relative z-10">
          <div className="p-3.5 bg-zinc-100 text-zinc-900 rounded-xl border border-zinc-200">
            <Users size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 font-bold uppercase tracking-wider">总用户数</p>
            <p className="text-3xl font-black text-slate-800 tracking-tight">1,248</p>
          </div>
        </div>
        <div className="text-sm text-emerald-500 font-bold flex items-center gap-1.5 relative z-10 bg-emerald-50 w-fit px-3 py-1 rounded-full border border-emerald-100">
          <Activity size={14} /> +12% 较上周
        </div>
      </Card>
      
      <Card className="p-6 relative overflow-hidden group hover:shadow-md transition-shadow">
        <div className="absolute top-0 right-0 w-32 h-32 bg-zinc-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 group-hover:opacity-70 transition-opacity"></div>
        <div className="flex items-center gap-4 mb-4 relative z-10">
          <div className="p-3.5 bg-zinc-100 text-zinc-900 rounded-xl border border-zinc-200">
            <MessageSquare size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 font-bold uppercase tracking-wider">总对话数</p>
            <p className="text-3xl font-black text-slate-800 tracking-tight">45,912</p>
          </div>
        </div>
        <div className="text-sm text-emerald-500 font-bold flex items-center gap-1.5 relative z-10 bg-emerald-50 w-fit px-3 py-1 rounded-full border border-emerald-100">
          <Activity size={14} /> +24% 较上周
        </div>
      </Card>
      
      <Card className="p-6 relative overflow-hidden group hover:shadow-md transition-shadow">
        <div className="absolute top-0 right-0 w-32 h-32 bg-zinc-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 group-hover:opacity-70 transition-opacity"></div>
        <div className="flex items-center gap-4 mb-4 relative z-10">
          <div className="p-3.5 bg-zinc-100 text-zinc-900 rounded-xl border border-zinc-200">
            <Server size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 font-bold uppercase tracking-wider">API 调用量</p>
            <p className="text-3xl font-black text-slate-800 tracking-tight">1.2M</p>
          </div>
        </div>
        <div className="text-sm text-rose-500 font-bold flex items-center gap-1.5 relative z-10 bg-rose-50 w-fit px-3 py-1 rounded-full border border-rose-100">
          <Activity size={14} /> 接近配额限制
        </div>
      </Card>
    </div>
  );
};
