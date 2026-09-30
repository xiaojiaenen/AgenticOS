import React, { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart3,
  BellRing,
  BookOpen,
  Bot,
  Brain,
  ChevronDown,
  CloudCog,
  Globe,
  LogOut,
  MessageCircle,
  MessageSquare,
  Plug,
  Puzzle,
  Settings,
  Users,
  type LucideIcon,
} from 'lucide-react';
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

type NavItem = {
  id: string;
  icon: LucideIcon;
  label: string;
  description: string;
};

type NavGroup = {
  id: string;
  label: string;
  /** 分组头用与菜单项一致的图标块 */
  icon: LucideIcon;
  description: string;
  items: NavItem[];
};

/** 分组折叠：展开后条目样式与原侧栏一致 */
const navGroups: NavGroup[] = [
  {
    id: 'overview',
    label: '系统总览',
    icon: BarChart3,
    description: '查看用户、会话和资源统计',
    items: [{ id: 'dashboard', icon: BarChart3, label: '系统总览', description: '查看用户、会话和资源统计' }],
  },
  {
    // 完整独立功能：企业上游（不在集成管理里）
    id: 'upstream',
    label: '企业上游',
    icon: CloudCog,
    description: 'agents.gree.com 登录态与自动登录',
    items: [
      {
        id: 'upstream',
        icon: CloudCog,
        label: '企业上游',
        description: 'agents.gree.com Cookie 与自动登录',
      },
    ],
  },
  {
    id: 'content',
    label: '对话与内容',
    icon: MessageSquare,
    description: '聊天记录、公告与用户记忆',
    items: [
      { id: 'history', icon: MessageSquare, label: '聊天记录', description: '检索会话并查看完整详情' },
      { id: 'announcements', icon: BellRing, label: '公告设计', description: '设计用户进入系统时看到的公告' },
      { id: 'memory', icon: Brain, label: '记忆管理', description: '查看和管理 AI 学到的用户记忆' },
    ],
  },
  {
    id: 'capability',
    label: '智能体与能力',
    icon: Bot,
    description: '智能体、Skill、知识库与站点',
    items: [
      { id: 'agents', icon: Bot, label: '智能体配置', description: '维护智能体、工具审批与绑定' },
      { id: 'skills', icon: Puzzle, label: 'Skill 管理', description: '管理本地 Skill 与脚本目录' },
      { id: 'knowledge', icon: BookOpen, label: '知识库', description: '管理知识库文档与 Wiki 编译' },
      { id: 'website_deploys', icon: Globe, label: '网站部署', description: '审批和管理网站部署请求' },
    ],
  },
  {
    id: 'platform',
    label: '组织与系统',
    icon: Users,
    description: '账号、集成与系统配置',
    items: [
      { id: 'users', icon: Users, label: '用户管理', description: '管理账号、角色和启用状态' },
      { id: 'integrations', icon: Plug, label: '集成管理', description: '管理第三方集成与 API 接口' },
      { id: 'settings', icon: Settings, label: '系统设置', description: '管理 LDAP 认证等系统配置' },
    ],
  },
];

function groupOfTab(tab: string): string {
  for (const group of navGroups) {
    if (group.items.some((item) => item.id === tab)) return group.id;
  }
  return navGroups[0].id;
}

const STORAGE_KEY = 'agenticos-admin-nav-expanded';

function loadExpanded(activeTab: string): Record<string, boolean> {
  const activeGroup = groupOfTab(activeTab);
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, boolean>;
      return { ...parsed, [activeGroup]: true };
    }
  } catch {
    // ignore
  }
  // 默认展开总览与当前分组，其余收起，减少侧栏高度
  return Object.fromEntries(navGroups.map((g) => [g.id, g.id === 'overview' || g.id === activeGroup]));
}

function persistExpanded(map: Record<string, boolean>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

export const AdminSidebar = React.memo(
  ({ activeTab, setActiveTab, isMobile, isOpen, onClose }: AdminSidebarProps) => {
    const navigate = useNavigate();
    const user = getStoredUser();
    const [expanded, setExpanded] = useState<Record<string, boolean>>(() => loadExpanded(activeTab));

    React.useEffect(() => {
      const gid = groupOfTab(activeTab);
      setExpanded((prev) => {
        if (prev[gid]) return prev;
        const next = { ...prev, [gid]: true };
        persistExpanded(next);
        return next;
      });
    }, [activeTab]);

    const toggleGroup = useCallback((groupId: string) => {
      setExpanded((prev) => {
        const next = { ...prev, [groupId]: !prev[groupId] };
        persistExpanded(next);
        return next;
      });
    }, []);

    const handleSelect = useCallback(
      (tab: string) => {
        setActiveTab(tab);
        if (isMobile) onClose();
      },
      [setActiveTab, isMobile, onClose],
    );

    const handleLogout = async () => {
      await logout();
      navigate('/login');
    };

    /** 与旧版一致的菜单项：大图标块 + 标题 + 描述 */
    const renderNavItem = (item: NavItem) => {
      const active = activeTab === item.id;
      return (
        <motion.button
          key={item.id}
          type="button"
          onClick={() => handleSelect(item.id)}
          whileTap={{ scale: 0.985 }}
          className={cn(
            'admin-nav-item focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
            active
              ? 'admin-nav-item-active text-zinc-900'
              : 'text-slate-600 hover:text-slate-900',
          )}
        >
          {active && (
            <motion.span
              layoutId="admin-active-nav"
              className={cn(
                'absolute inset-0 rounded-lg border-l-3',
                'border-l-indigo-600 bg-white shadow-md',
              )}
              transition={{ type: 'spring', damping: 28, stiffness: 380 }}
            />
          )}
          <div
            className={cn(
              'admin-nav-icon',
              active
                ? 'border-zinc-900 bg-zinc-900 text-white shadow-button'
                : 'border-slate-200/80 bg-white/80 text-slate-500 group-hover:text-slate-700',
            )}
          >
            <item.icon size={18} />
          </div>
          <div className="relative min-w-0">
            <p className="truncate text-sm font-semibold">{item.label}</p>
            <p
              className={cn(
                'mt-1 line-clamp-2 text-xs font-medium leading-5',
                'text-slate-400',
              )}
            >
              {item.description}
            </p>
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
    };

    const sidebarContent = (
      <>
        <div
          className={cn(
            'relative z-10 flex items-center justify-between border-b px-4 py-4',
            'border-slate-200/80',
          )}
        >
          <Logo iconSize={22} className="text-lg" />
          <button
            type="button"
            onClick={onClose}
            className={cn(
              'rounded-xl p-2 transition-all active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
              'text-slate-400 hover:bg-white hover:text-slate-700 hover:shadow-sm',
            )}
            aria-label="关闭导航"
          >
            <MenuIcon size={20} />
          </button>
        </div>

        <div className="relative z-10 flex-1 overflow-y-auto px-3 py-4">
          <div className="space-y-1">
            {navGroups.map((group) => {
              const open = !!expanded[group.id];
              const hasActive = group.items.some((i) => i.id === activeTab);
              const isOverview = group.id === 'overview';
              const single = group.items.length === 1;

              // 总览仅一项：直接渲染原样式条目，无折叠头
              if (isOverview || single) {
                return (
                  <div key={group.id} className="space-y-1">
                    {group.items.map((item) => renderNavItem(item))}
                  </div>
                );
              }

              return (
                <section key={group.id} className="pt-2 first:pt-0">
                  {/* 分组头：沿用 admin-nav-item 视觉语言，点击折叠 */}
                  <motion.button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={open}
                    whileTap={{ scale: 0.985 }}
                    className={cn(
                      'admin-nav-item focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
                      open || hasActive
                        ? 'text-slate-800'
                        : 'text-slate-600 hover:text-slate-900',
                    )}
                  >
                    <div
                      className={cn(
                        'admin-nav-icon',
                        open || hasActive
                          ? 'border-zinc-800/20 bg-zinc-900/10 text-zinc-800'
                          : 'border-slate-200/80 bg-white/80 text-slate-500',
                      )}
                    >
                      <group.icon size={18} />
                    </div>
                    <div className="relative min-w-0 flex-1 text-left">
                      <p className="truncate text-sm font-semibold">{group.label}</p>
                      <p
                        className={cn(
                          'mt-1 line-clamp-2 text-xs font-medium leading-5',
                          'text-slate-400',
                        )}
                      >
                        {group.description}
                      </p>
                    </div>
                    <motion.span
                      animate={{ rotate: open ? 180 : 0 }}
                      transition={{ duration: 0.2 }}
                      className={cn('relative shrink-0', 'text-slate-400')}
                    >
                      <ChevronDown size={18} />
                    </motion.span>
                  </motion.button>

                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        key="body"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                        className="overflow-hidden"
                      >
                        <div className="mt-1 space-y-1 pl-2">{group.items.map((item) => renderNavItem(item))}</div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </section>
              );
            })}
          </div>
        </div>

        <div className={cn('relative z-10 space-y-3 border-t p-4', 'border-slate-200/80')}>
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className={cn(
              'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium shadow-lg transition-all focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
              'bg-zinc-900 text-white hover:bg-zinc-800 hover:shadow-button',
            )}
          >
            <MessageCircle size={18} />
            进入对话
          </button>

          <div
            className={cn(
              'flex items-center gap-3 rounded-lg p-2.5 shadow-sm transition-all hover:shadow-md',
              'border border-zinc-200/80 bg-white',
            )}
          >
            <div
              className={cn(
                'flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl shadow-sm',
                'border border-zinc-200 bg-[linear-gradient(135deg,rgba(15,23,42,0.06),rgba(255,255,255,0.9))] text-zinc-600',
              )}
            >
              <UserAvatarIcon size={20} />
            </div>
            <div className="min-w-0 flex-1">
              <p className={cn('truncate text-xs font-medium', 'text-slate-800')}>
                {user?.name || 'AgenticOS User'}
              </p>
              <p className={cn('truncate text-[10px] font-medium', 'text-slate-400')}>
                {user?.email || 'signed in'}
              </p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className={cn(
                'rounded-xl p-2 transition-all hover:scale-110 active:scale-90 focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2',
                'text-slate-400 hover:bg-rose-50 hover:text-rose-500',
              )}
              title="退出登录"
              aria-label="退出登录"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </>
    );

    return (
      <motion.aside
        initial={isMobile ? { x: -300 } : { width: 296 }}
        animate={{ x: 0, width: 296 }}
        exit={isMobile ? { x: -300 } : { width: 0 }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className={cn(
          'z-20 flex flex-shrink-0 flex-col overflow-hidden',
          'border-r border-zinc-200/80 bg-white/80 shadow-[10px_0_36px_rgba(15,23,42,0.06)] backdrop-blur-2xl',
          isMobile ? 'fixed inset-y-0 left-0 w-[296px] shadow-lg' : 'w-[296px]',
          !isOpen && !isMobile && 'hidden',
        )}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-br from-indigo-100/50 to-transparent" />
        {sidebarContent}
      </motion.aside>
    );
  },
);

AdminSidebar.displayName = 'AdminSidebar';
