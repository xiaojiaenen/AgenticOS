import React, { Suspense, lazy, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, RefreshCw, ShieldAlert } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { Button } from '@/components/shadcn/button';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';
import { getDashboardStats, getUsageRoutes } from '../services/dashboardService';

/*
 * 17 个管理面板全部 React.lazy 按需分包：此前它们被静态打进 admin 首包
 * （约 1.9 万行组件 + recharts/xyflow），首屏只用到一个 tab 却要下载全部。
 * 每个面板体积可观（SystemSettings 704 行…），
 * 拆开后切到对应 tab 才拉取对应 chunk，与页面级 lazy 的既有模式对齐。
 */

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

/** tab chunk 加载/渲染中的占位：与面板卡片同构的骨架，避免突兀空白 */
const TabFallback = () => (
  <div className="space-y-4" aria-busy="true">
    <div className="h-9 w-56 animate-pulse rounded-lg bg-[var(--surface-2)]" />
    <div className="h-24 animate-pulse rounded-xl bg-[var(--surface-2)]" />
    <div className="h-64 animate-pulse rounded-xl bg-[var(--surface-2)]" />
  </div>
);


export const AdminDashboard = () => {
  const VALID_TABS = ['dashboard', 'user_analytics', 'history', 'feedback', 'approvals', 'users', 'permissions', 'agents', 'llm_providers', 'integrations', 'api_keys', 'gateway', 'task_queue', 'quota', 'app_platform', 'skills', 'tool_policy', 'knowledge', 'website_deploys', 'announcements', 'settings', 'memory', 'traces', 'evals'];
  // tab 与 URL hash 双向同步：刷新 / 分享链接不丢失当前管理页
  const [activeTab, setActiveTab] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    return VALID_TABS.includes(hash) ? hash : 'dashboard';
  });
  // Tab keep-alive：记录访问过的面板，切走时用 hidden 保留挂载而非卸载。
  // 面板内部 state（筛选/展开/滚动位置）不丢，自管 fetch 不重复请求。
  const [visitedTabs, setVisitedTabs] = useState<string[]>(() => {
    const hash = window.location.hash.replace('#', '');
    return [VALID_TABS.includes(hash) ? hash : 'dashboard'];
  });

  React.useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (VALID_TABS.includes(hash)) {
        setActiveTab(hash);
        setVisitedTabs((prev) => (prev.includes(hash) ? prev : [...prev, hash]));
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeTab = useCallback((tab: string) => {
    setActiveTab(tab);
    setVisitedTabs((prev) => (prev.includes(tab) ? prev : [...prev, tab]));
    if (window.location.hash.replace('#', '') !== tab) {
      window.history.replaceState(null, '', `#${tab}`);
    }
  }, []);

  // 后台主题：与前台 useTheme 完全一致的解析顺序。
  //
  // 原实现从未选过主题时无条件 'dark' —— 走查实测「聊天亮色 → 进后台
  // 突然全暗」的主题跳变。现在三档与前台一致：
  //   - 已存偏好（light/dark）→ 用它；
  //   - 存的是 system / 从未选过 → 跟随系统偏好。
  // 只挂载时应用一次：之后由 ThemeToggle 直接改 DOM，effect 不再覆盖它。
  React.useEffect(() => {
    const root = document.documentElement;
    let stored: string | null = null;
    try {
      stored = localStorage.getItem('agenticos-theme');
    } catch {
      stored = null;
    }
    const resolved =
      stored === 'light' || stored === 'dark'
        ? stored
        : window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
    root.classList.remove('light', 'dark');
    root.classList.add(resolved);

    return () => {
      // 离开后台时恢复用户真实主题偏好（'system' 也要解析，否则系统浅色的
      // 用户会被永久卡在暗色）。
      const next =
        stored === 'light' || stored === 'dark'
          ? stored
          : window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark'
            : 'light';
      root.classList.remove('light', 'dark');
      root.classList.add(next);
    };
  }, []);

  const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth >= 1024);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);
  const [timeRange, setTimeRange] = useState(14);

  const dashboardQuery = useQuery({
    queryKey: ['admin', 'dashboard', timeRange],
    queryFn: () => getDashboardStats(timeRange),
    enabled: activeTab === 'dashboard',
  });

  const dashboardData = dashboardQuery.data ?? null;
  const isDashboardLoading = dashboardQuery.isFetching;
  const dashboardError = dashboardQuery.isError
    ? (dashboardQuery.error as Error).message || '仪表盘数据加载失败'
    : null;

  // 用量路由审计：与主看板共用时间范围，但单独请求 —— 它是排障视图，
  // 取数失败不该让整个看板变成错误页。
  const usageRouteQuery = useQuery({
    queryKey: ['admin', 'usage-routes', timeRange],
    queryFn: () => getUsageRoutes(timeRange),
    enabled: activeTab === 'dashboard',
  });

  React.useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      setIsSidebarOpen(!mobile);
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 移动端侧栏打开时锁定背景滚动
  React.useEffect(() => {
    if (!isMobile || !isSidebarOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isMobile, isSidebarOpen]);

  const renderTab = (tab: string) => {
    switch (tab) {
      case 'dashboard':
        return (
          <div className="admin-page-stage space-y-5">
            {/* Overview header */}
            <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
                    系统总览
                  </p>
                  <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-[var(--foreground)] lg:text-3xl">
                    后台数据看板
                  </h1>
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <div
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--muted-foreground)] shadow-sm"
                    role="status"
                    aria-live="polite"
                  >
                    {isDashboardLoading ? '正在同步数据' : '数据已同步'}
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => void dashboardQuery.refetch()}
                    disabled={isDashboardLoading}
                    className="gap-1.5"
                    size="sm"
                  >
                    {isDashboardLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <RefreshCw size={14} />
                    )}
                    刷新
                  </Button>
                  <div
                    role="group"
                    aria-label="统计时间范围"
                    style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px' }}
                  >
                    {[7, 14, 30].map((d) => (
                      <button
                        key={d}
                        onClick={() => setTimeRange(d)}
                        aria-pressed={timeRange === d}
                        className={`rounded-lg px-2.5 py-1 font-medium transition-colors focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)] ${
                          timeRange === d ? 'bg-[var(--primary)] text-[var(--primary-foreground)]' : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
                        }`}
                      >
                        {d}天
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {/* KPI 指标统一由下方 DashboardStats 呈现，此处不再重复一排快捷卡片 */}
            </section>

            {dashboardError && (
              <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}

            {isDashboardLoading && !dashboardData ? (
              <div className="space-y-5">
                <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-sm">
                  <div className="mb-4 h-3 w-20 animate-pulse rounded bg-zinc-200" />
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {[0, 1, 2, 3].map((i) => (
                      <ChartSkeleton key={i} variant="stat" />
                    ))}
                  </div>
                </section>
                <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <ChartSkeleton key={i} variant="stat" />
                  ))}
                </section>
                <section className="grid gap-5 lg:grid-cols-2">
                  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-sm">
                    <ChartSkeleton variant="area" height={220} />
                  </div>
                  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-sm">
                    <ChartSkeleton variant="pie" height={220} />
                  </div>
                </section>
              </div>
            ) : dashboardData ? (
              <>
                <DashboardStats summary={dashboardData.summary} />
                <DashboardCharts data={dashboardData} />
                {usageRouteQuery.data && <UsageRoutePanel data={usageRouteQuery.data} />}
              </>
            ) : null}
          </div>
        );
      case 'history':
        return <ChatHistory />;
      case 'user_analytics':
        return <UserAnalytics />;
      case 'feedback':
        return <FeedbackCenter />;
      case 'approvals':
        return <ApprovalCenter />;
      case 'users':
        return <UserManagement />;
      case 'permissions':
        return <PermissionManagement />;
      case 'agents':
        return <AgentManagement />;
      case 'llm_providers':
        return <LlmProviderManagement />;
      case 'integrations':
        return <IntegrationManagement />;
      case 'api_keys':
        return <ApiKeyManagement />;
      case 'gateway':
        return <GatewayEndpointsPanel />;
      case 'task_queue':
        return <TaskQueueOps />;
      case 'app_platform':
        return <AppManagement />;
      case 'quota':
        return <QuotaManagement />;
      case 'skills':
        return <SkillManagement />;
      case 'tool_policy':
        return <AgentToolPolicyPanel />;
      case 'knowledge':
        return <KnowledgeManagement />;
      case 'website_deploys':
        return <WebsiteDeployManagement />;
      case 'announcements':
        return <AnnouncementManagement />;
      case 'settings':
        return <SystemSettings />;
      case 'memory':
        return <MemoryPanel />;
      case 'traces':
        return <TracePanel />;
      case 'evals':
        return <EvalPanel />;
      default:
        return (
          <div className="admin-page-stage flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-8 text-center">
            <ShieldAlert size={32} className="text-[var(--muted-foreground)]" />
            <p className="text-sm font-semibold text-[var(--foreground)]">暂无可用的管理面板</p>
            <p className="max-w-md text-xs text-[var(--muted-foreground)]">
              你的角色可进入后台，但没有可访问的面板权限。请联系管理员分配相应能力位。
            </p>
          </div>
        );
    }
  };

  return (
    <motion.div
      key="admin"
      /* 挂载即可见（initial=false）：整页可见性绝不依赖 motion 入场动画，
         否则懒加载 chunk + AnimatePresence(mode=wait) 竞态会把页面卡在 opacity:0（白屏）。
         入场动效由 .admin-page-stage 的 CSS 动画在内容层提供。 */
      initial={false}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={cn('admin-dashboard-shell relative flex h-full w-full overflow-hidden bg-transparent font-sans', 'text-[var(--foreground)]')}
    >
      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 z-10 bg-black/20 "
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {isSidebarOpen && (
          <AdminSidebar
            activeTab={activeTab}
            setActiveTab={changeTab}
            isMobile={isMobile}
            isOpen={isSidebarOpen}
            onClose={() => setIsSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!isSidebarOpen && !isMobile && (
          <motion.button
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            onClick={() => setIsSidebarOpen(true)}
            className="fixed left-4 top-4 z-40"
            aria-label="展开侧栏"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm transition-all hover:bg-[var(--surface-1)] hover:shadow-md">
              <MascotCool size={24} className="transition-transform hover:scale-110" />
            </div>
          </motion.button>
        )}
      </AnimatePresence>

      {!isSidebarOpen && isMobile && (
        <button
          type="button"
          onClick={() => setIsSidebarOpen(true)}
          aria-label="展开侧栏"
        >
          <div className="fixed left-4 top-4 z-40 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm">
            <MascotCool size={24} />
          </div>
        </button>
      )}

      <main id="main-content" className="relative z-10 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1540px] px-4 pb-10 pt-6 md:px-6 xl:px-8">
          {/* Tab keep-alive：已访问面板全部保持挂载，仅用 hidden 切换可见性。
              切回时不重新挂载 → 筛选/滚动状态保留、自管 fetch 不重复请求。
              hidden 属性配合 !hidden 工具类，避免内部 display 类覆盖。 */}
          {visitedTabs.map((tab) => (
            <div
              key={tab}
              hidden={tab !== activeTab}
              className="admin-page-stage [&[hidden]]:!hidden"
            >
              <Suspense fallback={<TabFallback />}>{renderTab(tab)}</Suspense>
            </div>
          ))}
        </div>
      </main>
    </motion.div>
  );
};
