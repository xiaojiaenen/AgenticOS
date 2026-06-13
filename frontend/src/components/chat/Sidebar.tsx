import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { LiquidGlass, glassPresets, radii } from '@xiaojiaenen/liquid-glass';

// 圆角值，与浅色模式 rounded-xl 一致
const glassRadius = 12;
import { Session } from '../../types';
import { cn } from '../../lib/utils';
import { Logo } from '../Logo';
import { PlusIcon, ChatBubbleIcon, TrashIcon, MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { getStoredUser, logout } from '../../services/authService';
import { IntegrationMarket } from './IntegrationMarket';
import { EmailSettingsPanel } from './EmailSettingsPanel';
import { Modal, ModalHeader, ModalFooter } from '../ui/Modal';
import { ThemeToggle } from '../ui/ThemeToggle';
import { useIsGlassTheme } from '../liquid-glass';

// 会话项组件（液态玻璃主题下，鼠标悬停时显示玻璃效果）
const SessionItemGlass: React.FC<{
  isActive: boolean;
  onClick: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  children: React.ReactNode;
}> = ({ isActive, onClick, onKeyDown, children }) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={onKeyDown}
      aria-current={isActive ? 'page' : undefined}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="group flex items-center justify-between px-3 py-3 rounded-xl cursor-pointer transition-all duration-200 ease-out"
      style={{
        background: isHovered || isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
        backdropFilter: isHovered || isActive ? 'blur(20px)' : 'none',
        WebkitBackdropFilter: isHovered || isActive ? 'blur(20px)' : 'none',
        border: isHovered || isActive ? '1px solid rgba(255,255,255,0.1)' : '1px solid transparent',
        color: isHovered || isActive ? '#ffffff' : 'rgba(255,255,255,0.6)',
        fontWeight: isActive ? 700 : 500,
      }}
    >
      {children}
    </div>
  );
};

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
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; title: string } | null>(null);
  const [showMarket, setShowMarket] = useState(false);
  const [showEmailSettings, setShowEmailSettings] = useState(false);
  const isGlass = useIsGlassTheme();

  const handleScroll = React.useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50 && hasMore && onLoadMore) {
      onLoadMore();
    }
  }, [hasMore, onLoadMore]);

  // ── 侧边栏内容（两种主题共用） ──
  const sidebarContent = (
    <>
      <div className={cn("p-4 flex items-center justify-between border-b", isGlass ? "border-white/10" : "border-slate-100")}>
        <Logo iconSize={20} className="text-lg" />
        <button onClick={onClose} className={cn("p-2 rounded-lg group transition-colors", isGlass ? "text-slate-500 hover:text-slate-700 hover:bg-white/50" : "text-slate-400 hover:text-slate-600 hover:bg-slate-50")} aria-label="关闭侧边栏">
          <MenuIcon size={20} />
        </button>
      </div>

      <div className="p-4">
        {isGlass ? (
          <LiquidGlass
            as="button"
            {...glassPresets.control}
            tint="rgba(255,255,255,0.08)"
            radius={glassRadius}
            onClick={onNewChat}
            className="rounded-xl"
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', cursor: 'pointer' }}
          >
            <PlusIcon size={18} className="group-hover:rotate-90" /> 新的对话
          </LiquidGlass>
        ) : (
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-900 text-white rounded-xl hover:bg-zinc-800 transition-colors shadow-sm font-medium group"
          >
            <PlusIcon size={18} className="group-hover:rotate-90" /> 新的对话
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 py-2 space-y-1 custom-scrollbar"
      >
        {sessions.map(session => {
          const isActive = currentSessionId === session.id;
          const sessionInner = (
            <>
              <div className="flex items-center gap-3 overflow-hidden">
                <ChatBubbleIcon size={16} active={isActive} className={isActive ? "text-zinc-800" : "text-slate-400"} />
                <span className="truncate text-sm">{session.title}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteConfirm({ id: session.id, title: session.title });
                }}
                className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1.5 rounded-md transition-all text-slate-400 hover:text-red-500 hover:bg-red-50"
                aria-label="删除对话"
              >
                <TrashIcon size={16} />
              </button>
            </>
          );

          if (isGlass) {
            return (
              <SessionItemGlass
                key={session.id}
                isActive={isActive}
                onClick={() => onSelectSession(session.id)}
                onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectSession(session.id); } }}
              >
                {sessionInner}
              </SessionItemGlass>
            );
          }

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
                  ? "bg-white/70 backdrop-blur-sm text-zinc-900 font-bold shadow-xs border border-white/60"
                  : "text-slate-600 hover:bg-white/40 hover:text-slate-900 font-medium"
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
              className={cn(
                "w-full rounded-xl border px-3 py-2 text-xs font-bold shadow-sm transition-all",
                isGlass
                  ? "border-white/15 bg-white/8 text-slate-500 hover:bg-white/12 hover:text-slate-800"
                  : "border-white/70 bg-white/55 text-slate-500 hover:bg-white/80 hover:text-slate-800"
              )}
              aria-label="加载更多对话"
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
      <div className={cn("p-4 border-t flex flex-col gap-2", isGlass ? "border-white/10" : "border-slate-100")}>
        <button
          onClick={() => navigate('/agents')}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors font-bold text-sm",
            isGlass ? "text-gray-300 hover:bg-white/10 hover:text-white" : "text-slate-700 hover:bg-slate-50"
          )}
          aria-label="智能体商店"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          智能体商店
        </button>
        <button
          onClick={() => setShowMarket(true)}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors font-bold text-sm",
            isGlass ? "text-gray-300 hover:bg-white/10 hover:text-white" : "text-slate-700 hover:bg-sky-50/60"
          )}
          aria-label="集成市场"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4M12 16h.01"/></svg>
          集成市场
        </button>
        <button
          onClick={() => setShowEmailSettings(true)}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors font-bold text-sm",
            isGlass ? "text-gray-300 hover:bg-white/10 hover:text-white" : "text-slate-700 hover:bg-sky-50/60"
          )}
          aria-label="邮箱设置"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
          邮箱设置
        </button>
        {user?.role === 'admin' && (
          <button
            onClick={() => navigate('/admin')}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors shadow-sm font-bold text-sm",
              isGlass
                ? "bg-white/10 text-white hover:bg-white/15 border border-white/15 backdrop-blur-sm"
                : "bg-zinc-900 text-white hover:bg-zinc-800"
            )}
            aria-label="管理后台"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            管理后台 (Admin)
          </button>
        )}
        <div className={cn("flex items-center gap-3 p-2 rounded-xl transition-colors", isGlass ? "hover:bg-white/10" : "hover:bg-slate-50")}>
          <div className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center shadow-sm overflow-hidden flex-shrink-0",
            isGlass ? "bg-white/10 text-gray-300 border border-white/15" : "bg-zinc-100 text-zinc-600 border border-zinc-200"
          )}>
            <UserAvatarIcon size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <p className={cn("text-xs font-bold truncate", isGlass ? "text-white" : "text-slate-800")}>
              {user?.name || 'AgenticOS User'}
            </p>
            <p className={cn("text-[10px] font-medium truncate", isGlass ? "text-gray-400" : "text-slate-400")}>
              {user?.email || 'signed in'}
            </p>
          </div>
          {/* 主题切换 */}
          <ThemeToggle variant="icon" className={cn(
            "",
            isGlass ? "text-gray-400 hover:text-white hover:bg-white/10" : "text-slate-400 hover:text-slate-600 hover:bg-slate-50"
          )} />
          <button
            onClick={async () => {
              await logout();
              navigate('/login');
            }}
            className={cn(
              "p-2 rounded-lg transition-colors",
              isGlass ? "text-gray-400 hover:text-rose-500 hover:bg-rose-50" : "text-slate-400 hover:text-rose-500 hover:bg-rose-50"
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
    <motion.aside
      initial={isMobile ? { x: -300 } : { width: 280 }}
      animate={{ x: 0, width: 280 }}
      exit={isMobile ? { x: -300 } : { width: 0 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className={cn(
        "flex flex-col z-20 flex-shrink-0 overflow-hidden",
        isGlass
          ? "border-r border-white/10"
          : "bg-white/60 backdrop-blur-2xl border-r border-white/40 shadow-sm",
        isMobile ? "fixed inset-y-0 left-0 shadow-2xl w-[280px]" : "h-full"
      )}
    >
      {isGlass ? (
        <LiquidGlass
          {...glassPresets.card}
          tint="rgba(255,255,255,0.06)"
          radius={0}
          style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}
        >
          {sidebarContent}
        </LiquidGlass>
      ) : sidebarContent}
    </motion.aside>
    <IntegrationMarket open={showMarket} onClose={() => setShowMarket(false)} />
    <EmailSettingsPanel open={showEmailSettings} onClose={() => setShowEmailSettings(false)} />
    {/* Delete Confirmation Modal */}
    <Modal open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} maxWidth="max-w-sm">
      <ModalHeader title="删除对话" subtitle="确认删除" onClose={() => setDeleteConfirm(null)} />
      <p className="text-sm text-slate-600 mb-4">
        确定要删除对话「{deleteConfirm?.title || '新对话'}」吗？此操作不可撤销。
      </p>
      <ModalFooter
        onCancel={() => setDeleteConfirm(null)}
        submitLabel="删除"
        onSubmit={() => {
          if (deleteConfirm) {
            onDeleteSession(deleteConfirm.id, {} as React.MouseEvent);
            setDeleteConfirm(null);
          }
        }}
      />
    </Modal>
    </>
  );
});
