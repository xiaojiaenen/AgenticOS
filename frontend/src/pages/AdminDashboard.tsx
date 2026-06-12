import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Activity, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AnnouncementManagement } from '../components/admin/AnnouncementManagement';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { IntegrationManagement } from '../components/admin/IntegrationManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { MemoryPanel } from '../components/settings/MemoryPanel';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { Button } from '../components/ui/Button';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { RandomMascot } from '../components/ui/RandomMascot';
import { cn, formatNumber, formatTokenNumber, formatLatency } from '../lib/utils';
import { DashboardStats as DashboardStatsData, getDashboardStats } from '../services/dashboardService';
import { useIsGlassTheme, Ferrofluid } from '../components/liquid-glass';


export const AdminDashboard = () => {
 const isGlass = useIsGlassTheme();
 const [activeTab, setActiveTab] = useState('dashboard');
 const [dashboardData, setDashboardData] = useState<DashboardStatsData | null>(null);
 const [dashboardError, setDashboardError] = useState<string | null>(null);
 const [isDashboardLoading, setIsDashboardLoading] = useState(false);
 const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth >= 1024);
 const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);
 const [timeRange, setTimeRange] = useState(14);
 const [autoRefresh, setAutoRefresh] = useState(false);

 const loadDashboard = React.useCallback(async () => {
  setIsDashboardLoading(true);
  setDashboardError(null);
  try {
   setDashboardData(await getDashboardStats(timeRange));
  } catch (err) {
   setDashboardError(err instanceof Error ? err.message : '仪表盘数据加载失败');
  } finally {
   setIsDashboardLoading(false);
  }
 }, [timeRange]);

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

 React.useEffect(() => {
  if (activeTab === 'dashboard' && !dashboardData) {
   loadDashboard();
  }
 }, [activeTab, loadDashboard, dashboardData]);

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
    value: formatTokenNumber(summary.total_sessions > 0 ? Math.round(summary.total_tokens / summary.total_sessions) : 0),
   },
  ];
 }, [dashboardData]);

 const renderContent = () => {
  switch (activeTab) {
   case 'dashboard':
    return (
     <div className="admin-page-stage space-y-5">
      {/* Overview header */}
      <section className={cn("rounded-lg p-5 shadow-md", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "border border-[var(--admin-card-border)] bg-[var(--admin-card-bg)]")}>
       <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
         <p className="admin-section-kicker">系统总览</p>
         <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-950 lg:text-3xl">后台数据看板</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
         <div className="admin-kpi-pill text-xs font-semibold">
          {isDashboardLoading ? '正在同步数据' : '数据已同步'}
         </div>
         <Button variant="secondary" onClick={loadDashboard} disabled={isDashboardLoading} className="gap-1.5" size="sm">
          {isDashboardLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          刷新
         </Button>
         <div className={cn("flex items-center gap-1 rounded-xl p-0.5 text-xs", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "bg-white border border-slate-200/80")}>
          {[7, 14, 30].map((d) => (
           <button
            key={d}
            onClick={() => setTimeRange(d)}
            className={`rounded-lg px-2.5 py-1 font-medium transition-colors ${timeRange === d ? "bg-[var(--admin-accent)] text-white" : "text-slate-500 hover:text-slate-700"}`}
           >
            {d}天
           </button>
          ))}
         </div>
        </div>
       </div>
       {/* Quick insights */}
       <div className="mt-4 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
        {headerInsights.map((item) => (
         <div key={item.label} className="admin-stat-card rounded-xl px-4 py-3">
          <p className="text-[11px] font-semibold tracking-[0.08em] text-slate-400">{item.label}</p>
          <p className="mt-1.5 text-lg font-semibold tracking-tight text-slate-950">{item.value}</p>
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
        <section className={cn("rounded-lg p-6 shadow-md", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "border border-slate-200/80 bg-[var(--admin-card-bg)]")}>
         <div className="h-3 w-20 animate-pulse rounded bg-slate-200 mb-4" />
         <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0,1,2,3].map(i => <ChartSkeleton key={i} variant="stat" />)}
         </div>
        </section>
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
         {[0,1,2,3,4].map(i => <ChartSkeleton key={i} variant="stat" />)}
        </section>
        <section className="grid gap-5 lg:grid-cols-2">
         <div className={cn("rounded-lg p-6 shadow-md", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "border border-slate-200/80 bg-[var(--admin-card-bg)]")}>
          <ChartSkeleton variant="area" height={220} />
         </div>
         <div className={cn("rounded-lg p-6 shadow-md", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "border border-slate-200/80 bg-[var(--admin-card-bg)]")}>
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
   case 'announcements':
    return <AnnouncementManagement />;
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
   className={cn(
     "admin-dashboard-shell relative flex h-screen overflow-hidden font-sans",
     isGlass ? "text-white" : "text-slate-800"
   )}
   style={{
     background: isGlass ? '#000000' : undefined,
   }}
  >
   <div className="admin-dashboard-backdrop pointer-events-none">
    {isGlass ? (
      <Ferrofluid
        colors={['#1a1a2e', '#16213e', '#0f3460']}
        speed={0.3}
        scale={1.2}
        turbulence={0.8}
        fluidity={0.15}
        rimWidth={0.15}
        sharpness={2}
        shimmer={1}
        glow={1.5}
        flowDirection="down"
        opacity={0.6}
        mouseInteraction={true}
        mouseStrength={0.8}
        mouseRadius={0.3}
        mouseDampening={0.2}
      />
    ) : (
      <>
        {/* Animated blobs — professional, deeper tones */}
        {/* blob removed */}
        {/* blob removed */}
        {/* blob removed */}

        {/* mascot removed */}
        {/* mascot removed */}
      </>
    )}
   </div>

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
      className={cn("fixed left-4 top-4 z-40 flex h-12 w-12 items-center justify-center rounded-lg text-zinc-800 shadow-sm transition-all hover:shadow-md", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm hover:bg-white/12" : "bg-white border border-slate-200/80 hover:bg-white")}
      aria-label="展开侧栏"
     >
      <MascotCool size={24} className="transition-transform hover:scale-110" />
     </motion.button>
    )}
   </AnimatePresence>

   {!isSidebarOpen && isMobile && (
    <button
     type="button"
     onClick={() => setIsSidebarOpen(true)}
     className={cn("fixed left-4 top-4 z-40 flex h-12 w-12 items-center justify-center rounded-lg text-zinc-800 shadow-sm", isGlass ? "bg-white/8 border border-white/15 backdrop-blur-sm" : "bg-white border border-slate-200/80")}
     aria-label="展开侧栏"
    >
     <MascotCool size={24} />
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
