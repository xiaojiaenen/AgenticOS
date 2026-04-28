import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Session } from '../../types';
import { cn } from '../../lib/utils';
import { Logo } from '../Logo';
import { PlusIcon, ChatBubbleIcon, TrashIcon, MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { getStoredUser, logout } from '../../services/authService';

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
  onClose: () => void;
  isMobile: boolean;
  onLoadMore?: () => void;
  hasMore?: boolean;
}

export const Sidebar = React.memo(({
  sessions,
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClose,
  isMobile,
  onLoadMore,
  hasMore = false
}: SidebarProps) => {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const user = getStoredUser();

  const handleScroll = React.useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50 && hasMore && onLoadMore) {
      onLoadMore();
    }
  }, [hasMore, onLoadMore]);

  return (
    <motion.aside
      initial={isMobile ? { x: -300 } : { width: 280 }}
      animate={{ x: 0, width: 280 }}
      exit={isMobile ? { x: -300 } : { width: 0 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className={cn(
        "bg-white/60 backdrop-blur-2xl border-r border-white/40 flex flex-col z-20 flex-shrink-0 overflow-hidden shadow-[4px_0_24px_rgba(0,0,0,0.03)]",
        isMobile ? "fixed inset-y-0 left-0 shadow-2xl w-[280px]" : "h-full"
      )}
    >
      <div className="p-4 flex items-center justify-between border-b border-slate-100">
        <Logo iconSize={20} className="text-lg" />
        <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-lg group transition-colors">
          <MenuIcon size={20} />
        </button>
      </div>

      <div className="p-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-900 text-white rounded-xl hover:bg-zinc-800 transition-colors shadow-sm font-medium group"
        >
          <PlusIcon size={18} className="group-hover:rotate-90" /> 新的对话
        </button>
      </div>

      <div 
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 py-2 space-y-1 custom-scrollbar"
      >
        {sessions.map(session => (
          <div
            key={session.id}
            onClick={() => onSelectSession(session.id)}
            className={cn(
              "group flex items-center justify-between px-3 py-3 rounded-xl cursor-pointer transition-all",
              currentSessionId === session.id
                ? "bg-white/70 backdrop-blur-sm text-zinc-900 font-bold shadow-[0_2px_10px_rgba(0,0,0,0.05)] border border-white/60"
                : "text-slate-600 hover:bg-white/40 hover:text-slate-900 font-medium"
            )}
          >
            <div className="flex items-center gap-3 overflow-hidden">
              <ChatBubbleIcon size={16} active={currentSessionId === session.id} className={currentSessionId === session.id ? "text-zinc-800" : "text-slate-400"} />
              <span className="truncate text-sm">{session.title}</span>
            </div>
            <button
              onClick={(e) => onDeleteSession(session.id, e)}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-all"
            >
              <TrashIcon size={16} />
            </button>
          </div>
        ))}
        {hasMore && (
          <div className="px-2 py-3">
            <button
              type="button"
              onClick={onLoadMore}
              className="w-full rounded-xl border border-white/70 bg-white/55 px-3 py-2 text-xs font-bold text-slate-500 shadow-sm transition-all hover:bg-white/80 hover:text-slate-800"
            >
              加载更多对话
            </button>
          </div>
        )}
        {sessions.length === 0 && (
          <div className="text-center text-slate-400 text-sm mt-10">
            暂无历史对话
          </div>
        )}
      </div>

      {/* User Profile & Logout at bottom */}
      <div className="p-4 border-t border-slate-100 flex flex-col gap-2">
        {user?.role === 'admin' && (
          <button 
            onClick={() => navigate('/admin')}
            className="w-full flex items-center gap-3 px-3 py-2.5 bg-zinc-900 text-white rounded-xl hover:bg-zinc-800 transition-colors shadow-sm font-bold text-sm"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            管理后台 (Admin)
          </button>
        )}
        <div className="flex items-center gap-3 p-2 rounded-xl hover:bg-slate-50 transition-colors">
          <div className="w-9 h-9 rounded-xl bg-zinc-100 flex items-center justify-center text-zinc-600 border border-zinc-200 shadow-sm overflow-hidden flex-shrink-0">
            <UserAvatarIcon size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-slate-800 truncate">
              {user?.name || 'AgenticOS User'}
            </p>
            <p className="text-[10px] text-slate-400 font-medium truncate">
              {user?.email || 'signed in'}
            </p>
          </div>
          <button 
            onClick={async () => {
              await logout();
              navigate('/login');
            }}
            className="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors"
            title="退出登录"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </div>
    </motion.aside>
  );
});
