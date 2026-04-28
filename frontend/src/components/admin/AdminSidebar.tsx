import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, Bot, LogOut, MessageCircle, MessageSquare, Puzzle, Users } from 'lucide-react';
import { Logo } from '../Logo';
import { MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { RandomMascot } from '../ui/RandomMascot';
import { getStoredUser, logout } from '../../services/authService';
import { cn } from '../../lib/utils';

interface AdminSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isMobile: boolean;
  isOpen: boolean;
  onClose: () => void;
}

const navItems = [
  { id: 'dashboard', icon: BarChart3, label: '系统总览', description: '查看用户、会话和资源统计' },
  { id: 'history', icon: MessageSquare, label: '聊天记录', description: '检索会话与查看完整详情' },
  { id: 'users', icon: Users, label: '用户管理', description: '管理账号、角色和启用状态' },
  { id: 'agents', icon: Bot, label: '智能体配置', description: '维护智能体、工具审批与绑定' },
  { id: 'skills', icon: Puzzle, label: 'Skill 管理', description: '管理本地 Skill 与脚本目录' },
] as const;

export const AdminSidebar = React.memo(({ activeTab, setActiveTab, isMobile, isOpen, onClose }: AdminSidebarProps) => {
  const navigate = useNavigate();
  const user = getStoredUser();

  const handleSelect = (tab: string) => {
    setActiveTab(tab);
    if (isMobile) {
      onClose();
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <motion.aside
      initial={isMobile ? { x: -300 } : { width: 296 }}
      animate={{ x: 0, width: 296 }}
      exit={isMobile ? { x: -300 } : { width: 0 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className={cn(
        'relative z-20 flex h-full flex-shrink-0 flex-col overflow-hidden border-r border-white/40 bg-white/60 shadow-[4px_0_24px_rgba(0,0,0,0.03)] backdrop-blur-2xl',
        isMobile ? 'fixed inset-y-0 left-0 w-[296px] shadow-2xl' : 'w-[296px]',
        !isOpen && !isMobile && 'hidden',
      )}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <RandomMascot size={300} className="absolute -bottom-16 -right-16 text-slate-900 opacity-[0.03]" />
      </div>

      <div className="relative z-10 flex items-center justify-between border-b border-slate-100 px-4 py-4">
        <Logo iconSize={22} className="text-lg" />
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
          aria-label="关闭导航"
        >
          <MenuIcon size={20} />
        </button>
      </div>

      <div className="relative z-10 flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-1">
          {navItems.map((item) => {
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelect(item.id)}
                className={cn(
                  'group flex w-full items-start gap-3 rounded-2xl px-3 py-3 text-left transition-all',
                  active
                    ? 'border border-white/65 bg-white/78 text-zinc-900 shadow-[0_2px_10px_rgba(0,0,0,0.05)]'
                    : 'text-slate-600 hover:bg-white/45 hover:text-slate-900',
                )}
              >
                <div
                  className={cn(
                    'mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl border transition-colors',
                    active
                      ? 'border-zinc-900 bg-zinc-900 text-white'
                      : 'border-white/70 bg-white/65 text-slate-500 group-hover:text-slate-700',
                  )}
                >
                  <item.icon size={18} />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-black">{item.label}</p>
                  <p className="mt-1 line-clamp-2 text-xs font-medium leading-5 text-slate-400">{item.description}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="relative z-10 border-t border-slate-100 p-4">
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="mb-3 flex w-full items-center gap-3 rounded-xl bg-zinc-900 px-3 py-2.5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-zinc-800"
        >
          <MessageCircle size={18} />
          进入对话
        </button>

        <div className="flex items-center gap-3 rounded-xl p-2 transition-colors hover:bg-slate-50">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-zinc-200 bg-zinc-100 text-zinc-600 shadow-sm">
            <UserAvatarIcon size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-bold text-slate-800">{user?.name || 'AgenticOS User'}</p>
            <p className="truncate text-[10px] font-medium text-slate-400">{user?.email || 'signed in'}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"
            title="退出登录"
            aria-label="退出登录"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </motion.aside>
  );
});

AdminSidebar.displayName = 'AdminSidebar';
