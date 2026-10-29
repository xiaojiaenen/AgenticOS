import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AnnouncementManagement } from '../components/admin/AnnouncementManagement';
import { AgentManagement } from '../components/admin/AgentManagement';
import { LlmProviderManagement } from '../components/admin/LlmProviderManagement';
import { ApiKeyManagement } from '../components/admin/ApiKeyManagement';
import { GatewayEndpointsPanel } from '../components/admin/GatewayEndpointsPanel';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { UsageRoutePanel } from '../components/admin/UsageRoutePanel';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { KnowledgeManagement } from '../components/admin/KnowledgeManagement';
import { WebsiteDeployManagement } from '../components/admin/WebsiteDeployManagement';
import { SystemSettings } from '../components/admin/SystemSettings';
import { IntegrationManagement } from '../components/admin/IntegrationManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { MemoryPanel } from '../components/settings/MemoryPanel';
import { PermissionManagement } from '../components/admin/PermissionManagement';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { Button } from '@/components/shadcn/button';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';
import { getDashboardStats, getUsageRoutes } from '../services/dashboardService';

export const AdminDashboard = () => {
  const VALID_TABS = ['dashboard', 'history', 'users', 'permissions', 'agents', 'llm_providers', 'integrations', 'api_keys', 'gateway', 'skills', 'knowledge', 'website_deploys', 'announcements', 'settings', 'memory'];
  // tab 与 URL hash 双向同步：刷新 / 分享链接不丢失当前管理页
  const [activeTab, setActiveTab] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    return VALID_TABS.includes(hash) ? hash : 'dashboard';
  });

  React.useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (VALID_TABS.includes(hash)) setActiveTab(hash);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeTab = useCallback((tab: string) => {
    setActiveTab(tab);
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

  const renderContent = () => {
    switch (activeTab) {
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
      case 'skills':
        return <SkillManagement />;
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
      default:
        return null;
    }
  };

  return (
    <motion.div
      key="admin"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={cn('admin-dashboard-shell relative flex h-screen overflow-hidden font-sans', 'text-[var(--foreground)]')}
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
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </motion.div>
  );
};
