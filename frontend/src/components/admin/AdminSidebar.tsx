import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, Bot, LogOut, MessageCircle, MessageSquare, Puzzle, Users } from 'lucide-react';
import { Logo } from '../Logo';
import { MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
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
        'relative z-20 flex h-full flex-shrink-0 flex-col overflow-hidden border-r border-white/70 bg-white/78 shadow-[10px_0_36px_rgba(15,23,42,0.06)] ring-1 ring-white/50 backdrop-blur-2xl',
        isMobile ? 'fixed inset-y-0 left-0 w-[296px] shadow-2xl' : 'w-[296px]',
        !isOpen && !isMobile && 'hidden',
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[linear-gradient(135deg,rgba(14,165,233,0.12),rgba(16,185,129,0.08),transparent)]" />

      <div className="relative z-10 flex items-center justify-between border-b border-white/70 px-4 py-4">
        <Logo iconSize={22} className="text-lg" />
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl p-2 text-slate-400 transition-colors hover:bg-white/80 hover:text-slate-700"
          aria-label="关闭导航"
        >
          <MenuIcon size={20} />
        </button>
      </div>

      <div className="relative z-10 px-4 pt-4">
        <div className="rounded-[20px] border border-white/80 bg-white/64 px-4 py-3 shadow-[0_12px_28px_rgba(15,23,42,0.045)]">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Admin Console</p>
          <p className="mt-1 text-sm font-black text-slate-950">AgenticOS 工作台</p>
        </div>
      </div>

      <div className="relative z-10 flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-1">
          {navItems.map((item) => {
            const active = activeTab === item.id;
            return (
              <motion.button
                key={item.id}
                type="button"
                onClick={() => handleSelect(item.id)}
                whileHover={{ x: 3 }}
                whileTap={{ scale: 0.985 }}
                className={cn(
                  'group relative flex w-full items-start gap-3 rounded-[18px] px-3 py-3 text-left transition-all',
                  active
                    ? 'text-zinc-900'
                    : 'text-slate-600 hover:bg-white/50 hover:text-slate-900',
                )}
              >
                {active && (
                  <motion.span
                    layoutId="admin-active-nav"
                    className="absolute inset-0 rounded-[18px] border border-white/80 bg-white/86 shadow-[0_12px_30px_rgba(15,23,42,0.08)]"
                    transition={{ type: 'spring', damping: 28, stiffness: 380 }}
                  />
                )}
                <div
                  className={cn(
                    'relative mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[15px] border transition-colors',
                    active
                      ? 'border-zinc-900 bg-zinc-900 text-white shadow-[0_10px_24px_rgba(15,23,42,0.22)]'
                      : 'border-white/70 bg-white/70 text-slate-500 group-hover:text-slate-700',
                  )}
                >
                  <item.icon size={18} />
                </div>
                <div className="relative min-w-0">
                  <p className="truncate text-sm font-black">{item.label}</p>
                  <p className="mt-1 line-clamp-2 text-xs font-medium leading-5 text-slate-400">{item.description}</p>
                </div>
              </motion.button>
            );
          })}
        </div>
      </div>

      <div className="relative z-10 border-t border-white/70 p-4">
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="mb-3 flex w-full items-center gap-3 rounded-[16px] bg-zinc-900 px-3 py-2.5 text-sm font-bold text-white shadow-[0_16px_32px_rgba(15,23,42,0.22)] transition-all hover:-translate-y-0.5 hover:bg-zinc-800"
        >
          <MessageCircle size={18} />
          进入对话
        </button>

        <div className="flex items-center gap-3 rounded-[16px] border border-white/70 bg-white/58 p-2 transition-colors hover:bg-white/82">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-[13px] border border-zinc-200 bg-zinc-100 text-zinc-600 shadow-sm">
            <UserAvatarIcon size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-bold text-slate-800">{user?.name || 'AgenticOS User'}</p>
            <p className="truncate text-[10px] font-medium text-slate-400">{user?.email || 'signed in'}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-xl p-2 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"
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
