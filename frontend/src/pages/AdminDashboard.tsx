import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Activity, AlertCircle, Gauge, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AnnouncementManagement } from '../components/admin/AnnouncementManagement';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { ChartSkeleton } from '../components/ui/ChartSkeleton';
import { Button } from '../components/ui/Button';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { RandomMascot } from '../components/ui/RandomMascot';
import { cn, formatNumber, formatTokenNumber, formatLatency } from '../lib/utils';
import { DashboardStats as DashboardStatsData, getDashboardStats } from '../services/dashboardService';


export const AdminDashboard = () => {
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

  const topSummary = useMemo(() => {
    const summary = dashboardData?.summary;

    return [
      {
        label: '总 Token',
        value: formatTokenNumber(summary?.total_tokens),
        meta: summary ? `${formatNumber(summary?.total_sessions || 0)} 个会话累计产生` : '平台内容总负载',
        tone: 'bg-[linear-gradient(135deg,rgba(56,189,248,0.2),rgba(255,255,255,0.72),rgba(14,165,233,0.08))]',
        icon: Gauge,
      },
      {
        label: '输入 Token',
        value: formatTokenNumber(summary?.input_tokens),
        meta: summary ? `${Math.round((summary.input_tokens / Math.max(summary.total_tokens, 1)) * 100)}% 输入占比` : '用户输入内容沉淀',
        tone: 'bg-[linear-gradient(135deg,rgba(74,222,128,0.2),rgba(255,255,255,0.72),rgba(45,212,191,0.08))]',
        icon: Activity,
      },
      {
        label: '输出 Token',
        value: formatTokenNumber(summary?.output_tokens),
        meta: summary ? `${Math.round((summary.output_tokens / Math.max(summary.total_tokens, 1)) * 100)}% 输出占比` : '模型输出内容沉淀',
        tone: 'bg-[linear-gradient(135deg,rgba(196,181,253,0.26),rgba(255,255,255,0.72),rgba(244,114,182,0.08))]',
        icon: Sparkles,
      },
      {
        label: '总运行',
        value: formatNumber(summary?.total_runs),
        meta: summary ? `${formatNumber(summary.llm_calls)} 次模型调用` : '观察执行总规模',
        tone: 'bg-[linear-gradient(135deg,rgba(251,191,36,0.24),rgba(255,255,255,0.72),rgba(34,197,94,0.08))]',
        icon: Activity,
      },
    ];
  }, [dashboardData]);

  const sideSummary = useMemo(() => {
    const summary = dashboardData?.summary;
    return [
      {
        label: '总用户',
        value: formatNumber(summary?.total_users),
        meta: '平台累计用户规模',
      },
      {
        label: '总会话',
        value: formatNumber(summary?.total_sessions),
        meta: '会话沉淀总量',
      },
      {
        label: '活跃用户',
        value: formatNumber(summary?.active_users),
        meta: '当前活跃账号数量',
      },
      {
        label: '总运行',
        value: formatNumber(summary?.total_runs),
        meta: '全局执行次数',
      },
      {
        label: '平均耗时',
        value: formatLatency(summary?.avg_latency_ms),
        meta: '按单次运行统计',
      },
      {
        label: '模型调用',
        value: formatNumber(summary?.llm_calls),
        meta: '全局推理触发次数',
      },
    ];
  }, [dashboardData]);

  const headerInsights = useMemo(() => {
    const summary = dashboardData?.summary;
    if (!summary) {
      return [
        { label: '输出占比', value: '--' },
        { label: '每用户会话', value: '--' },
        { label: '每次运行工具', value: '--' },
        { label: '输入 Token', value: '--' },
      ];
    }

    return [
      {
        label: '输出占比',
        value: `${Math.round((summary.output_tokens / Math.max(summary.total_tokens, 1)) * 100)}%`,
      },
      {
        label: '每用户会话',
        value: (summary.total_sessions / Math.max(summary.total_users, 1)).toFixed(1),
      },
      {
        label: '每次运行工具',
        value: (summary.tool_calls / Math.max(summary.total_runs, 1)).toFixed(2),
      },
      {
        label: '输入 Token',
        value: formatTokenNumber(summary.input_tokens),
      },
    ];
  }, [dashboardData]);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <div className="admin-page-stage space-y-5">
            {/* Top row: overview + key metrics — semi-transparent tinted cards */}
            <section className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_400px]">
              <div className="rounded-2xl border border-white/50 bg-[linear-gradient(135deg,rgba(255,255,255,0.62),rgba(255,255,255,0.38),rgba(186,230,253,0.34))] p-5 shadow-md">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="max-w-3xl">
                    <p className="admin-section-kicker">系统总览</p>
                    <h1 className="mt-1.5 text-2xl font-black tracking-tight text-slate-950 lg:text-3xl">后台数据看板</h1>
                    <div className="mt-3 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
                      {headerInsights.map((item) => (
                        <div key={item.label} className="admin-stat-card rounded-xl px-4 py-3">
                          <p className="text-[11px] font-black tracking-[0.14em] text-slate-400">{item.label}</p>
                          <p className="mt-1.5 text-lg font-black tracking-tight text-slate-950">{item.value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2.5">
                    <div className="admin-kpi-pill text-xs font-black">
                      {isDashboardLoading ? '正在同步数据' : '数据已同步'}
                    </div>
                    <Button variant="secondary" onClick={loadDashboard} disabled={isDashboardLoading} className="gap-1.5" size="sm">
                      {isDashboardLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                      刷新
                    </Button>
                    <div className="flex items-center gap-1 rounded-xl border border-slate-200/80 bg-white/80 p-0.5 text-xs">
                      {[7, 14, 30].map((d) => (
                        <button
                          key={d}
                          onClick={() => setTimeRange(d)}
                          className={`rounded-lg px-2.5 py-1 font-bold transition-colors ${timeRange === d ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-700"}`}
                        >
                          {d}天
                        </button>
                      ))}
                    </div>
                    <button
                      onClick={() => setAutoRefresh(!autoRefresh)}
                      className={`rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors ${autoRefresh ? "bg-emerald-100 text-emerald-700" : "text-slate-400 hover:text-slate-600"}`}
                      title={autoRefresh ? "关闭自动刷新" : "开启自动刷新（30秒）"}
                    >
                      {autoRefresh ? "自动: 开" : "自动: 关"}
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                  {topSummary.map((item) => (
                    <div key={item.label} className={`admin-stat-card px-4 py-4 ${item.tone}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-black tracking-[0.16em] text-slate-500">{item.label}</span>
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/70 bg-white/65 text-slate-900 shadow-sm transition-transform duration-300 group-hover:scale-110">
                          <item.icon size={18} />
                        </div>
                      </div>
                      <p className="mt-3 text-2xl font-black tracking-tight text-slate-950">{item.value}</p>
                      <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">{item.meta}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-white/50 bg-[linear-gradient(135deg,rgba(255,255,255,0.58),rgba(233,213,255,0.28),rgba(255,255,255,0.36))] p-5 shadow-md">
                <p className="admin-section-kicker">关键刻度</p>
                <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
                  {sideSummary.map((item, index) => (
                    <div
                      key={item.label}
                      className={cn(
                        'admin-stat-card rounded-xl px-4 py-3.5',
                        index === 0 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(56,189,248,0.12))]',
                        index === 1 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(125,211,252,0.12))]',
                        index === 2 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(244,114,182,0.10))]',
                        index === 3 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(196,181,253,0.12))]',
                        index === 4 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(251,191,36,0.10))]',
                        index === 5 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(16,185,129,0.10))]',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-slate-500">{item.label}</span>
                        <span className="text-lg font-bold tracking-tight text-slate-950">{item.value}</span>
                      </div>
                      <p className="mt-1 text-xs font-medium text-slate-500">{item.meta}</p>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {dashboardError && (
              <div className="flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}

            {isDashboardLoading && !dashboardData ? (
              <div className="space-y-5">
                <section className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_400px]">
                  <div className="rounded-2xl border border-white/60 bg-white/50 p-6 shadow-xl backdrop-blur-2xl">
                    <div className="h-3 w-20 animate-pulse rounded bg-slate-200 mb-4" />
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {[0,1,2,3].map(i => <ChartSkeleton key={i} variant="stat" />)}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/60 bg-white/50 p-6 shadow-xl backdrop-blur-2xl">
                    <ChartSkeleton variant="stat" />
                  </div>
                </section>
                <section className="grid gap-5 lg:grid-cols-2">
                  <div className="rounded-2xl border border-white/60 bg-white/50 p-6 shadow-xl backdrop-blur-2xl">
                    <ChartSkeleton variant="area" height={220} />
                  </div>
                  <div className="rounded-2xl border border-white/60 bg-white/50 p-6 shadow-xl backdrop-blur-2xl">
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
      case 'skills':
        return <SkillManagement />;
      case 'announcements':
        return <AnnouncementManagement />;
      default:
        return null;
    }
  };

  return (
    <motion.div
      key="admin"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="admin-dashboard-shell relative flex h-screen overflow-hidden font-sans text-slate-800 selection:bg-zinc-200 selection:text-zinc-900"
    >
      <div className="admin-dashboard-backdrop pointer-events-none">
        {/* Animated blobs — professional, deeper tones */}
        <div className="absolute -top-20 -left-10 w-[550px] h-[550px] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.15),transparent_70%)] blur-[80px] animate-[bg-blob-1_16s_ease-in-out_infinite]" />
        <div className="absolute top-1/4 -right-8 w-[460px] h-[460px] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.12),transparent_70%)] blur-[70px] animate-[bg-blob-2_18s_ease-in-out_infinite]" />
        <div className="absolute -bottom-12 left-1/3 w-[480px] h-[480px] rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.13),transparent_70%)] blur-[80px] animate-[bg-blob-3_17s_ease-in-out_infinite]" />

        <RandomMascot size={760} className="admin-backdrop-mascot admin-backdrop-mascot-primary" />
        <RandomMascot size={360} className="admin-backdrop-mascot admin-backdrop-mascot-secondary" />
      </div>

      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 z-10 bg-white/30"
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
            className="fixed left-4 top-4 z-40 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/60 bg-white/80 text-zinc-800 shadow-sm backdrop-blur-md transition-all hover:bg-white hover:shadow-md"
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
          className="fixed left-4 top-4 z-40 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/60 bg-white/80 text-zinc-800 shadow-sm backdrop-blur-md"
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
