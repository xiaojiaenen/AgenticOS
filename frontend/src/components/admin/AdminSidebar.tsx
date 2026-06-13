import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, BellRing, Bot, Brain, LogOut, MessageCircle, MessageSquare, Plug, Puzzle, Users } from 'lucide-react';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { Logo } from '../Logo';
import { MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { getStoredUser, logout } from '../../services/authService';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';

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
 const isGlass = useIsGlassTheme();

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
    'relative z-20 flex h-full flex-shrink-0 flex-col overflow-hidden border-r border-slate-200/80 bg-[var(--admin-sidebar-bg)] shadow-[10px_0_36px_rgba(15,23,42,0.06)] backdrop-blur-2xl',
    isMobile ? 'fixed inset-y-0 left-0 w-[296px] shadow-lg' : 'w-[296px]',
    !isOpen && !isMobile && 'hidden',
   )}
  >
   <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-br from-[var(--admin-accent-soft)] to-transparent" />

   <div className={cn("relative z-10 flex items-center justify-between border-b px-4 py-4", isGlass ? "border-white/10" : "border-slate-200/80")}>
    <Logo iconSize={22} className="text-lg" />
    <button
     type="button"
     onClick={onClose}
     className={cn(
      "rounded-xl p-2 transition-all active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2",
      isGlass ? "text-white/70 hover:bg-white/10 hover:text-white" : "text-slate-400 hover:bg-white hover:text-slate-700 hover:shadow-sm"
     )}
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
         active
          ? isGlass ? 'admin-nav-item-active text-white' : 'admin-nav-item-active text-zinc-900'
          : isGlass ? 'text-white/70 hover:text-white' : 'text-slate-600 hover:text-slate-900',
        )}
       >
        {active && (
         <motion.span
          layoutId="admin-active-nav"
          className={cn(
           "absolute inset-0 rounded-lg border-l-3 shadow-md",
           isGlass ? "bg-white/10 border-l-sky-400" : "bg-[var(--admin-card-bg)] border-l-[var(--admin-accent)]"
          )}
          transition={{ type: 'spring', damping: 28, stiffness: 380 }}
         />
        )}
        <div
         className={cn(
          'admin-nav-icon',
          active
           ? isGlass ? 'border-sky-400 bg-sky-400 text-white shadow-button' : 'border-zinc-900 bg-zinc-900 text-white shadow-button'
           : isGlass ? 'border-white/20 bg-white/10 text-white/70 group-hover:text-white' : 'border-slate-200/80 bg-white/80 text-slate-500 group-hover:text-slate-700',
         )}
        >
         <item.icon size={18} />
        </div>
        <div className="relative min-w-0">
         <p className="truncate text-sm font-semibold">{item.label}</p>
         <p className={cn("mt-1 line-clamp-2 text-xs font-medium leading-5", isGlass ? "text-white/50" : "text-slate-400")}>{item.description}</p>
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

   <div className={cn("relative z-10 space-y-3 border-t p-4", isGlass ? "border-white/10" : "border-slate-200/80")}>
    <button
     type="button"
     onClick={() => navigate('/chat')}
     className={cn(
      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium shadow-lg transition-all focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2",
      isGlass ? "bg-white/10 text-white hover:bg-white/15" : "bg-zinc-900 text-white hover:bg-zinc-800 hover:shadow-button"
     )}
    >
     <MessageCircle size={18} />
     进入对话
    </button>

    <div className={cn(
     "flex items-center gap-3 rounded-lg p-2.5 shadow-sm transition-all hover:shadow-md",
     isGlass ? "border border-white/10 bg-white/5" : "border border-[var(--admin-card-border)] bg-[var(--admin-card-bg)]"
    )}>
     <div className={cn(
      "flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl shadow-sm",
      isGlass ? "border border-white/20 bg-white/10 text-white" : "border border-zinc-200 bg-[linear-gradient(135deg,rgba(15,23,42,0.06),rgba(255,255,255,0.9))] text-zinc-600"
     )}>
      <UserAvatarIcon size={20} />
     </div>
     <div className="min-w-0 flex-1">
      <p className={cn("truncate text-xs font-medium", isGlass ? "text-white" : "text-slate-800")}>{user?.name || 'AgenticOS User'}</p>
      <p className={cn("truncate text-[10px] font-medium", isGlass ? "text-white/60" : "text-slate-400")}>{user?.email || 'signed in'}</p>
     </div>
     <button
      type="button"
      onClick={handleLogout}
      className={cn(
       "rounded-xl p-2 transition-all hover:scale-110 active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2",
       isGlass ? "text-white/70 hover:bg-rose-500/20 hover:text-rose-400" : "text-slate-400 hover:bg-rose-50 hover:text-rose-500"
      )}
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
