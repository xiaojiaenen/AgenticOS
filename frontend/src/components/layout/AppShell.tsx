import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { toast } from 'sonner';
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Compass,
  LayoutGrid,
  Loader2,
  Menu,
  MessageCircleHeart,
  MessageSquare,
  MessageSquareText,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Logo } from '../Logo';
import { ThemeToggle } from '../ui/ThemeToggle';
import { cn } from '../../lib/utils';
import { canEnterAdmin, getStoredUser } from '@/services/authTokenStore';
import { useChatStore } from '../../stores/chatStore';
import { listSessions, deleteSession as deleteSessionApi } from '../../services/agentService';
import { convertBackendSession } from '../../lib/sessionMerge';
import type { Session } from '../../types';

type SidebarPanel = 'nav' | 'chats';

interface NavItem {
  key: string;
  label: string;
  path: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  match: (pathname: string) => boolean;
}

const PRIMARY_NAV: NavItem[] = [
  {
    key: 'home',
    label: '创作首页',
    path: '/',
    icon: Sparkles,
    match: (p) => p === '/',
  },
  {
    key: 'chat',
    label: '对话工作台',
    path: '/chat',
    icon: MessageSquareText,
    match: (p) => p.startsWith('/chat'),
  },
  {
    key: 'agents',
    label: 'AI 智能体',
    path: '/agents',
    icon: Bot,
    match: (p) => p.startsWith('/agents'),
  },
  {
    key: 'canvas',
    label: '创作画布',
    path: '/canvas',
    icon: Palette,
    match: (p) => p.startsWith('/canvas'),
  },
  {
    key: 'gallery',
    label: '作品库',
    path: '/gallery',
    icon: LayoutGrid,
    match: (p) => p.startsWith('/gallery'),
  },
  {
    key: 'feedback',
    label: '反馈建议',
    path: '/feedback',
    icon: MessageCircleHeart,
    match: (p) => p.startsWith('/feedback'),
  },
];

/**
 * 全站统一持久化工作台外壳（Persistent AppShell）：
 * - 单一左侧悬浮毛玻璃导航栏跨页常驻不重载，彻底消除页面割裂感
 * - 侧栏内部支持平滑横向滑动切换「主导航」⇄「对话列表」（支持点击顶部胶囊或左右滑动手势）
 * - 进入 `/chat` 自动滑至对话列表；在首页/智能体/作品库等任意页面也可随时滑出对话列表直达历史会话
 */
export const AppShell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [user] = useState(() => getStoredUser());
  const showAdmin = canEnterAdmin();

  // Global chat store sync
  const storeSessions = useChatStore((s) => s.sessions);
  const setStoreSessions = useChatStore((s) => s.setSessions);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const setCurrentSessionId = useChatStore((s) => s.setCurrentSessionId);

  const isDenseSecondarySidebar =
    location.pathname.startsWith('/admin') || location.pathname.startsWith('/canvas');

  const [manualCollapsed, setManualCollapsed] = useState<boolean>(false);
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [activePanel, setActivePanel] = useState<SidebarPanel>(() =>
    location.pathname.startsWith('/chat') ? 'chats' : 'nav',
  );
  const [chatSearch, setChatSearch] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Horizontal swipe gesture tracking inside sidebar
  const swipeStartRef = useRef<{ x: number; y: number } | null>(null);

  // Auto-slide sidebar panel based on route
  useEffect(() => {
    setMobileOpen(false);
    if (location.pathname.startsWith('/chat')) {
      setActivePanel('chats');
    } else {
      setActivePanel('nav');
    }
  }, [location.pathname]);

  // Fetch recent sessions when logged in and switching to chats panel (if store is empty)
  const fetchRecentSessions = useCallback(async () => {
    if (!user) return;
    setLoadingSessions(true);
    try {
      const items = await listSessions();
      if (Array.isArray(items) && items.length > 0) {
        setStoreSessions((prev) => {
          const existingById = new Map(prev.map((s) => [s.id, s]));
          // 用项目统一的后端→前端转换（字段是 session_id / metadata.response_mode，
          // 老代码里的 item.id / item.mode 是过期字段，会 TS 报错且 mode 丢失）。
          const mapped: Session[] = items.map((item) => {
            const converted = convertBackendSession(item);
            const existing = existingById.get(converted.id);
            return existing ? { ...converted, messages: existing.messages } : converted;
          });
          return mapped;
        });
      }
    } catch {
      // Quietly ignore if offline or unauthenticated
    } finally {
      setLoadingSessions(false);
    }
  }, [user, setStoreSessions]);

  useEffect(() => {
    if (activePanel === 'chats' && user && storeSessions.length === 0) {
      void fetchRecentSessions();
    }
  }, [activePanel, user, storeSessions.length, fetchRecentSessions]);

  const collapsed = isDenseSecondarySidebar ? true : manualCollapsed;

  const navItems: NavItem[] = useMemo(
    () =>
      showAdmin
        ? [
            ...PRIMARY_NAV,
            {
              key: 'admin',
              label: '企业后台',
              path: '/admin',
              icon: ShieldCheck,
              match: (p) => p.startsWith('/admin'),
            },
          ]
        : PRIMARY_NAV,
    [showAdmin],
  );

  const filteredSessions = useMemo(() => {
    const q = chatSearch.trim().toLowerCase();
    if (!q) return storeSessions;
    return storeSessions.filter((s) => (s.title || '新对话').toLowerCase().includes(q));
  }, [storeSessions, chatSearch]);

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setActivePanel('chats');
    setMobileOpen(false);
    if (!location.pathname.startsWith('/chat')) {
      navigate('/chat');
    }
  };

  const handleSelectSession = (id: string) => {
    setCurrentSessionId(id);
    setMobileOpen(false);
    if (!location.pathname.startsWith('/chat')) {
      navigate('/chat');
    }
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteSessionApi(id);
    } catch {
      // Remove locally even if backend session was purely local
    }
    setStoreSessions((prev) => prev.filter((s) => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
    }
    toast.success('已删除对话');
  };

  const onSidebarPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('input, textarea')) return;
    swipeStartRef.current = { x: e.clientX, y: e.clientY };
  };

  const onSidebarPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!swipeStartRef.current) return;
    const dx = e.clientX - swipeStartRef.current.x;
    const dy = e.clientY - swipeStartRef.current.y;
    swipeStartRef.current = null;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.4) {
      if (dx < 0) setActivePanel('chats');
      else setActivePanel('nav');
    }
  };

  const renderSlidingSidebarBody = (compact: boolean) => {
    if (compact) {
      return (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.match(location.pathname);
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  if (item.path === '/chat') {
                    setManualCollapsed(false);
                    setActivePanel('chats');
                  }
                  navigate(item.path);
                }}
                title={item.label}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex w-full items-center justify-center rounded-xl py-2.5 transition-all cursor-pointer',
                  active
                    ? 'bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm'
                    : 'text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]',
                )}
              >
                <Icon size={17} />
              </button>
            );
          })}
        </div>
      );
    }

    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {/* 顶部滑动切换胶囊：主导航 ⇄ 对话列表 */}
        <div className="relative mb-3 grid grid-cols-2 rounded-xl bg-[var(--surface-2)]/85 p-1 ring-1 ring-[var(--border-subtle)]">
          {(
            [
              ['nav', '导航', Compass],
              ['chats', '对话', MessageSquare],
            ] as [SidebarPanel, string, React.ComponentType<{ size?: number; className?: string }>][]
          ).map(([key, label, Icon]) => {
            const isActive = activePanel === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActivePanel(key)}
                className={cn(
                  'relative z-10 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition-colors cursor-pointer',
                  isActive
                    ? 'text-[var(--foreground)]'
                    : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                )}
              >
                {isActive && (
                  <motion.span
                    layoutId="aos-sidebar-panel-pill"
                    transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                    className="absolute inset-0 -z-10 rounded-lg bg-[var(--surface-1)] shadow-sm"
                  />
                )}
                <Icon size={13} />
                <span>{label}</span>
              </button>
            );
          })}
        </div>

        {/* 横向滑动轨道（200% 宽度，左半为主导航，右半为对话列表） */}
        <div
          onPointerDown={onSidebarPointerDown}
          onPointerUp={onSidebarPointerUp}
          className="relative min-h-0 flex-1 overflow-hidden"
        >
          <motion.div
            animate={{ x: activePanel === 'nav' ? '0%' : '-50%' }}
            transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
            className="flex h-full w-[200%]"
          >
            {/* 面板 1：主导航 */}
            <div className="flex h-full w-1/2 shrink-0 flex-col justify-between pr-1">
              <nav className="flex flex-col gap-1 overflow-y-auto" aria-label="主导航">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = item.match(location.pathname);
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => {
                        if (item.path === '/chat') {
                          setActivePanel('chats');
                        }
                        navigate(item.path);
                      }}
                      aria-current={active ? 'page' : undefined}
                      className={cn(
                        'flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-[13.5px] font-medium transition-all cursor-pointer',
                        active
                          ? 'bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm'
                          : 'text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]',
                      )}
                    >
                      <span className="flex items-center gap-2.5 truncate">
                        <Icon size={17} className="shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </span>
                      {item.path === '/chat' && (
                        <ChevronRight size={14} className="shrink-0 opacity-65" />
                      )}
                    </button>
                  );
                })}
              </nav>

              <button
                type="button"
                onClick={() => setActivePanel('chats')}
                className="mt-2 flex items-center justify-between rounded-xl border border-dashed border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:border-[var(--primary)]/40 hover:text-[var(--foreground)] cursor-pointer"
              >
                <span className="flex items-center gap-1.5">
                  <MessageSquare size={13} />
                  左滑或点击看历史对话
                </span>
                <ChevronRight size={13} />
              </button>
            </div>

            {/* 面板 2：对话列表 */}
            <div className="flex h-full w-1/2 shrink-0 flex-col pl-1">
              <div className="mb-2 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setActivePanel('nav')}
                  title="滑回主导航"
                  className="flex h-9 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/75 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--secondary)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-xl bg-[var(--primary)] px-3 text-xs font-semibold text-[var(--primary-foreground)] shadow-sm transition-all hover:opacity-90 active:scale-[0.98] cursor-pointer"
                >
                  <Plus size={14} />
                  新建对话
                </button>
              </div>

              {/* 搜索会话 */}
              <div className="relative mb-2.5">
                <Search
                  size={13}
                  className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
                />
                <input
                  type="search"
                  value={chatSearch}
                  onChange={(e) => setChatSearch(e.target.value)}
                  placeholder="搜索历史对话..."
                  aria-label="搜索历史对话"
                  className="h-8 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/75 pl-8 pr-2.5 text-xs text-[var(--foreground)] outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)]"
                />
              </div>

              {/* 会话列表 */}
              <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-0.5">
                {!user ? (
                  <div className="flex flex-1 flex-col items-center justify-center gap-2 px-3 text-center">
                    <p className="text-xs text-[var(--muted-foreground)]">登录后可同步与查看历史对话</p>
                    <button
                      type="button"
                      onClick={() => navigate('/login')}
                      className="rounded-xl bg-[var(--primary)]/12 px-3 py-1.5 text-xs font-semibold text-[var(--primary)] hover:bg-[var(--primary)]/20 cursor-pointer"
                    >
                      立即登录
                    </button>
                  </div>
                ) : loadingSessions && filteredSessions.length === 0 ? (
                  <div className="flex items-center justify-center gap-2 py-8 text-xs text-[var(--muted-foreground)]">
                    <Loader2 size={14} className="animate-spin" />
                    加载对话中...
                  </div>
                ) : filteredSessions.length === 0 ? (
                  <div className="flex flex-1 flex-col items-center justify-center gap-1.5 px-3 py-8 text-center">
                    <MessageSquare size={18} className="text-[var(--muted-foreground)]/60" />
                    <p className="text-xs text-[var(--muted-foreground)]">
                      {chatSearch ? '没有匹配的对话' : '还没有历史对话'}
                    </p>
                  </div>
                ) : (
                  filteredSessions.map((session) => {
                    const isCurrent =
                      location.pathname.startsWith('/chat') && currentSessionId === session.id;
                    return (
                      <div
                        key={session.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => handleSelectSession(session.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleSelectSession(session.id);
                          }
                        }}
                        className={cn(
                          'group flex items-center justify-between gap-2 rounded-xl px-2.5 py-2 text-left text-xs transition-all cursor-pointer',
                          isCurrent
                            ? 'bg-[var(--primary)]/12 font-semibold text-[var(--primary)] ring-1 ring-[var(--primary)]/25'
                            : 'text-[var(--foreground)]/85 hover:bg-[var(--secondary)]',
                        )}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-2">
                          <MessageSquare size={13} className="shrink-0 opacity-65" />
                          <span className="truncate">{session.title || '新对话'}</span>
                        </span>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSession(session.id, e)}
                          title="删除对话"
                          aria-label="删除对话"
                          className="shrink-0 rounded-lg p-1 text-[var(--muted-foreground)] opacity-0 transition-opacity hover:bg-rose-500/15 hover:text-rose-500 group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    );
  };

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)] font-sans">
      {/* 全站共享弥散光晕与点阵背景 */}
      <div className="aos-ambient-bg" aria-hidden="true" />
      <div className="aos-ambient-dots" aria-hidden="true" />

      {/* 移动端抽屉触发按钮 */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="打开导航"
        className="aos-glass-surface fixed left-3 top-3 z-40 flex h-9 w-9 items-center justify-center rounded-xl text-[var(--foreground)] lg:hidden"
      >
        <Menu size={17} />
      </button>

      {/* 移动端抽屉 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/35 backdrop-blur-xs"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="aos-glass-rail relative z-10 m-3 flex w-[248px] flex-col justify-between rounded-3xl p-3">
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="flex items-center justify-between px-1.5 pt-1">
                <button
                  type="button"
                  onClick={() => navigate('/')}
                  className="bg-transparent border-0 p-0 cursor-pointer"
                >
                  <Logo iconSize={26} showText />
                </button>
                <button
                  type="button"
                  onClick={() => setMobileOpen(false)}
                  aria-label="关闭导航"
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
                >
                  <X size={16} />
                </button>
              </div>
              {renderSlidingSidebarBody(false)}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 border-t border-[var(--border)] px-1 pt-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-[var(--foreground)]">
                  {user?.name || '访客模式'}
                </div>
                <div className="truncate text-[11px] text-[var(--muted-foreground)]">
                  {user?.email || '未登录'}
                </div>
              </div>
              <ThemeToggle />
            </div>
          </aside>
        </div>
      )}

      {/* 桌面端唯一持久化左侧悬浮毛玻璃侧栏（支持主导航 ⇄ 对话列表平滑滑动切换） */}
      <aside
        className={cn(
          'aos-glass-rail relative z-30 m-3 mr-0 hidden shrink-0 flex-col justify-between rounded-3xl p-3 transition-[width] duration-300 ease-out lg:flex',
          collapsed ? 'w-[68px]' : 'w-[244px]',
        )}
      >
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className={cn('flex items-center px-1 pt-1', collapsed ? 'justify-center' : 'justify-between')}>
            <button
              type="button"
              onClick={() => {
                setActivePanel('nav');
                navigate('/');
              }}
              className="bg-transparent border-0 p-0 cursor-pointer"
              aria-label="返回创作首页"
            >
              <Logo iconSize={26} showText={!collapsed} />
            </button>
            {!collapsed && !isDenseSecondarySidebar && (
              <button
                type="button"
                onClick={() => setManualCollapsed(true)}
                aria-label="收起侧栏"
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted-foreground)] transition-colors hover:bg-[var(--secondary)] hover:text-[var(--foreground)] cursor-pointer"
              >
                <PanelLeftClose size={16} />
              </button>
            )}
          </div>

          {renderSlidingSidebarBody(collapsed)}
        </div>

        <div className="mt-2 flex flex-col gap-2 border-t border-[var(--border)] pt-3">
          {collapsed && !isDenseSecondarySidebar && (
            <button
              type="button"
              onClick={() => setManualCollapsed(false)}
              aria-label="展开侧栏"
              className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl text-[var(--muted-foreground)] transition-colors hover:bg-[var(--secondary)] hover:text-[var(--foreground)] cursor-pointer"
            >
              <PanelLeftOpen size={16} />
            </button>
          )}
          <div className={cn('flex items-center gap-2 px-1', collapsed ? 'justify-center' : 'justify-between')}>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-[var(--foreground)]">
                  {user?.name || '访客模式'}
                </div>
                <div className="truncate text-[11px] text-[var(--muted-foreground)]">
                  {user?.email || '登录同步个人会话'}
                </div>
              </div>
            )}
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* 右侧主内容工作区 */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
};
