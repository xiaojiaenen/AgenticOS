import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { toast } from 'sonner';
import {
  BarChart2,
  Bot,
  ChevronLeft,
  ChevronRight,
  GitBranch,
  Globe,
  Loader2,
  Mail,
  Menu,
  MessageSquare,
  MessageSquareText,
  Palette,
  PanelLeftOpen,
  Plug,
  Plus,
  Presentation,
  Search,
  Sparkles,
  Table2,
  Trash2,
  Webhook,
  X,
} from 'lucide-react';
import { ThemeToggle } from '../ui/ThemeToggle';
import { Logo } from '../Logo';
import { ADMIN_NAV_GROUPS } from '../../config/adminNav';
import { useForesight } from '@foresightjs/react';
import { prefetchRoute } from '../../lib/foresight';
import { cn } from '../../lib/utils';
import { canEnterAdmin, getStoredUser, hasCapability } from '@/services/authTokenStore';
import { useChatStore } from '../../stores/chatStore';
import { listSessions, deleteSession as deleteSessionApi, getSessionMessages } from '../../services/agentService';
import type { Session } from '../../types';

type SidebarPanel = 'nav' | 'chats' | 'admin';
type UtilityModalType = 'market' | 'email' | 'usage' | null;

interface NavItem {
  key: string;
  label: string;
  path: string;
  badge?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  match: (pathname: string) => boolean;
}

const PRIMARY_NAV: NavItem[] = [
  { key: 'home', label: '创作首页', path: '/', icon: Sparkles, match: (p) => p === '/' },
  { key: 'chat', label: '对话工作台', path: '/chat', icon: MessageSquareText, match: (p) => p.startsWith('/chat') },
  { key: 'agents', label: 'AI 智能体', path: '/agents', badge: '5', icon: Bot, match: (p) => p.startsWith('/agents') },
  { key: 'canvas', label: '创作画布', path: '/canvas', icon: Palette, match: (p) => p.startsWith('/canvas') },
];

/** 最近会话按钮：Foresight 预测到用户将点击时，预热该会话消息（幂等读取）。 */
const PrefetchSessionButton: React.FC<{
  sessionId: string;
  title: string;
  isCurrent: boolean;
  icon: React.ReactNode;
  onClick: () => void;
}> = ({ sessionId, title, isCurrent, icon, onClick }) => {
  const { elementRef } = useForesight<HTMLButtonElement>({
    name: `session:${sessionId}`,
    callback: () => {
      if (isCurrent) return;
      // 仅预热服务端/浏览器缓存，不写任何状态；结果丢弃，失败静默
      void getSessionMessages(sessionId).catch(() => undefined);
    },
  });
  return (
    <button
      ref={elementRef}
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        'aos-nav-item !items-start !py-2 !text-[12.5px]',
        isCurrent && 'bg-[var(--surface-2)] text-[var(--foreground)] font-semibold',
      )}
    >
      {icon}
      <span className="line-clamp-2 flex-1 leading-snug">{title || '未命名对话'}</span>
    </button>
  );
};

/** 主导航按钮：Foresight 预测到用户将点击时，提前预取对应路由 chunk。 */
const PrefetchNavButton: React.FC<{
  path: string;
  label: string;
  badge?: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  active: boolean;
  onClick: () => void;
}> = ({ path, label, badge, Icon, active, onClick }) => {
  const { elementRef } = useForesight<HTMLButtonElement>({
    name: `nav:${path}`,
    callback: () => prefetchRoute(path),
  });
  return (
    <button
      ref={elementRef}
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn('aos-nav-item justify-between', active && 'active')}
    >
      <span className="flex items-center gap-2.5 truncate">
        <Icon size={16} className="shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      {badge && (
        <span className="aos-nav-badge rounded-full px-1.5 py-0.5 text-[10.5px] font-medium tabular-nums">
          {badge}
        </span>
      )}
    </button>
  );
};

/** 会话图标：优先按智能体 slug，其次按 mode（内置智能体与 mode 一一对应）。 */
function getSessionTone(slugOrMode?: string): {
  toneClass: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
} {
  switch ((slugOrMode || '').toLowerCase()) {
    case 'ppt':
      return { toneClass: 'aos-tone-amber', Icon: Presentation };
    case 'website':
      return { toneClass: 'aos-tone-sky', Icon: Globe };
    case 'office':
      return { toneClass: 'aos-tone-emerald', Icon: Table2 };
    case 'email':
      return { toneClass: 'aos-tone-rose', Icon: Mail };
    case 'general':
      return { toneClass: 'aos-tone-violet', Icon: Sparkles };
    default:
      return { toneClass: 'aos-tone-violet', Icon: MessageSquare };
  }
}

/**
 * 全站统一持久化外壳（1:1 复刻 agenticos.html 原型）：
 * - 暖珊瑚 + 天蓝 + 淡紫弥散光晕背景 + 建筑细点阵
 * - 左侧固定 240px 悬浮毛玻璃栏：品牌标识 → 主导航（含胶囊徽章）→ 最近会话（彩色语义图标）→ 底部三格快捷栏（集成/邮箱/用量）→ 用户信息 + 主题切换
 * - 支持侧栏左右滑动 / 点击胶囊平滑切换至完整可搜索「对话列表」
 * - 顶部悬浮毛玻璃双胶囊顶栏在首页、对话、智能体、作品库、企业后台全站统一常驻
 */
export const AppShell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [user] = useState(() => getStoredUser());
  const showAdmin = canEnterAdmin();

  const storeSessions = useChatStore((s) => s.sessions);
  const setStoreSessions = useChatStore((s) => s.setSessions);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const setCurrentSessionId = useChatStore((s) => s.setCurrentSessionId);

  // 全站统一保留顶栏与侧栏（含创作画布），侧栏展开/收缩由用户点击 Logo 控制
  const isCanvasRoute = location.pathname.startsWith('/canvas');
  const hideGlobalTopBar = false;

  const [manualCollapsed, setManualCollapsed] = useState<boolean>(false);
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [activePanel, setActivePanel] = useState<SidebarPanel>(() =>
    location.pathname.startsWith('/chat') ? 'chats' : location.pathname.startsWith('/admin') ? 'admin' : 'nav',
  );
  const [expandedAdminGroups, setExpandedAdminGroups] = useState<string[]>([]);
  const [chatSearch, setChatSearch] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(false);

  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState('');
  const [utilityModal, setUtilityModal] = useState<UtilityModalType>(null);

  const swipeStartRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    setMobileOpen(false);
    if (location.pathname.startsWith('/chat')) setActivePanel('chats');
    else if (location.pathname.startsWith('/admin')) setActivePanel('admin');
    else setActivePanel('nav');
  }, [location.pathname]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdOpen((v) => !v);
      } else if (e.key === 'Escape') {
        setCmdOpen(false);
        setUtilityModal(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const fetchRecentSessions = useCallback(async () => {
    if (!user) return;
    setLoadingSessions(true);
    try {
      const items = await listSessions();
      if (Array.isArray(items) && items.length > 0) {
        setStoreSessions((prev) => {
          const existingById = new Map(prev.map((s) => [s.id, s]));
          return items.map((item) => {
            const existing = existingById.get(item.id);
            if (existing) {
              return { ...existing, title: item.title || existing.title };
            }
            return {
              id: item.id,
              title: item.title || '未命名对话',
              messages: [],
              updatedAt: item.updated_at ? new Date(item.updated_at).getTime() : Date.now(),
              mode: (item.mode as Session['mode']) || 'general',
            };
          });
        });
      }
    } catch {
      // Quietly ignore if offline
    } finally {
      setLoadingSessions(false);
    }
  }, [user, setStoreSessions]);

  useEffect(() => {
    if (user && storeSessions.length === 0) {
      void fetchRecentSessions();
    }
  }, [user, storeSessions.length, fetchRecentSessions]);

  const collapsed = manualCollapsed;

  const navItems: NavItem[] = useMemo(
    () =>
      PRIMARY_NAV.map((item) =>
        item.key === 'chat' && storeSessions.length > 0
          ? { ...item, badge: String(storeSessions.length) }
          : item,
      ),
    [storeSessions.length],
  );

  const filteredSessions = useMemo(() => {
    const q = chatSearch.trim().toLowerCase();
    if (!q) return storeSessions;
    return storeSessions.filter((s) => (s.title || '新对话').toLowerCase().includes(q));
  }, [storeSessions, chatSearch]);

  // 最近会话：渲染全部，由 flex-1 容器 + 底部渐隐决定显示多少，
  // 不再用像素计算硬切条数（之前会切断最后半行、出现难看的滚动条）。
  const recentPreviewSessions = storeSessions.slice(0, 3);

  const cmdMatches = useMemo(() => {
    const q = cmdQuery.trim().toLowerCase();
    const base = navItems.map((n) => ({
      id: `nav-${n.key}`,
      label: `前往：${n.label}`,
      sub: n.path,
      Icon: n.icon,
      run: () => {
        navigate(n.path);
        setCmdOpen(false);
      },
    }));
    if (!q) return base;
    return base.filter((b) => b.label.toLowerCase().includes(q) || b.sub.toLowerCase().includes(q));
  }, [cmdQuery, navItems, navigate]);

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
      const order: SidebarPanel[] = ['nav', 'chats', 'admin'];
      const idx = order.indexOf(activePanel);
      const next = dx < 0 ? Math.min(idx + 1, order.length - 1) : Math.max(idx - 1, 0);
      setActivePanel(order[next]);
    }
  };

  const roleDisplay = useMemo(() => {
    if (!user) return '访客 · guest';
    const role = (user as { role?: string }).role;
    if (role === 'superadmin') return '超级管理员 · superadmin';
    if (role === 'admin') return '管理员 · admin';
    if (role === 'operator') return '运营 · operator';
    if (role === 'auditor') return '审计员 · auditor';
    return user.email || '普通用户 · user';
  }, [user]);

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
                onClick={() => navigate(item.path)}
                title={item.label}
                aria-current={active ? 'page' : undefined}
                className={cn('aos-nav-item !justify-center !px-0', active && 'active')}
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
        {/* 滑动切换轨道（支持手势左滑/右滑与点击按钮平滑切换主导航 ⇄ 全部对话） */}
        <div
          onPointerDown={onSidebarPointerDown}
          onPointerUp={onSidebarPointerUp}
          className="relative min-h-0 flex-1 overflow-hidden"
        >
          <motion.div
            animate={{
              x: activePanel === 'nav' ? '0%' : activePanel === 'chats' ? '-33.333%' : '-66.666%',
            }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="flex h-full w-[300%]"
          >
            {/* 面板 1：主导航 + 分割线 + 最近会话（1:1 复刻原型截图左侧栏） */}
            <div className="flex h-full w-1/3 shrink-0 flex-col gap-3 overflow-hidden pr-0.5">
              <nav className="flex shrink-0 flex-col gap-1" aria-label="主导航">
                {navItems.map((item) => (
                  <PrefetchNavButton
                    key={item.key}
                    path={item.path}
                    label={item.label}
                    badge={item.badge}
                    Icon={item.icon}
                    active={item.match(location.pathname)}
                    onClick={() => {
                      // 点主导航任何项都滑回对应面板，避免停留在后台面板回不来
                      setActivePanel(item.key === 'chat' ? 'chats' : 'nav');
                      navigate(item.path);
                    }}
                  />
                ))}
              </nav>

              <div className="h-px w-full bg-[var(--border-subtle)]" />

              {/* 最近会话区（点击标题右侧可平滑滑入完整对话列表） */}
              <div className="aos-recent-list flex min-h-0 flex-1 flex-col gap-1 overflow-hidden">
                <div className="flex shrink-0 items-center justify-between px-2.5 pb-1 text-[11px] font-medium text-[var(--muted-foreground)]">
                  <span>最近会话</span>
                  <button
                    type="button"
                    onClick={() => setActivePanel('chats')}
                    className="inline-flex items-center gap-1 bg-transparent border-0 p-0 text-[10.5px] font-medium text-emerald-600 hover:underline dark:text-emerald-400 cursor-pointer"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 aos-pulse-dot" />
                    <span>全部对话</span>
                    <ChevronRight size={11} />
                  </button>
                </div>

                {recentPreviewSessions.length > 0 ? (
                  recentPreviewSessions.map((session) => {
                    const { toneClass, Icon: ModeIcon } = getSessionTone(session.agentProfileSlug || session.mode);
                    const isCurrent =
                      location.pathname.startsWith('/chat') && currentSessionId === session.id;
                    return (
                      <PrefetchSessionButton
                        key={session.id}
                        sessionId={session.id}
                        title={session.title || '未命名对话'}
                        isCurrent={isCurrent}
                        onClick={() => handleSelectSession(session.id)}
                        icon={
                          <span className={cn('aos-icon-badge mt-0.5 h-6 w-6 shrink-0 !rounded-lg', toneClass)}>
                            <ModeIcon size={13} />
                          </span>
                        }
                      />
                    );
                  })
                ) : (
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="aos-nav-item !py-2 !text-[12.5px]"
                  >
                    <span className="aos-icon-badge aos-tone-amber h-6 w-6 !rounded-lg">
                      <Plus size={13} />
                    </span>
                    <span className="flex-1 truncate">开启第一个智能体对话</span>
                  </button>
                )}
              </div>
            </div>

            {/* 面板 2：完整对话列表（带新建、搜索与删除，支持右滑返回主导航） */}
            <div className="flex h-full w-1/3 shrink-0 flex-col pl-1">
              <div className="mb-2 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setActivePanel('nav')}
                  title="返回主导航"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="aos-cta-pill h-8 flex-1 !rounded-xl !text-xs"
                >
                  <Plus size={14} />
                  新建对话
                </button>
              </div>

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
                  className="h-8 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] pl-8 pr-2.5 text-xs text-[var(--foreground)] outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus:border-[var(--border-strong)]"
                />
              </div>

              <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-0.5">
                {!user ? (
                  <div className="flex flex-1 flex-col items-center justify-center gap-2 px-3 text-center">
                    <p className="text-xs text-[var(--muted-foreground)]">登录后可同步与查看历史对话</p>
                    <button
                      type="button"
                      onClick={() => navigate('/login')}
                      className="aos-cta-pill !py-1.5 !px-3.5 !text-xs"
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
                    const { toneClass, Icon: ModeIcon } = getSessionTone(session.agentProfileSlug || session.mode);
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
                          'group flex items-center justify-between gap-2 rounded-xl px-2 py-2 text-left text-[12.5px] transition-all cursor-pointer',
                          isCurrent
                            ? 'bg-[var(--primary)] font-semibold text-[var(--primary-foreground)] shadow-sm'
                            : 'text-[var(--foreground)]/85 hover:bg-[var(--surface-2)]',
                        )}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-2">
                          <span
                            className={cn(
                              'flex h-6 w-6 shrink-0 items-center justify-center rounded-lg',
                              isCurrent ? 'bg-white/15 text-current' : toneClass,
                            )}
                          >
                            <ModeIcon size={13} />
                          </span>
                          <span className="truncate">{session.title || '新对话'}</span>
                        </span>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSession(session.id, e)}
                          title="删除对话"
                          aria-label="删除对话"
                          className="shrink-0 rounded-lg p-1 opacity-0 transition-opacity hover:bg-rose-500/20 hover:text-rose-500 group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* 面板 3：企业后台功能导航（分组可展开，点击直达对应面板） */}
            <div className="flex h-full w-1/3 shrink-0 flex-col overflow-hidden pl-1">
              <div className="flex items-center justify-between px-2.5 pb-2 pt-0.5">
                <span className="text-[12px] font-semibold text-[var(--foreground)]">企业后台</span>
                <button
                  type="button"
                  onClick={() => { setActivePanel('nav'); navigate('/'); }}
                  className="aos-pill-btn !py-0.5 !px-2 !text-[10px]"
                >
                  退出后台
                </button>
              </div>
              <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pr-0.5">
                {ADMIN_NAV_GROUPS.map((group) => {
                  // 与后台功能卡片保持一致：两边都按 capability 过滤，只显示当前账户有权限的项
                  const allowed = group.items.filter((it) => hasCapability(it.cap));
                  if (allowed.length === 0) return null;
                  const expanded = expandedAdminGroups.includes(group.key);
                  const GroupIcon = group.icon;
                  return (
                    <div key={group.key} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/40 p-1">
                      <button
                        type="button"
                        onClick={() =>
                          // 手风琴：展开当前组，其余收缩；再点当前组则全部收起
                          setExpandedAdminGroups((prev) =>
                            prev.includes(group.key) && prev.length === 1 ? [] : [group.key],
                          )
                        }
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11.5px] font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
                      >
                        <GroupIcon size={14} className="shrink-0 text-[var(--muted-foreground)]" />
                        <span className="flex-1 truncate">{group.label}</span>
                        <span className="text-[10px] text-[var(--muted-foreground)]">{allowed.length}</span>
                        <ChevronRight size={12} className={cn('shrink-0 transition-transform', expanded && 'rotate-90')} />
                      </button>
                      {expanded && (
                        <div className="mt-0.5 flex flex-col gap-0.5 pb-1">
                          {allowed.map((item) => {
                            const ItemIcon = item.icon;
                            const active = location.hash.replace('#', '') === item.tab;
                            return (
                              <button
                                key={item.tab}
                                type="button"
                                onClick={() => {
                                  if (!location.pathname.startsWith('/admin')) navigate('/admin');
                                  window.location.hash = item.tab;
                                }}
                                className={cn(
                                  'flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[11.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
                                  active && 'bg-[var(--surface-2)] font-semibold text-[var(--foreground)]',
                                )}
                              >
                                <ItemIcon size={13} className="shrink-0" />
                                <span className="truncate">{item.label}</span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        </div>

        {/* 底部切换指示胶囊（轻巧不抢主导航视觉） */}
        <div className="mt-2 flex items-center justify-center gap-1.5 pt-1">
          <button
            type="button"
            onClick={() => setActivePanel('nav')}
            aria-label="主导航面板"
            className={cn(
              'h-1.5 rounded-full transition-all cursor-pointer border-0 p-0',
              activePanel === 'nav' ? 'w-5 bg-[var(--primary)]' : 'w-1.5 bg-[var(--border-strong)]',
            )}
          />
          <button
            type="button"
            onClick={() => setActivePanel('chats')}
            aria-label="对话列表面板"
            className={cn(
              'h-1.5 rounded-full transition-all cursor-pointer border-0 p-0',
              activePanel === 'chats' ? 'w-5 bg-[var(--primary)]' : 'w-1.5 bg-[var(--border-strong)]',
            )}
          />
          {showAdmin && (
            <button
              type="button"
              onClick={() => setActivePanel('admin')}
              aria-label="后台功能面板"
              className={cn(
                'h-1.5 rounded-full transition-all cursor-pointer border-0 p-0',
                activePanel === 'admin' ? 'w-5 bg-[var(--primary)]' : 'w-1.5 bg-[var(--border-strong)]',
              )}
            />
          )}
        </div>
      </div>
    );
  };

  const renderBottomDock = (compact: boolean) => (
    <div className="mt-2 flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-3">
      {!compact && (
        <div className="grid grid-cols-3 gap-1.5">
          <button
            type="button"
            onClick={() => setUtilityModal('market')}
            title="集成市场"
            className="flex flex-col items-center justify-center gap-1 rounded-xl border border-transparent bg-[var(--surface-2)] py-2 text-[var(--muted-foreground)] transition-all hover:border-[var(--border-subtle)] hover:bg-[var(--surface-3)] hover:text-[var(--foreground)] active:scale-95 cursor-pointer"
          >
            <Plug size={14} style={{ color: '#7C3AED' }} />
            <span className="text-[10.5px] font-medium">集成</span>
          </button>
          <button
            type="button"
            onClick={() => setUtilityModal('email')}
            title="邮箱设置"
            className="flex flex-col items-center justify-center gap-1 rounded-xl border border-transparent bg-[var(--surface-2)] py-2 text-[var(--muted-foreground)] transition-all hover:border-[var(--border-subtle)] hover:bg-[var(--surface-3)] hover:text-[var(--foreground)] active:scale-95 cursor-pointer"
          >
            <Mail size={14} style={{ color: '#0284C7' }} />
            <span className="text-[10.5px] font-medium">邮箱</span>
          </button>
          <button
            type="button"
            onClick={() => setUtilityModal('usage')}
            title="我的用量"
            className="flex flex-col items-center justify-center gap-1 rounded-xl border border-transparent bg-[var(--surface-2)] py-2 text-[var(--muted-foreground)] transition-all hover:border-[var(--border-subtle)] hover:bg-[var(--surface-3)] hover:text-[var(--foreground)] active:scale-95 cursor-pointer"
          >
            <BarChart2 size={14} style={{ color: '#059669' }} />
            <span className="text-[10.5px] font-medium">用量</span>
          </button>
        </div>
      )}

      {compact && !isCanvasRoute && (
        <button
          type="button"
          onClick={() => setManualCollapsed(false)}
          aria-label="展开侧栏"
          className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] cursor-pointer"
        >
          <PanelLeftOpen size={16} />
        </button>
      )}

    </div>
  );

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[var(--background)] p-2.5 text-[var(--foreground)] font-sans sm:p-3 gap-3">
      {/* 全站共享弥散光晕（暖珊瑚 + 天蓝 + 淡紫）与细点阵 */}
      <div className="aos-ambient-bg" aria-hidden="true" />
      <div className="aos-ambient-dots" aria-hidden="true" />

      {/* 移动端抽屉 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/30 backdrop-blur-xs"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="aos-glass-rail relative z-10 m-3 flex w-[248px] flex-col justify-between rounded-2xl p-3">
            <div className="flex min-h-0 flex-1 flex-col gap-3.5">
              <div className="flex items-center justify-between px-1.5 pt-1">
                <button
                  type="button"
                  onClick={() => { navigate('/'); setMobileOpen(false); }}
                  className="bg-transparent border-0 p-0 cursor-pointer"
                >
                  <Logo className="gap-2" iconSize={26} />
                </button>
                <button
                  type="button"
                  onClick={() => setMobileOpen(false)}
                  aria-label="关闭导航"
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                >
                  <X size={16} />
                </button>
              </div>
              {renderSlidingSidebarBody(false)}
            </div>
            {renderBottomDock(false)}
          </aside>
        </div>
      )}

      {/* 桌面端持久化左侧悬浮毛玻璃栏（240px rounded-2xl，与原型一致） */}
      <aside
        className={cn(
          'aos-glass-rail relative z-30 hidden h-full shrink-0 flex-col justify-between rounded-2xl p-3 transition-[width] duration-300 ease-out lg:flex',
          collapsed ? 'w-[72px]' : 'w-[240px]',
        )}
      >
        <div className="flex min-h-0 flex-1 flex-col gap-3.5">
          <div className={cn('flex items-center px-1.5 pt-1', collapsed ? 'justify-center' : 'justify-between')}>
            <button
              type="button"
              onClick={() => {
                setActivePanel('nav');
                // 点击 Logo 在任何页面（含创作画布）都展开/收缩侧栏
                setManualCollapsed((v) => !v);
              }}
              className="bg-transparent border-0 p-0 cursor-pointer"
              aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
              title={collapsed ? '展开侧栏' : '收起侧栏'}
            >
              <Logo className="gap-2" iconSize={26} showText={!collapsed} />
            </button>
          </div>

          {renderSlidingSidebarBody(collapsed)}
        </div>

        {renderBottomDock(collapsed)}
      </aside>

      {/* 右侧主列：原型统一悬浮顶栏 + 独立滚动工作区 */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
        {!hideGlobalTopBar && (
          <header className="z-30 flex shrink-0 items-center justify-between gap-2 px-1 pb-2 sm:px-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                aria-label="打开导航"
                className="aos-top-pill flex h-9 w-9 items-center justify-center rounded-full text-[var(--foreground)] lg:hidden cursor-pointer"
              >
                <Menu size={16} />
              </button>
              <button
                type="button"
                onClick={() => setCmdOpen(true)}
                className="aos-top-pill hidden items-center gap-2 rounded-full px-3.5 py-1.5 text-xs text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] sm:inline-flex cursor-pointer"
              >
                <Search size={13} />
                <span>快捷跳转</span>
                <kbd className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--foreground)]/70">
                  ⌘K
                </kbd>
              </button>
            </div>

            <div className="aos-top-pill flex items-center gap-2 rounded-full px-2.5 py-1.5 text-xs sm:px-3">
              {user ? (
                <>
                  {/* 用户信息（原左下角）移到右上角：头像 + 姓名/角色邮箱 */}
                  <span className="hidden items-center gap-2 rounded-full bg-[var(--surface-2)] py-1 pl-1 pr-2.5 sm:inline-flex" title={roleDisplay}>
                    <span
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white"
                      style={{ background: 'linear-gradient(135deg, #27272A, #121316)' }}
                    >
                      {(user.name || user.email || 'X').slice(0, 1).toUpperCase()}
                    </span>
                    <span className="flex min-w-0 flex-col leading-tight">
                      <span className="truncate text-[11.5px] font-semibold text-[var(--foreground)]">{user.name || '工作台'}</span>
                      <span className="max-w-[140px] truncate text-[10px] text-[var(--muted-foreground)]">{roleDisplay}</span>
                    </span>
                  </span>
                  <ThemeToggle />
                  <span className="opacity-30">|</span>
                  <button
                    type="button"
                    onClick={() => navigate('/chat')}
                    className="rounded-full px-2.5 py-1 font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] cursor-pointer"
                  >
                    对话
                  </button>
                  {showAdmin && (
                    <button
                      type="button"
                      onClick={() => {
                        if (!location.pathname.startsWith('/admin')) navigate('/admin');
                        setActivePanel('admin');
                        setExpandedAdminGroups((prev) => prev.length ? prev : [ADMIN_NAV_GROUPS[0].key]);
                      }}
                      className="aos-cta-pill !py-1 !px-3.5 !text-[11.5px]"
                    >
                      企业后台
                    </button>
                  )}
                </>
              ) : (
                <>
                  <ThemeToggle />
                  <span className="opacity-30">|</span>
                  <button
                    type="button"
                    onClick={() => navigate('/login')}
                    className="rounded-full px-2.5 py-1 font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] cursor-pointer"
                  >
                    登录
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/signup')}
                    className="aos-cta-pill !py-1 !px-3.5 !text-[11.5px]"
                  >
                    注册
                  </button>
                </>
              )}
            </div>
          </header>
        )}

        {/* 子路由主视口 */}
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </div>

      {/* ⌘K 快捷跳转命令面板 */}
      <AnimatePresence>
        {cmdOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setCmdOpen(false)}
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/35 px-4 pt-[14vh] backdrop-blur-xs"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="aos-glass-rail w-full max-w-lg overflow-hidden rounded-2xl p-2 shadow-2xl"
            >
              <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2.5">
                <Search size={15} className="text-[var(--muted-foreground)]" />
                <input
                  autoFocus
                  type="text"
                  value={cmdQuery}
                  onChange={(e) => setCmdQuery(e.target.value)}
                  placeholder="跳转页面、搜索功能..."
                  className="flex-1 bg-transparent text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
                />
                <kbd className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--muted-foreground)]">
                  ESC
                </kbd>
              </div>
              <div className="mt-1.5 flex max-h-72 flex-col gap-0.5 overflow-y-auto">
                {cmdMatches.map((item) => {
                  const Icon = item.Icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={item.run}
                      className="flex items-center justify-between rounded-xl px-3 py-2.5 text-left text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] cursor-pointer"
                    >
                      <span className="flex items-center gap-2.5">
                        <Icon size={15} className="text-[var(--muted-foreground)]" />
                        <span>{item.label}</span>
                      </span>
                      <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[10.5px] text-[var(--muted-foreground)]">
                        {item.sub}
                      </span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 底部三格快捷弹窗（集成市场 / 邮箱设置 / 我的用量） */}
      <AnimatePresence>
        {utilityModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setUtilityModal(null)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-xs"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              onClick={(e) => e.stopPropagation()}
              className="aos-glass-surface w-full max-w-lg space-y-4 rounded-2xl p-5 shadow-2xl"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-[15px] font-semibold text-[var(--foreground)]">
                  {utilityModal === 'market'
                    ? '集成市场与 MCP 工具'
                    : utilityModal === 'email'
                      ? '个人邮箱设置 (IMAP / SMTP)'
                      : '我的用量与每日配额'}
                </h3>
                <button
                  type="button"
                  onClick={() => setUtilityModal(null)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--surface-2)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  <X size={15} />
                </button>
              </div>

              {utilityModal === 'market' && (
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] p-3">
                    <div className="flex items-center gap-2.5">
                      <span className="aos-icon-badge aos-tone-slate h-8 w-8 !rounded-lg">
                        <GitBranch size={15} />
                      </span>
                      <div>
                        <div className="font-medium text-[var(--foreground)]">GitHub MCP</div>
                        <div className="text-[11px] text-[var(--muted-foreground)]">读取仓库、PR 与 Issue</div>
                      </div>
                    </div>
                    <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-emerald-600 dark:text-emerald-400">
                      已连接
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] p-3">
                    <div className="flex items-center gap-2.5">
                      <span className="aos-icon-badge aos-tone-sky h-8 w-8 !rounded-lg">
                        <Webhook size={15} />
                      </span>
                      <div>
                        <div className="font-medium text-[var(--foreground)]">飞书 / 企微 Webhook</div>
                        <div className="text-[11px] text-[var(--muted-foreground)]">任务完成与审批提醒</div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setUtilityModal(null);
                        if (showAdmin) navigate('/admin#integrations');
                        else toast.info('请联系管理员配置第三方集成');
                      }}
                      className="aos-pill-btn !py-1 !px-2.5"
                    >
                      配置
                    </button>
                  </div>
                </div>
              )}

              {utilityModal === 'email' && (
                <div className="space-y-2 text-xs">
                  <div className="space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3.5 font-mono text-[11.5px] text-[var(--foreground)]">
                    <div>IMAP: TLS 加密连接 · 读取与智能检索</div>
                    <div>SMTP: TLS 加密发送 · 发送前强制人工审批</div>
                  </div>
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setUtilityModal(null);
                        navigate('/chat');
                      }}
                      className="aos-cta-pill !py-1.5 !px-3.5 !text-xs"
                    >
                      前往对话中配置邮箱
                    </button>
                  </div>
                </div>
              )}

              {utilityModal === 'usage' && (
                <div className="space-y-3 text-xs">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-[var(--border-subtle)] p-3.5">
                      <div className="text-[var(--muted-foreground)]">当前会话数</div>
                      <div className="mt-1 text-lg font-bold tabular-nums text-[var(--foreground)]">
                        {storeSessions.length}
                      </div>
                    </div>
                    <div className="rounded-xl border border-[var(--border-subtle)] p-3.5">
                      <div className="text-[var(--muted-foreground)]">账号状态</div>
                      <div className="mt-1 text-lg font-bold text-emerald-600 dark:text-emerald-400">
                        配额健康
                      </div>
                    </div>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
                    <div
                      className="aos-bar-animate h-full rounded-full"
                      style={{
                        width: '18%',
                        background: 'linear-gradient(90deg, #34D399, #059669)',
                      }}
                    />
                  </div>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
