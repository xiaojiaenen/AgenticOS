import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, Bot, ChevronRight, LogOut, MessageSquare, Users, Wrench } from 'lucide-react';
import { Logo } from '../Logo';
import { getStoredUser, logout } from '../../services/authService';
import { UserAvatarIcon } from '../ui/AnimatedIcons';
import { cn } from '../../lib/utils';

interface AdminSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const AdminSidebar = ({ activeTab, setActiveTab }: AdminSidebarProps) => {
  const navigate = useNavigate();
  const user = getStoredUser();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const items = [
    { id: 'dashboard', icon: BarChart3, label: '系统仪表盘' },
    { id: 'history', icon: MessageSquare, label: '对话历史' },
    { id: 'users', icon: Users, label: '用户管理' },
    { id: 'agents', icon: Bot, label: '智能体配置' },
    { id: 'settings', icon: Wrench, label: '工具管理' },
  ];

  return (
    <motion.aside
      initial={{ x: -24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className="z-20 flex h-full w-[280px] flex-shrink-0 flex-col overflow-hidden border-r border-white/40 bg-white/60 shadow-[4px_0_24px_rgba(0,0,0,0.03)] backdrop-blur-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-100/80 p-4">
        <Logo iconSize={20} className="text-lg" showText={true} />
      </div>

      <div className="border-b border-slate-100/80 px-4 py-4">
        <div className="rounded-2xl border border-white/70 bg-white/60 p-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-900 text-white shadow-sm">
              <UserAvatarIcon size={20} />
            </div>
            <div className="min-w-0">
              <span className="block truncate text-sm font-black leading-none text-slate-800">
                {user?.name || 'Admin'}
              </span>
              <span className="mt-1 block truncate text-[10px] font-bold uppercase tracking-widest text-slate-400">
                管理工作台
              </span>
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-2 px-4 py-5">
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={cn(
              'flex w-full items-center gap-3 rounded-xl px-4 py-3 font-bold transition-all',
              activeTab === item.id
                ? 'border border-white/70 bg-white/75 text-zinc-900 shadow-[0_2px_12px_rgba(15,23,42,0.05)]'
                : 'text-slate-600 hover:bg-white/45 hover:text-slate-900',
            )}
          >
            <item.icon size={20} className={activeTab === item.id ? 'text-zinc-800' : 'text-slate-400'} />
            {item.label}
            {activeTab === item.id && <ChevronRight size={16} className="ml-auto opacity-70" />}
          </button>
        ))}
      </nav>

      <div className="space-y-2 border-t border-slate-100/80 p-4">
        <button
          onClick={() => navigate('/chat')}
          className="flex w-full items-center gap-3 rounded-xl px-4 py-3 font-bold text-slate-600 transition-colors hover:bg-white/60 hover:text-zinc-900"
        >
          <MessageSquare size={20} />
          回到对话
        </button>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-xl px-4 py-3 font-bold text-slate-500 transition-colors hover:bg-rose-50 hover:text-rose-600"
        >
          <LogOut size={20} />
          退出登录
        </button>
      </div>
    </motion.aside>
  );
};
