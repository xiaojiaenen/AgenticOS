import React, { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  AppWindow,
  Gauge,
  ShieldAlert,
  BarChart3,
  BellRing,
  BookOpen,
  Bot,
  Brain,
  Building2,
  ChevronDown,
  FlaskConical,
  Globe,
  KeyRound,
  LineChart,
  LogOut,
  MessageCircle,
  MessageSquare,
  MessageSquarePlus,
  Plug,
  Puzzle,
  Settings,
  Sparkles,
  Network,
  Cpu,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { Logo } from '../Logo';
import { MenuIcon, UserAvatarIcon } from '../ui/AnimatedIcons';
import { ThemeToggle } from '../ui/ThemeToggle';
import { getStoredUser, logout } from '../../services/authService';
import { hasCapability } from '../../services/authTokenStore';
import { toast } from 'sonner';
import { cn } from '../../lib/utils';
import { toastError } from '../../lib/errors';

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
  /**
   * 打开该面板所需的后端能力位（app/core/roles.py）。
   *
   * 战线 E-P0（系统改造总方案 8.2）：侧栏按能力过滤渲染 —— 之前
   * navGroups 是常量，auditor/operator 能看到全部入口、点了才 403。
   * 能力位与后端端点的门禁一一对应（require_admin → user:manage）；
   * 后端把某个面板的门禁细化成专用能力后，这里只改这一行。
   */
  capability: string;
};

type NavGroup = {
  id: string;
  label: string;
  /** 分组头用与菜单项一致的图标块 */
  icon: LucideIcon;
  description: string;
  items: NavItem[];
};

/** 当前登录用户可用的菜单（按能力过滤后的 navGroups）。 */
function visibleNavGroups(): NavGroup[] {
  return navGroups
    .map((group) => ({ ...group, items: group.items.filter((item) => hasCapability(item.capability)) }))
    .filter((group) => group.items.length > 0);
}

/** 分组折叠：展开后条目样式与原侧栏一致 */
const navGroups: NavGroup[] = [
  {
    id: 'overview',
    label: '系统总览',
    icon: BarChart3,
    description: '查看用户、会话和资源统计',
    items: [
      { id: 'dashboard', icon: BarChart3, label: '系统总览', description: '查看用户、会话和资源统计', capability: 'audit:view' },
      { id: 'user_analytics', icon: LineChart, label: '用户分析', description: '每用户用量、在线状态与常用工具/功能', capability: 'audit:view' },
      { id: 'quota', icon: Gauge, label: '用量与配额', description: '每日 Token 配额与超限用户运营视图', capability: 'audit:view' },
    ],
  },
  {
    id: 'content',
    label: '对话与内容',
    icon: MessageSquare,
    description: '聊天记录、公告与用户记忆',
    items: [
      { id: 'approvals', icon: ShieldAlert, label: '审批中心', description: '聚合部署/发布/工具调用的待审批事项', capability: 'approval:review' },
      { id: 'history', icon: MessageSquare, label: '聊天记录', description: '检索会话并查看完整详情', capability: 'user:manage' },
      { id: 'announcements', icon: BellRing, label: '公告设计', description: '设计用户进入系统时看到的公告', capability: 'announcement:manage' },
      { id: 'memory', icon: Brain, label: '记忆管理', description: '查看和管理 AI 学到的用户记忆', capability: 'user:manage' },
      { id: 'traces', icon: Activity, label: '运行追踪', description: '每次运行的步骤瀑布、耗时与反馈标注', capability: 'user:manage' },
      { id: 'feedback', icon: MessageSquarePlus, label: '反馈中心', description: '公开反馈广场的状态流转、官方回复与成果看板', capability: 'user:manage' },
    ],
  },
  {
    id: 'capability',
    label: '智能体与能力',
    icon: Bot,
    description: '智能体、Skill、知识库与站点',
    items: [
      { id: 'agents', icon: Bot, label: '智能体配置', description: '维护智能体、工具审批与绑定', capability: 'agent:manage' },
      { id: 'llm_providers', icon: Sparkles, label: 'AI 提供商', description: '配置全站使用的大模型后端', capability: 'provider:manage' },
      { id: 'skills', icon: Puzzle, label: 'Skill 管理', description: '管理本地 Skill 与脚本目录', capability: 'agent:manage' },
      { id: 'tool_policy', icon: ShieldAlert, label: '能力限制', description: '限制用户自建智能体可用的危险工具', capability: 'agent:manage' },
      { id: 'knowledge', icon: BookOpen, label: '知识库', description: '管理知识库文档与 Wiki 编译', capability: 'knowledge:manage' },
      { id: 'website_deploys', icon: Globe, label: '部署', description: '审批和管理网站部署请求', capability: 'gallery:manage' },
      { id: 'app_platform', icon: AppWindow, label: '网站应用', description: '应用化平台：manifest 声明、plan 审批与数据托管', capability: 'gallery:manage' },
      { id: 'evals', icon: FlaskConical, label: '评测', description: '用固定用例集回归验证智能体质量', capability: 'user:manage' },
    ],
  },
  {
    id: 'platform',
    label: '组织与系统',
    icon: Users,
    description: '账号、集成与系统配置',
    items: [
      { id: 'users', icon: Users, label: '用户管理', description: '管理账号、角色和启用状态', capability: 'user:manage' },
      { id: 'permissions', icon: Building2, label: '权限管理', description: '角色、策略与审计日志', capability: 'user:manage' },
      { id: 'integrations', icon: Plug, label: '集成管理', description: '管理第三方集成与 API 接口', capability: 'user:manage' },
      { id: 'api_keys', icon: KeyRound, label: 'API Key', description: '外部软件调用的凭证', capability: 'user:manage' },
      { id: 'gateway', icon: Network, label: '对外接口', description: '协议端点、接入配置与可用模型', capability: 'user:manage' },
      { id: 'task_queue', icon: Cpu, label: '任务队列', description: '重计算任务的队列健康、失败原因与重试', capability: 'user:manage' },
      { id: 'settings', icon: Settings, label: '系统设置', description: '管理 LDAP 认证等系统配置', capability: 'user:manage' },
    ],
  },
];

function groupOfTab(tab: string): string {
  const groups = visibleNavGroups();
  for (const group of groups) {
    if (group.items.some((item) => item.id === tab)) return group.id;
  }
  return groups[0]?.id ?? 'overview';
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
  // 默认展开总览与当前分组，其余收起，减少侧栏高度（只含能力可见的分组）
  return Object.fromEntries(visibleNavGroups().map((g) => [g.id, g.id === 'overview' || g.id === activeGroup]));
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

    const handleNavClick = useCallback(
      (tab: string) => {
        setActiveTab(tab);
        if (isMobile) onClose();
      },
      [setActiveTab, isMobile, onClose],
    );

    const handleLogout = async () => {
      try {
        await logout();
      } catch (err) {
        // 失败时给明确反馈，而非静默无响应
        toast.error(toastError(err, '退出登录失败'));
      }
      navigate('/login');
    };

    /**
     * 子菜单项：紧凑单行（图标 + 标签），左侧有一条轨道线标识层级。
     *
     * 为什么不再放大图标块与描述：侧边栏是导航而非营销位。大图标块让
     * 「分组」和「子项」看起来同等重要，用户无法判断哪些是可展开分组；
     * 收进轨道线后，层级一眼可辨，且一屏能放下更多入口。
     */
    const renderNavItem = (item: NavItem) => {
      const active = activeTab === item.id;
      const Icon = item.icon;
      return (
        <button
          key={item.id}
          type="button"
          onClick={() => handleNavClick(item.id)}
          aria-current={active ? 'page' : undefined}
          title={item.description}
          className={cn(
            'group/nav relative flex w-full items-center gap-2.5 rounded-lg py-2 pl-3 pr-2.5 text-left',
            'transition-colors duration-150',
            active
              ? 'bg-[var(--surface-2)] font-medium text-[var(--foreground)]'
              : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]/70 hover:text-[var(--foreground)]',
          )}
        >
          {/* 激活指示条：贴左边缘，与轨道线区分开 */}
          {active && (
            <motion.span
              layoutId="admin-nav-active-bar"
              className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-[var(--ring)]"
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
            />
          )}
          <Icon
            size={16}
            strokeWidth={active ? 2.1 : 1.8}
            className={cn(
              'shrink-0 transition-colors',
              active ? 'text-[var(--ring)]' : 'text-[var(--muted-foreground)] group-hover/nav:text-[var(--foreground)]',
            )}
          />
          <span className="truncate text-[13px] leading-5">{item.label}</span>
        </button>
      );
    };

    const sidebarContent = (
      <>
        <div
          className={cn(
            'relative z-10 flex items-center justify-between border-b px-4 py-4',
            'border-[var(--border-subtle)]',
          )}
        >
          {/* shrink-0：防止折叠按钮挤压字标 */}
          <Logo iconSize={22} className="text-lg shrink-0" />
          <button
            type="button"
            onClick={onClose}
            className={cn(
              'rounded-xl p-2 transition-colors hover:bg-[var(--surface-2)] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2',
              'text-[var(--muted-foreground)] hover:bg-[var(--surface-1)] hover:text-[var(--foreground)] hover:shadow-sm',
            )}
            aria-label="关闭导航"
          >
            <MenuIcon size={20} />
          </button>
        </div>

        <div className="relative z-10 flex-1 overflow-y-auto px-3 py-4">
          <div className="space-y-1">
            {visibleNavGroups().map((group) => {
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
                  {/*
                   分组头：刻意做成「小号标签行」而不是与子项同形的卡片。
                   原因：旧版分组头和子项长得一样（都是大图标块 + 标
                   题 + 描述），只靠缩进区分，用户看不出谁可展开。
                   现在分组头 = 图标 + 大写字距标签 + 旋转箭头，
                   子项 = 紧凑单行，两层级一眼可分。
                  */}
                  <motion.button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={open}
                    whileTap={{ scale: 0.99 }}
                    className={cn(
                      'group/head flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5',
                      'transition-colors focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-1',
                      'focus-visible:outline-none',
                      hasActive
                        ? 'text-[var(--foreground)]'
                        : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
                    )}
                  >
                    <group.icon
                      size={13}
                      strokeWidth={2}
                      className={cn(
                        'shrink-0 transition-colors',
                        hasActive ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)]',
                      )}
                    />
                    <span className="min-w-0 flex-1 truncate text-left text-[11px] font-semibold uppercase tracking-[0.1em]">
                      {group.label}
                    </span>
                    {hasActive && !open && (
                      <span
                        className="size-1.5 shrink-0 rounded-full bg-[var(--foreground)]"
                        aria-hidden
                      />
                    )}
                    <motion.span
                      animate={{ rotate: open ? 180 : 0 }}
                      transition={{ duration: 0.2 }}
                      className={cn('relative shrink-0', 'text-[var(--muted-foreground)]')}
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
                        <div className="mt-1 ml-3 space-y-0.5 border-l border-[var(--border-subtle)] pl-3">{group.items.map((item) => renderNavItem(item))}</div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </section>
              );
            })}
          </div>
        </div>

        <div className={cn('relative z-10 space-y-3 border-t p-4', 'border-[var(--border-subtle)]')}>
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className={cn(
              'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium shadow-lg transition-all focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2',
              'bg-zinc-900 text-white hover:bg-zinc-800 hover:shadow-button',
            )}
          >
            <MessageCircle size={18} />
            进入对话
          </button>

          <div
            className={cn(
              'flex items-center gap-3 rounded-lg p-2.5 shadow-sm transition-all hover:shadow-md',
              'border border-[var(--border-subtle)] bg-[var(--surface-1)]',
            )}
          >
            <div
              className={cn(
                'flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl shadow-sm',
                'border border-[var(--border-subtle)] bg-[linear-gradient(135deg,rgba(15,23,42,0.04),rgba(255,255,255,0.6))] text-[var(--muted-foreground)] dark:bg-[linear-gradient(135deg,rgba(250,250,250,0.04),rgba(24,24,27,0.6))]',
              )}
            >
              <UserAvatarIcon size={20} />
            </div>
            <div className="min-w-0 flex-1">
              <p className={cn('truncate text-[13px] font-medium leading-5', 'text-[var(--foreground)]')}>
                {user?.name || 'AgenticOS User'}
              </p>
              <p className={cn('truncate text-[11px] font-normal leading-4', 'text-[var(--muted-foreground)]')}>
                {user?.email || 'signed in'}
              </p>
            </div>
            {/* 主题切换：与前台聊天侧栏同一位置 —— 用户信息卡内、退出按钮左侧。
                后台原先强制 dark 且没有入口，用户找不到切换。 */}
            <ThemeToggle
              variant="icon"
              className={cn(
                'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--muted-foreground)]',
              )}
            />
            <button
              type="button"
              onClick={handleLogout}
              className={cn(
                'rounded-xl p-2 transition-colors hover:bg-[var(--surface-2)] focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2',
                'text-[var(--muted-foreground)] hover:bg-rose-50 hover:text-rose-500',
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
          'aos-glass-rail',
          isMobile ? 'fixed inset-y-3 left-3 w-[284px] rounded-2xl shadow-2xl' : 'm-2.5 h-[calc(100%-20px)] w-[280px] rounded-2xl',
          !isOpen && !isMobile && 'hidden',
        )}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-br from-[var(--surface-2)] to-transparent" />
        {sidebarContent}
      </motion.aside>
    );
  },
);

AdminSidebar.displayName = 'AdminSidebar';
