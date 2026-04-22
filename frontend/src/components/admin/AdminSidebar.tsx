import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Users, MessageSquare, Settings, BarChart3, LogOut, ChevronRight, Cpu, Wrench } from 'lucide-react';
import { Logo } from '../Logo';

interface AdminSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const AdminSidebar = ({ activeTab, setActiveTab }: AdminSidebarProps) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('role');
    navigate('/login');
  };

  return (
    <div className="w-64 bg-white border-r border-slate-200 flex flex-col z-20 flex-shrink-0">
      <div className="p-6 flex items-center justify-between border-b border-slate-100">
        <Logo iconSize={24} showText={true} />
      </div>
      
      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
         <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-zinc-900 rounded-xl flex items-center justify-center text-white border border-slate-200 shadow-sm">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <div>
              <span className="block text-sm font-bold text-slate-800 leading-none mb-1">Admin Panel</span>
              <span className="block text-[10px] font-medium text-slate-500 uppercase tracking-widest">Workspace</span>
            </div>
         </div>
      </div>
      
      <nav className="flex-1 px-4 py-6 space-y-2">
        {[
          { id: 'dashboard', icon: BarChart3, label: '系统仪表盘' },
          { id: 'history', icon: MessageSquare, label: '对话历史' },
          { id: 'users', icon: Users, label: '用户管理' },
          { id: 'settings', icon: Wrench, label: '工具管理' },
          { id: 'models', icon: Cpu, label: '模型参数' },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all font-medium ${
              activeTab === item.id 
                ? 'bg-zinc-100 text-zinc-900 shadow-sm border border-zinc-200' 
                : 'text-slate-600 hover:bg-slate-50/80 hover:text-slate-900'
            }`}
          >
            <item.icon size={20} className={activeTab === item.id ? "text-zinc-800" : "text-slate-400"} />
            {item.label}
            {activeTab === item.id && <ChevronRight size={16} className="ml-auto opacity-70" />}
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-slate-100 space-y-2">
        <button 
          onClick={() => navigate('/chat')}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-zinc-100 hover:text-zinc-900 transition-colors text-slate-600 font-medium"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          回到对话
        </button>
        <button 
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-rose-50 hover:text-rose-600 transition-colors text-slate-500 font-medium"
        >
          <LogOut size={20} />
          退出登录
        </button>
      </div>
    </div>
  );
};
