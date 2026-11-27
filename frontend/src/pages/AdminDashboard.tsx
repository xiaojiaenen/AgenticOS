import React, { Suspense, lazy, useState, useCallback, useMemo } from 'react';
import { motion } from 'motion/react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  AppWindow,
  ArrowLeft,
  BarChart3,
  BellRing,
  BookOpen,
  Bot,
  Brain,
  Building2,
  Cpu,
  FlaskConical,
  Gauge,
  Globe,
  History,
  KeyRound,
  Loader2,
  Mail,
  MessageSquare,
  MessageSquarePlus,
  Network,
  Plug,
  Presentation,
  Puzzle,
  RefreshCw,
  Settings,
  ShieldAlert,
  ShieldBan,
  ShieldCheck,
  Sparkles,
  Table2,
  Users,
} from 'lucide-react';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { cn } from '../lib/utils';
import { hasCapability } from '../services/authTokenStore';
import { getDashboardStats, getUsageRoutes } from '../services/dashboardService';
import { getStoredUser } from '@/services/authTokenStore';

const AnnouncementManagement = lazy(() => import('../components/admin/AnnouncementManagement').then((m) => ({ default: m.AnnouncementManagement })));
const AgentManagement = lazy(() => import('../components/admin/AgentManagement').then((m) => ({ default: m.AgentManagement })));
const LlmProviderManagement = lazy(() => import('../components/admin/LlmProviderManagement').then((m) => ({ default: m.LlmProviderManagement })));
const ApiKeyManagement = lazy(() => import('../components/admin/ApiKeyManagement').then((m) => ({ default: m.ApiKeyManagement })));
const GatewayEndpointsPanel = lazy(() => import('../components/admin/GatewayEndpointsPanel').then((m) => ({ default: m.GatewayEndpointsPanel })));
const ChatHistory = lazy(() => import('../components/admin/ChatHistory').then((m) => ({ default: m.ChatHistory })));
const DashboardCharts = lazy(() => import('../components/admin/DashboardCharts').then((m) => ({ default: m.DashboardCharts })));
const UsageRoutePanel = lazy(() => import('../components/admin/UsageRoutePanel').then((m) => ({ default: m.UsageRoutePanel })));
const DashboardStats = lazy(() => import('../components/admin/DashboardStats').then((m) => ({ default: m.DashboardStats })));
const SkillManagement = lazy(() => import('../components/admin/SkillManagement').then((m) => ({ default: m.SkillManagement })));
const KnowledgeManagement = lazy(() => import('../components/admin/KnowledgeManagement').then((m) => ({ default: m.KnowledgeManagement })));
const AgentToolPolicyPanel = lazy(() => import('../components/admin/AgentToolPolicyPanel').then((m) => ({ default: m.AgentToolPolicyPanel })));
const WebsiteDeployManagement = lazy(() => import('../components/admin/WebsiteDeployManagement').then((m) => ({ default: m.WebsiteDeployManagement })));
const SystemSettings = lazy(() => import('../components/admin/SystemSettings').then((m) => ({ default: m.SystemSettings })));
const IntegrationManagement = lazy(() => import('../components/admin/IntegrationManagement').then((m) => ({ default: m.IntegrationManagement })));
const UserManagement = lazy(() => import('../components/admin/UserManagement').then((m) => ({ default: m.UserManagement })));
const MemoryPanel = lazy(() => import('../components/settings/MemoryPanel').then((m) => ({ default: m.MemoryPanel })));
const TracePanel = lazy(() => import('../components/settings/TracePanel').then((m) => ({ default: m.TracePanel })));
const EvalPanel = lazy(() => import('../components/settings/EvalPanel').then((m) => ({ default: m.EvalPanel })));
const PermissionManagement = lazy(() => import('../components/admin/PermissionManagement').then((m) => ({ default: m.PermissionManagement })));
const FeedbackCenter = lazy(() => import('../components/admin/FeedbackCenter').then((m) => ({ default: m.FeedbackCenter })));
const UserAnalytics = lazy(() => import('../components/admin/UserAnalytics').then((m) => ({ default: m.UserAnalytics })));
const ApprovalCenter = lazy(() => import('../components/admin/ApprovalCenter').then((m) => ({ default: m.ApprovalCenter })));
const TaskQueueOps = lazy(() => import('../components/admin/TaskQueueOps').then((m) => ({ default: m.TaskQueueOps })));
const AppManagement = lazy(() => import('../components/admin/AppManagement').then((m) => ({ default: m.AppManagement })));
const QuotaManagement = lazy(() => import('../components/admin/QuotaManagement').then((m) => ({ default: m.QuotaManagement })));

type AdminGroupKey = 'overview' | 'content' | 'knowledge' | 'gateway';

interface AdminModuleCard {
  tab: string;
  title: string;
  desc: string;
  cap: string;
  badge: string;
  tone: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  alert?: boolean;
  danger?: boolean;
}

const ADMIN_GROUP_TABS: {
  key: AdminGroupKey;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  { key: 'overview', label: '系统总览', icon: BarChart3 },
  { key: 'content', label: '对话与内容', icon: MessageSquare },
  { key: 'knowledge', label: '智能体与能力', icon: Cpu },
  { key: 'gateway', label: '组织与系统', icon: Building2 },
];

const ADMIN_GROUPS: Record<Exclude<AdminGroupKey, 'overview'>, AdminModuleCard[]> = {
  content: [
    { tab: 'approvals', icon: ShieldAlert, tone: 'aos-tone-amber', title: '审批中心', desc: '聚合网站部署、智能体发布与外接工具待审批事项', cap: 'approval:review', badge: '待处理', alert: true },
    { tab: 'announcements', icon: BellRing, tone: 'aos-tone-violet', title: '公告设计', desc: '设计全局弹窗公告，支持 AI 辅助生成与预览', cap: 'announcement:manage', badge: '全局公告' },
    { tab: 'history', icon: MessageSquare, tone: 'aos-tone-slate', title: '聊天记录元数据', desc: '检索会话元数据与状态（正文仅授权代查）', cap: 'user:manage', badge: '已脱敏' },
    { tab: 'user_analytics', icon: Activity, tone: 'aos-tone-sky', title: '用户行为分析', desc: '留存、活跃趋势与高频场景使用洞察', cap: 'audit:view', badge: '分析' },
    { tab: 'memory', icon: Brain, tone: 'aos-tone-sky', title: '记忆管理', desc: '查看和管理 AI 沉淀的用户长期记忆条目', cap: 'user:manage', badge: '长期记忆' },
    { tab: 'traces', icon: Activity, tone: 'aos-tone-emerald', title: '运行追踪', desc: '每次智能体运行的步骤瀑布、耗时与反馈标注', cap: 'user:manage', badge: 'OTel' },
    { tab: 'feedback', icon: MessageSquarePlus, tone: 'aos-tone-amber', title: '反馈中心', desc: '公开反馈广场状态流转、官方回复与成果看板', cap: 'user:manage', badge: '广场' },
  ],
  knowledge: [
    { tab: 'agents', icon: Bot, tone: 'aos-tone-amber', title: '智能体配置', desc: '维护内置/公开智能体、工具绑定与审批策略', cap: 'agent:manage', badge: '内置+自建' },
    { tab: 'skills', icon: Puzzle, tone: 'aos-tone-violet', title: 'Skill 管理', desc: '管理本地热插拔 Skill 与脚本目录可见性', cap: 'agent:manage', badge: '热插拔' },
    { tab: 'tool_policy', icon: ShieldBan, tone: 'aos-tone-rose', title: '能力限制', desc: '限制用户自建智能体可用的高风险工具边界', cap: 'agent:manage', badge: '强约束' },
    { tab: 'knowledge', icon: BookOpen, tone: 'aos-tone-emerald', title: '知识库与 Wiki', desc: '混合检索、知识图谱与文档 ACL 权限', cap: 'knowledge:manage', badge: 'RAG' },
    { tab: 'website_deploys', icon: Globe, tone: 'aos-tone-sky', title: '网站部署审批', desc: '审批与管理网站工程师发布的短链静态站点', cap: 'gallery:manage', badge: '短链站点', alert: true },
    { tab: 'app_platform', icon: AppWindow, tone: 'aos-tone-sky', title: '网站应用化平台', desc: 'manifest 声明、plan 审批与轻量数据托管', cap: 'gallery:manage', badge: '应用托管' },
    { tab: 'llm_providers', icon: Sparkles, tone: 'aos-tone-amber', title: 'AI 提供商', desc: '配置全站 OpenAI 兼容模型后端与凭据', cap: 'provider:manage', badge: '模型后端' },
    { tab: 'evals', icon: FlaskConical, tone: 'aos-tone-emerald', title: '回归评测', desc: '用固定用例集验证智能体回答质量', cap: 'user:manage', badge: '质量评估' },
  ],
  gateway: [
    { tab: 'users', icon: Users, tone: 'aos-tone-slate', title: '用户与角色管理', desc: '管理账号、5 级角色分配与启用状态', cap: 'user:manage', badge: '账号体系' },
    { tab: 'permissions', icon: Building2, tone: 'aos-tone-violet', title: 'Casbin 权限矩阵', desc: '角色策略、部门 ACL 与完整安全审计日志', cap: 'user:manage', badge: 'RBAC' },
    { tab: 'integrations', icon: Plug, tone: 'aos-tone-sky', title: '第三方集成与 MCP', desc: 'OpenAPI 导入、外部 MCP 接入与连通性测试', cap: 'user:manage', badge: 'MCP' },
    { tab: 'api_keys', icon: KeyRound, tone: 'aos-tone-amber', title: '平台级 API Key', desc: '供外部业务系统调用的受控密钥与额度', cap: 'apikey:manage', badge: '密钥' },
    { tab: 'gateway', icon: Network, tone: 'aos-tone-emerald', title: '对外接口网关', desc: '协议端点、接入配置与模型路由映射', cap: 'user:manage', badge: '网关' },
    { tab: 'task_queue', icon: Cpu, tone: 'aos-tone-sky', title: '任务队列', desc: '重计算队列健康度、失败重试与监控', cap: 'user:manage', badge: '队列' },
    { tab: 'quota', icon: Gauge, tone: 'aos-tone-violet', title: '配额与限流', desc: '部门及个人每日 Token 配额与速率策略', cap: 'audit:view', badge: '配额' },
    { tab: 'settings', icon: Settings, tone: 'aos-tone-slate', title: '系统设置', desc: '企业 LDAP 认证、SMTP 服务与全局安全配置', cap: 'system:settings', badge: '内网' },
  ],
};

const VALID_TABS = [
  'dashboard',
  ...ADMIN_GROUPS.content.map((m) => m.tab),
  ...ADMIN_GROUPS.knowledge.map((m) => m.tab),
  ...ADMIN_GROUPS.gateway.map((m) => m.tab),
];

function findGroupForTab(tab: string): AdminGroupKey {
  if (tab === 'dashboard') return 'overview';
  if (ADMIN_GROUPS.content.some((m) => m.tab === tab)) return 'content';
  if (ADMIN_GROUPS.knowledge.some((m) => m.tab === tab)) return 'knowledge';
  if (ADMIN_GROUPS.gateway.some((m) => m.tab === tab)) return 'gateway';
  return 'overview';
}

const TabFallback = () => (
  <div className="space-y-4" aria-busy="true">
    <div className="h-9 w-56 animate-pulse rounded-lg bg-[var(--surface-2)]" />
    <div className="h-24 animate-pulse rounded-2xl bg-[var(--surface-2)]" />
    <div className="h-64 animate-pulse rounded-2xl bg-[var(--surface-2)]" />
  </div>
);

const AGENT_DIST_BARS = [
  { label: '通用助手', icon: Sparkles, tone: 'aos-tone-slate', pct: 82, count: 512, bar: 'linear-gradient(90deg, #3F3F46, #18181B)' },
  { label: 'PPT 设计师', icon: Presentation, tone: 'aos-tone-amber', pct: 61, count: 384, bar: 'linear-gradient(90deg, #FB923C, #EA580C)' },
  { label: '办公助手', icon: Table2, tone: 'aos-tone-emerald', pct: 46, count: 289, bar: 'linear-gradient(90deg, #34D399, #059669)' },
  { label: '网站工程师', icon: Globe, tone: 'aos-tone-sky', pct: 34, count: 214, bar: 'linear-gradient(90deg, #38BDF8, #0284C7)' },
  { label: '邮箱助手', icon: Mail, tone: 'aos-tone-violet', pct: 22, count: 138, bar: 'linear-gradient(90deg, #A78BFA, #7C3AED)' },
];

export const AdminDashboard = () => {
  const [user] = useState(() => getStoredUser());
  const initialHash = window.location.hash.replace('#', '');
  const initialTab = VALID_TABS.includes(initialHash) ? initialHash : 'dashboard';

  const [activeGroup, setActiveGroup] = useState<AdminGroupKey>(() => findGroupForTab(initialTab));
  const [activeModule, setActiveModule] = useState<string | null>(() =>
    initialTab === 'dashboard' ? null : initialTab,
  );
  const [visitedModules, setVisitedModules] = useState<string[]>(() =>
    initialTab === 'dashboard' ? [] : [initialTab],
  );
  const [timeRange, setTimeRange] = useState(14);

  React.useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (VALID_TABS.includes(hash)) {
        setActiveGroup(findGroupForTab(hash));
        if (hash === 'dashboard') {
          setActiveModule(null);
        } else {
          setActiveModule(hash);
          setVisitedModules((prev) => (prev.includes(hash) ? prev : [...prev, hash]));
        }
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const selectGroup = useCallback((group: AdminGroupKey) => {
    setActiveGroup(group);
    setActiveModule(null);
    window.history.replaceState(null, '', group === 'overview' ? '#dashboard' : `#${group}`);
  }, []);

  const openModule = useCallback((tab: string) => {
    setActiveGroup(findGroupForTab(tab));
    setActiveModule(tab);
    setVisitedModules((prev) => (prev.includes(tab) ? prev : [...prev, tab]));
    if (window.location.hash.replace('#', '') !== tab) {
      window.history.replaceState(null, '', `#${tab}`);
    }
  }, []);

  const dashboardQuery = useQuery({
    queryKey: ['admin', 'dashboard', timeRange],
    queryFn: () => getDashboardStats(timeRange),
    enabled: activeGroup === 'overview' && !activeModule,
  });

  const usageRouteQuery = useQuery({
    queryKey: ['admin', 'usage-routes', timeRange],
    queryFn: () => getUsageRoutes(timeRange),
    enabled: activeGroup === 'overview' && !activeModule,
  });

  const dashboardData = dashboardQuery.data ?? null;
  const isDashboardLoading = dashboardQuery.isFetching;
  const dashboardError = dashboardQuery.isError
    ? (dashboardQuery.error as Error).message || '仪表盘数据加载失败'
    : null;

  const currentModuleMeta = useMemo(() => {
    if (!activeModule) return null;
    for (const group of Object.values(ADMIN_GROUPS)) {
      const found = group.find((m) => m.tab === activeModule);
      if (found) return found;
    }
    return null;
  }, [activeModule]);

  const roleBadgeText = useMemo(() => {
    const role = (user as { role?: string } | null)?.role || 'admin';
    if (role === 'superadmin') return '超级管理员 · superadmin';
    if (role === 'operator') return '运营 · operator';
    if (role === 'auditor') return '审计员 · auditor';
    return '管理员 · admin';
  }, [user]);

  const renderModulePanel = (tab: string) => {
    switch (tab) {
      case 'history': return <ChatHistory />;
      case 'user_analytics': return <UserAnalytics />;
      case 'feedback': return <FeedbackCenter />;
      case 'approvals': return <ApprovalCenter />;
      case 'users': return <UserManagement />;
      case 'permissions': return <PermissionManagement />;
      case 'agents': return <AgentManagement />;
      case 'llm_providers': return <LlmProviderManagement />;
      case 'integrations': return <IntegrationManagement />;
      case 'api_keys': return <ApiKeyManagement />;
      case 'gateway': return <GatewayEndpointsPanel />;
      case 'task_queue': return <TaskQueueOps />;
      case 'app_platform': return <AppManagement />;
      case 'quota': return <QuotaManagement />;
      case 'skills': return <SkillManagement />;
      case 'tool_policy': return <AgentToolPolicyPanel />;
      case 'knowledge': return <KnowledgeManagement />;
      case 'website_deploys': return <WebsiteDeployManagement />;
      case 'announcements': return <AnnouncementManagement />;
      case 'settings': return <SystemSettings />;
      case 'memory': return <MemoryPanel />;
      case 'traces': return <TracePanel />;
      case 'evals': return <EvalPanel />;
      default:
        return (
          <div className="aos-glass-surface flex min-h-[300px] flex-col items-center justify-center gap-3 rounded-2xl p-8 text-center">
            <AlertTriangle size={28} className="text-[var(--muted-foreground)]" />
            <p className="text-sm font-semibold text-[var(--foreground)]">暂无可用的管理面板</p>
          </div>
        );
    }
  };

  return (
    <motion.div
      key="admin"
      initial={false}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="relative h-full w-full overflow-y-auto px-1 pb-14 font-sans text-[var(--foreground)] sm:px-3"
    >
      <main id="main-content" className="mx-auto w-full max-w-[1140px] px-1 sm:px-4">
        {/* 管理后台导航带：进入具体模块时整块隐藏，避免与子面板标题形成双层大标题 */}
        {!activeModule && (
        <div className="aos-glass-surface mb-3 mt-1 rounded-2xl border border-[var(--border-subtle)] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="aos-icon-badge aos-tone-slate h-7 w-7 !rounded-lg">
                <ShieldCheck size={15} />
              </span>
              <span className="text-sm font-semibold text-[var(--foreground)]">管理后台</span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-0.5 text-[10.5px] font-semibold text-[var(--foreground)]">
                {roleBadgeText}
              </span>
            </div>

            {activeGroup === 'overview' && !activeModule && (
              <div className="flex flex-wrap items-center gap-1.5">
                {[7, 14, 30].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setTimeRange(d)}
                    className={cn('aos-pill-btn !py-1 !px-2.5 !text-xs', timeRange === d && 'active')}
                  >
                    {d}天
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => void dashboardQuery.refetch()}
                  disabled={isDashboardLoading}
                  title="刷新看板"
                  className="aos-pill-btn !p-1.5"
                >
                  {isDashboardLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                </button>
              </div>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-3">
            <div className="flex flex-wrap items-center gap-1.5">
              {ADMIN_GROUP_TABS.map((g) => {
                const Icon = g.icon;
                const active = activeGroup === g.key;
                return (
                  <button
                    key={g.key}
                    type="button"
                    onClick={() => selectGroup(g.key)}
                    className={cn('aos-pill-btn !px-3.5 !py-1.5 !text-xs', active && 'active')}
                  >
                    <Icon size={14} />
                    <span>{g.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2 text-[11.5px] text-[var(--muted-foreground)]">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
              <span>不含他人对话正文</span>
            </div>
          </div>
        </div>
        )}

        {/* 当点进某个具体管理模块时，显示轻巧返回栏 + 真实业务管理面板 */}
        {activeModule ? (
          <div className="space-y-4">
            <div className="aos-glass-surface flex items-center justify-between gap-3 rounded-2xl px-4 py-3">
              <button
                type="button"
                onClick={() => setActiveModule(null)}
                className="aos-pill-btn !py-1.5 !px-3 !text-xs"
              >
                <ArrowLeft size={14} />
                <span>返回模块列表</span>
              </button>
              {currentModuleMeta && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-semibold text-[var(--foreground)]">{currentModuleMeta.title}</span>
                  <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[10.5px] text-[var(--muted-foreground)]">
                    {currentModuleMeta.cap}
                  </span>
                </div>
              )}
            </div>

            {visitedModules.map((tab) => (
              <div key={tab} hidden={tab !== activeModule} className="[&[hidden]]:!hidden">
                <Suspense fallback={<TabFallback />}>{renderModulePanel(tab)}</Suspense>
              </div>
            ))}
          </div>
        ) : activeGroup === 'overview' ? (
          /* 系统总览（1:1 复刻截图 5 布局：4 列 KPI + 7/5 分布与实时动态 + 真实图表） */
          <div className="space-y-4">
            {dashboardError && (
              <div className="flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}

            {isDashboardLoading && !dashboardData ? (
              <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((i) => (
                  <ChartSkeleton key={i} variant="stat" />
                ))}
              </div>
            ) : dashboardData ? (
              <Suspense fallback={<TabFallback />}>
                <DashboardStats summary={dashboardData.summary} />
              </Suspense>
            ) : null}

            {/* 原型同款 7/5 双栏卡片：智能体调用分布 + 实时安全与审批动态 */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="aos-glass-surface rounded-2xl p-5 lg:col-span-7">
                <div className="mb-4 flex items-center gap-2.5">
                  <span className="aos-icon-badge aos-tone-slate h-8 w-8 !rounded-xl">
                    <BarChart3 size={15} />
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--foreground)]">各内置智能体 {timeRange} 日调用分布</h3>
                    <p className="text-[11px] text-[var(--muted-foreground)]">含主对话、网站应用与公开短链任务</p>
                  </div>
                </div>
                <div className="space-y-3.5 text-xs">
                  {AGENT_DIST_BARS.map((row, idx) => (
                    <div key={row.label} className="flex items-center gap-3">
                      <span className={cn('aos-icon-badge h-7 w-7 !rounded-lg', row.tone)}>
                        <row.icon size={13} />
                      </span>
                      <span className="w-20 font-medium text-[var(--foreground)]">{row.label}</span>
                      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
                        <div
                          className="aos-bar-animate h-full rounded-full"
                          style={{
                            width: `${row.pct}%`,
                            animationDelay: `${idx * 60}ms`,
                            background: row.bar,
                          }}
                        />
                      </div>
                      <span className="w-10 text-right font-semibold tabular-nums text-[var(--foreground)]">
                        {row.count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="aos-glass-surface rounded-2xl p-5 lg:col-span-5">
                <div className="mb-4 flex items-center gap-2.5">
                  <span className="aos-icon-badge aos-tone-emerald h-8 w-8 !rounded-xl">
                    <History size={15} />
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--foreground)]">实时安全与审批动态</h3>
                    <p className="text-[11px] text-[var(--muted-foreground)]">仅记录元数据，不含对话正文</p>
                  </div>
                </div>
                <div className="space-y-2.5 text-xs">
                  <button
                    type="button"
                    onClick={() => openModule('approvals')}
                    className="flex w-full items-start gap-2.5 rounded-xl bg-[var(--surface-2)] p-3 text-left transition-colors hover:bg-[var(--surface-3)] cursor-pointer border-0"
                  >
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[var(--foreground)]">工具调用人工审批策略运行正常</div>
                      <div className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">点击进入审批中心查看待处理项</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => openModule('website_deploys')}
                    className="flex w-full items-start gap-2.5 rounded-xl bg-[var(--surface-2)] p-3 text-left transition-colors hover:bg-[var(--surface-3)] cursor-pointer border-0"
                  >
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-amber-500 aos-pulse-dot" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[var(--foreground)]">网站短链与公开应用部署审核</div>
                      <div className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">支持发布前安全审计与一键下架</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => openModule('knowledge')}
                    className="flex w-full items-start gap-2.5 rounded-xl bg-[var(--surface-2)] p-3 text-left transition-colors hover:bg-[var(--surface-3)] cursor-pointer border-0"
                  >
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-sky-500" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[var(--foreground)]">知识库增量索引与权限 ACL 同步</div>
                      <div className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">混合检索 · 部门可见性隔离</div>
                    </div>
                  </button>
                </div>
              </div>
            </div>

            {/* 保留真实后端趋势图表与路由审计面板 */}
            {dashboardData && (
              <Suspense fallback={<TabFallback />}>
                <DashboardCharts data={dashboardData} />
                {usageRouteQuery.data && <UsageRoutePanel data={usageRouteQuery.data} />}
              </Suspense>
            )}
          </div>
        ) : (
          /* 分组模块卡片网格（对话与内容 / 智能体与能力 / 组织与系统） */
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {ADMIN_GROUPS[activeGroup].filter((m) => hasCapability(m.cap)).map((m) => (
              <button
                key={m.tab}
                type="button"
                onClick={() => openModule(m.tab)}
                className="aos-glass-surface aos-surface-interactive group flex flex-col justify-between gap-3.5 rounded-2xl p-4 text-left cursor-pointer"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className={cn('aos-icon-badge h-10 w-10', m.tone)}>
                      <m.icon size={17} />
                    </span>
                    <span
                      className={cn(
                        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 text-[10.5px] font-medium',
                        m.danger ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--muted-foreground)]',
                      )}
                    >
                      {m.alert && <span className="h-1.5 w-1.5 rounded-full bg-amber-500 aos-pulse-dot" />}
                      {m.badge}
                    </span>
                  </div>
                  <div className="mt-3 text-[14.5px] font-semibold text-[var(--foreground)]">{m.title}</div>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)]">{m.desc}</p>
                </div>
                <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-2.5 font-mono text-[11px] text-[var(--muted-foreground)]">
                  <span>{m.cap}</span>
                  <span className="font-sans font-medium text-[var(--foreground)]">进入 →</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </main>
    </motion.div>
  );
};
