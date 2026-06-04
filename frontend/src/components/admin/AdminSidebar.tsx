import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, BellRing, Bot, Brain, LogOut, MessageCircle, MessageSquare, Plug, Puzzle, Users } from 'lucide-react';
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
  { id: 'history', icon: MessageSquare, label: '聊天记录', description: '检索会话并查看完整详情' },
  { id: 'users', icon: Users, label: '用户管理', description: '管理账号、角色和启用状态' },
  { id: 'agents', icon: Bot, label: '智能体配置', description: '维护智能体、工具审批与绑定' },
  { id: 'skills', icon: Puzzle, label: 'Skill 管理', description: '管理本地 Skill 与脚本目录' },
  { id: 'integrations', icon: Plug, label: '集成管理', description: '管理第三方集成与 API 接口' },
  { id: 'announcements', icon: BellRing, label: '公告设计', description: '设计用户进入系统时看到的公告' },
  { id: 'memory', icon: Brain, label: '记忆管理', description: '查看和管理 AI 学到的用户记忆' },
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
        'relative z-20 flex h-full flex-shrink-0 flex-col overflow-hidden border-r border-white/70 bg-[var(--admin-sidebar-bg)] shadow-[10px_0_36px_rgba(15,23,42,0.06)] ring-1 ring-white/50 backdrop-blur-2xl',
        isMobile ? 'fixed inset-y-0 left-0 w-[296px] shadow-2xl' : 'w-[296px]',
        !isOpen && !isMobile && 'hidden',
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-br from-[var(--admin-accent-soft)] to-transparent" />

      <div className="relative z-10 flex items-center justify-between border-b border-white/70 px-4 py-4">
        <Logo iconSize={22} className="text-lg" />
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl p-2 text-slate-400 transition-all hover:bg-white/80 hover:text-slate-700 hover:shadow-sm active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2"
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
              <motion.button
                key={item.id}
                type="button"
                onClick={() => handleSelect(item.id)}
                whileTap={{ scale: 0.985 }}
                className={cn(
                  'admin-nav-item focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2',
                  active ? 'admin-nav-item-active text-zinc-900' : 'text-slate-600 hover:text-slate-900',
                )}
              >
                {active && (
                  <motion.span
                    layoutId="admin-active-nav"
                    className="absolute inset-0 rounded-2xl bg-[var(--admin-card-bg)] border-l-3 border-l-[var(--admin-accent)] shadow-md"
                    transition={{ type: 'spring', damping: 28, stiffness: 380 }}
                  />
                )}
                <div
                  className={cn(
                    'admin-nav-icon',
                    active
                      ? 'border-zinc-900 bg-zinc-900 text-white shadow-button'
                      : 'border-white/70 bg-white/70 text-slate-500 group-hover:text-slate-700',
                  )}
                >
                  <item.icon size={18} />
                </div>
                <div className="relative min-w-0">
                  <p className="truncate text-sm font-black">{item.label}</p>
                  <p className="mt-1 line-clamp-2 text-xs font-medium leading-5 text-slate-400">{item.description}</p>
                </div>
                {active && (
                  <motion.div
                    layoutId="admin-active-dot"
                    className="absolute right-3 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-sky-500"
                    transition={{ type: 'spring', damping: 25, stiffness: 350 }}
                  />
                )}
              </motion.button>
            );
          })}
        </div>
      </div>

      <div className="relative z-10 space-y-3 border-t border-white/70 p-4">
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="flex w-full items-center gap-3 rounded-2xl bg-zinc-900 px-3 py-2.5 text-sm font-bold text-white shadow-lg transition-all hover:-translate-y-0.5 hover:bg-zinc-800 hover:shadow-button active:translate-y-0 focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2"
        >
          <MessageCircle size={18} />
          进入对话
        </button>

        <div className="flex items-center gap-3 rounded-2xl border border-[var(--admin-card-border)] bg-[var(--admin-card-bg)] p-2.5 shadow-sm transition-all hover:shadow-md">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-zinc-200 bg-[linear-gradient(135deg,rgba(15,23,42,0.06),rgba(255,255,255,0.9))] text-zinc-600 shadow-sm">
            <UserAvatarIcon size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-bold text-slate-800">{user?.name || 'AgenticOS User'}</p>
            <p className="truncate text-[10px] font-medium text-slate-400">{user?.email || 'signed in'}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-xl p-2 text-slate-400 transition-all hover:bg-rose-50 hover:text-rose-500 hover:scale-110 active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2"
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
