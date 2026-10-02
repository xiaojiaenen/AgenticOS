import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AnnouncementManagement } from '../components/admin/AnnouncementManagement';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats, STATIC_CARD } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { KnowledgeManagement } from '../components/admin/KnowledgeManagement';
import { WebsiteDeployManagement } from '../components/admin/WebsiteDeployManagement';
import { UpstreamManagement } from '../components/admin/UpstreamManagement';
import { SystemSettings } from '../components/admin/SystemSettings';
import { IntegrationManagement } from '../components/admin/IntegrationManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { MemoryPanel } from '../components/settings/MemoryPanel';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { Button } from '@/components/shadcn/button';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { cn, formatNumber, formatTokenNumber } from '../lib/utils';
import { getDashboardStats } from '../services/dashboardService';

export const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  // Admin uses the dark theme while mounted
  React.useEffect(() => {
    const root = document.documentElement;
    root.classList.add('dark');
    return () => {
      // If user had dark mode, keep it; otherwise remove dark
      const stored = localStorage.getItem('agenticos-theme');
      if (stored !== 'dark' && stored !== 'system') {
        root.classList.remove('dark');
      }
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

  const headerInsights = useMemo(() => {
    const summary = dashboardData?.summary;
    if (!summary) {
      return [
        { label: '模型调用', value: '--' },
        { label: '总运行', value: '--' },
        { label: '总用户', value: '--' },
        { label: '单会话 Token', value: '--' },
      ];
    }

    return [
      {
        label: '模型调用',
        value: formatNumber(summary.llm_calls),
      },
      {
        label: '总运行',
        value: formatNumber(summary.total_runs),
      },
      {
        label: '总用户',
        value: formatNumber(summary.total_users),
      },
      {
        label: '单会话 Token',
        value: formatTokenNumber(
          summary.total_sessions > 0 ? Math.round(summary.total_tokens / summary.total_sessions) : 0,
        ),
      },
    ];
  }, [dashboardData]);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <div className="admin-page-stage space-y-5">
            {/* Overview header */}
            <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-700">
                    系统总览
                  </p>
                  <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-[var(--foreground)] lg:text-3xl">
                    后台数据看板
                  </h1>
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--muted-foreground)] shadow-sm">
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px' }}>
                    {[7, 14, 30].map((d) => (
                      <button
                        key={d}
                        onClick={() => setTimeRange(d)}
                        className={`rounded-lg px-2.5 py-1 font-medium transition-colors ${
                          timeRange === d ? 'bg-zinc-900 text-white' : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
                        }`}
                      >
                        {d}天
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {/* Quick insights —— 与下方 KPI 卡片共用 STATIC_CARD，保持两排视觉一致 */}
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {headerInsights.map((item) => (
                  <div key={item.label} className={STATIC_CARD}>
                    <span className="admin-muted text-[11px] font-semibold tracking-[0.08em]">{item.label}</span>
                    <p className="admin-heading mt-2.5 text-xl font-semibold tracking-tight lg:text-2xl">{item.value}</p>
                  </div>
                ))}
              </div>
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
              </>
            ) : null}
          </div>
        );
      case 'history':
        return <ChatHistory />;
      case 'users':
        return <UserManagement />;
      case 'agents':
        return <AgentManagement />;
      case 'integrations':
        return <IntegrationManagement />;
      case 'skills':
        return <SkillManagement />;
      case 'knowledge':
        return <KnowledgeManagement />;
      case 'website_deploys':
        return <WebsiteDeployManagement />;
      case 'upstream':
        return <UpstreamManagement />;
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
            setActiveTab={setActiveTab}
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
