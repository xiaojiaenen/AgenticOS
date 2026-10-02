import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';

import { Session } from '../../types';
import { cn } from '../../lib/utils';
import { Logo } from '../Logo';
import { PlusIcon, ChatBubbleIcon, TrashIcon, MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { getStoredUser, logout } from '../../services/authService';
import { IntegrationMarket } from './IntegrationMarket';
import { EmailSettingsPanel } from './EmailSettingsPanel';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../shadcn/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';
import { Button } from '../shadcn/button';
import { ThemeToggle } from '../ui/ThemeToggle';
interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e?: React.MouseEvent) => void;
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
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; title: string } | null>(null);
  const [showMarket, setShowMarket] = useState(false);
  const [showEmailSettings, setShowEmailSettings] = useState(false);  const handleScroll = React.useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50 && hasMore && onLoadMore) {
      onLoadMore();
    }
  }, [hasMore, onLoadMore]);

  // ── 侧边栏内容（两种主题共用） ──
  const sidebarContent = (
    <>
      <div className={cn("p-4 flex items-center justify-between border-b", "border-[var(--border-subtle)]")}>
        <Logo iconSize={20} className="text-lg" />
        <button onClick={onClose} className={cn("p-2 rounded-lg group transition-colors", "text-[var(--muted-foreground)] hover:text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]")} aria-label="关闭侧边栏">
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
        {sessions.map((session, index) => {
          const isActive = currentSessionId === session.id;
          // 层级递变：越靠下（越久远）的会话图标越小、越淡，形成视觉纵深
          const depth = Math.min(index, 6);
          const iconSize = 16 - depth;
          const iconOpacity = Math.max(0.45, 1 - depth * 0.09);
          const sessionInner = (
            <>
              <div className="flex items-center gap-3 overflow-hidden">
                <ChatBubbleIcon
                  size={iconSize}
                  active={isActive}
                  className={cn(
                    "shrink-0 transition-all duration-300",
                    isActive ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)]",
                  )}
                  style={isActive ? undefined : { opacity: iconOpacity }}
                />
                <span className="truncate text-sm">{session.title}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteConfirm({ id: session.id, title: session.title });
                }}
                /* 触屏（hover: none）无法 hover，删除按钮常驻可见；
                   指针设备仍保持 hover 出现，避免列表视觉过噪 */
                className="p-1.5 rounded-md transition-all text-[var(--muted-foreground)] hover:text-red-500 hover:bg-red-50 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100"
                aria-label="删除对话"
              >
                <TrashIcon size={16} />
              </button>
            </>
          );



          return (
            <div
              key={session.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectSession(session.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectSession(session.id); } }}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                "group flex items-center justify-between px-3 py-3 rounded-xl cursor-pointer transition-all",
                isActive
                  ? "bg-[var(--surface-1)] backdrop-blur-sm text-[var(--foreground)] font-bold shadow-xs border border-white/60"
                  : "text-[var(--muted-foreground)] hover:bg-white/40 hover:text-[var(--foreground)] font-medium"
              )}
            >
              {sessionInner}
            </div>
          );
        })}
        {hasMore && (
          <div className="px-2 py-3">
            <button
              type="button"
              onClick={onLoadMore}
              className="w-full rounded-xl border border-white/70 bg-white/55 px-3 py-2 text-xs font-bold text-[var(--muted-foreground)] shadow-sm transition-all hover:bg-[var(--surface-1)] hover:text-[var(--foreground)]"
              aria-label="加载更多对话"
            >
              加载更多对话
            </button>
          </div>
        )}
        {sessions.length === 0 && (
          <div className="text-center text-[var(--muted-foreground)] text-sm mt-10">
            暂无历史对话
          </div>
        )}
      </div>

      {/* User Profile & Logout at bottom */}
      <div className={cn("p-4 border-t flex flex-col gap-2", "border-[var(--border-subtle)]")}>
        {/* 次级入口收进一行图标，减少侧栏纵向占用（悬浮显示名称） */}
        <div className="flex items-center gap-1.5" role="group" aria-label="快捷入口">
          {[
            {
              key: 'store',
              label: '智能体商店',
              onClick: () => navigate('/agents'),
              icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>,
            },
            {
              key: 'market',
              label: '集成市场',
              onClick: () => setShowMarket(true),
              icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4M12 16h.01"/></svg>,
            },
            {
              key: 'email',
              label: '邮箱设置',
              onClick: () => setShowEmailSettings(true),
              icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>,
            },
          ].map(({ key, label, onClick, icon }) => (
            <Tooltip key={key}>
              <TooltipTrigger asChild>
                <button
                  onClick={onClick}
                  aria-label={label}
                  className={cn(
                    "flex-1 h-9 flex items-center justify-center rounded-xl transition-all duration-200",
                    "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] hover:-translate-y-px active:scale-95"
                  )}
                >
                  {icon}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={8}>{label}</TooltipContent>
            </Tooltip>
          ))}
        </div>
        {user?.role === 'admin' && (
          <button
            onClick={() => navigate('/admin')}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl bg-zinc-900 text-white hover:bg-zinc-800 transition-colors shadow-sm font-bold text-sm"
            aria-label="管理后台"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            管理后台 (Admin)
          </button>
        )}
        <div className={cn("flex items-center gap-3 p-2 rounded-xl transition-colors", "hover:bg-[var(--surface-2)]")}>
          <div className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center shadow-sm overflow-hidden flex-shrink-0",
            "bg-[var(--surface-2)] text-zinc-600 border border-[var(--border-subtle)]"
          )}>
            <UserAvatarIcon size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <p className={cn("text-xs font-bold truncate", "text-[var(--foreground)]")}>
              {user?.name || 'AgenticOS User'}
            </p>
            <p className={cn("text-[10px] font-medium truncate", "text-[var(--muted-foreground)]")}>
              {user?.email || 'signed in'}
            </p>
          </div>
          {/* 主题切换 */}
          <ThemeToggle variant="icon" className={cn(
            "",
            "text-[var(--muted-foreground)] hover:text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]"
          )} />
          <button
            onClick={async () => {
              await logout();
              navigate('/login');
            }}
            className={cn(
              "p-2 rounded-lg transition-colors",
              "text-[var(--muted-foreground)] hover:text-rose-500 hover:bg-rose-50"
            )}
            title="退出登录"
            aria-label="退出登录"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </div>
    </>
  );

  return (
    <>
    <TooltipProvider delayDuration={250} skipDelayDuration={400}>
    <motion.aside
      initial={isMobile ? { x: -300 } : { x: 0, width: 280 }}
      animate={{ x: 0, width: 280 }}
      exit={isMobile ? { x: -300 } : { width: 0 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className={cn(
        "flex flex-col z-20 flex-shrink-0 overflow-hidden",
        "bg-[var(--surface-1)] backdrop-blur-2xl border-r border-white/40 shadow-sm",
        isMobile ? "fixed inset-y-0 left-0 shadow-2xl w-[280px]" : "h-full"
      )}
    >
      {sidebarContent}
    </motion.aside>
    <IntegrationMarket open={showMarket} onClose={() => setShowMarket(false)} />
    <EmailSettingsPanel open={showEmailSettings} onClose={() => setShowEmailSettings(false)} />
    {/* Delete Confirmation Dialog */}
    <Dialog open={!!deleteConfirm} onOpenChange={(open) => { if (!open) setDeleteConfirm(null); }}>
      <DialogContent className="max-w-sm" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>删除对话</DialogTitle>
          <DialogDescription>
            确定要删除对话「{deleteConfirm?.title || '新对话'}」吗？此操作不可撤销。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => setDeleteConfirm(null)}>取消</Button>
          <Button
            variant="destructive"
            onClick={() => {
              if (deleteConfirm) {
                onDeleteSession(deleteConfirm.id);
                setDeleteConfirm(null);
              }
            }}
          >
            删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </TooltipProvider>
    </>
  );
});
