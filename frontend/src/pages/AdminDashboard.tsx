import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Activity, AlertCircle, Gauge, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { Button } from '../components/ui/Button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';
import { DashboardStats as DashboardStatsData, getDashboardStats } from '../services/dashboardService';

function formatNumber(value?: number): string {
  if (value === undefined || value === null) return '--';
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

function formatTokenNumber(value?: number): string {
  if (value === undefined || value === null) return '--';
  const abs = Math.abs(value);
  if (abs <= 10000) return `${value}`;
  if (abs >= 1e12) return `${(value / 1e12).toFixed(abs >= 1e13 ? 0 : 1)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(abs >= 1e10 ? 0 : 1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(abs >= 1e4 ? 0 : 1)}K`;
  return `${value}`;
}

function formatLatency(value?: number): string {
  if (!value) return '--';
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

export const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardData, setDashboardData] = useState<DashboardStatsData | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [isDashboardLoading, setIsDashboardLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth >= 1024);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);

  const loadDashboard = React.useCallback(async () => {
    setIsDashboardLoading(true);
    setDashboardError(null);
    try {
      setDashboardData(await getDashboardStats());
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : '仪表盘数据加载失败');
    } finally {
      setIsDashboardLoading(false);
    }
  }, []);

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
    if (activeTab === 'dashboard') {
      loadDashboard();
    }
  }, [activeTab, loadDashboard]);

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
            <section className="relative overflow-hidden rounded-[40px] border border-white/65 bg-white/42 shadow-[0_30px_90px_rgba(15,23,42,0.1)] ring-1 ring-white/35 backdrop-blur-[28px]">
              <div className="pointer-events-none absolute inset-0 overflow-hidden">
                <div className="absolute -left-12 top-0 h-56 w-56 rounded-full bg-cyan-300/30 blur-3xl" />
                <div className="absolute right-8 top-6 h-52 w-52 rounded-full bg-violet-300/22 blur-3xl" />
                <div className="absolute bottom-[-20%] left-[38%] h-56 w-56 rounded-full bg-emerald-300/18 blur-3xl" />
              </div>

              <div className="relative grid gap-4 px-5 py-5 xl:items-start xl:grid-cols-[minmax(0,1.35fr)_420px] xl:px-6">
                <div className="self-start rounded-[32px] border border-white/75 bg-[linear-gradient(135deg,rgba(255,255,255,0.76),rgba(255,255,255,0.4))] p-5 shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="max-w-3xl">
                      <p className="admin-section-kicker">系统总览</p>
                      <h2 className="mt-2.5 text-3xl font-black tracking-tight text-slate-950 lg:text-[2.45rem]">
                        后台数据看板
                      </h2>
                      <div className="mt-4 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
                        {headerInsights.map((item) => (
                          <div
                            key={item.label}
                            className="rounded-[20px] border border-white/75 bg-white/58 px-3.5 py-3 shadow-[0_10px_24px_rgba(15,23,42,0.05)]"
                          >
                            <p className="text-[11px] font-black tracking-[0.16em] text-slate-400">{item.label}</p>
                            <p className="mt-2 text-lg font-black tracking-tight text-slate-950">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="rounded-full border border-white/80 bg-white/72 px-4 py-2 text-xs font-black text-slate-500">
                        {isDashboardLoading ? '正在同步数据' : '数据已同步'}
                      </div>
                      <Button variant="secondary" onClick={loadDashboard} disabled={isDashboardLoading} className="gap-2">
                        {isDashboardLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                        刷新数据
                      </Button>
                    </div>
                  </div>

                  <div className="mt-5 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                    {topSummary.map((item) => (
                      <div
                        key={item.label}
                        className={`rounded-[24px] border border-white/75 px-4 py-3.5 shadow-[0_12px_28px_rgba(15,23,42,0.06)] ${item.tone}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-black tracking-[0.18em] text-slate-500">{item.label}</span>
                          <div className="flex h-9 w-9 items-center justify-center rounded-2xl border border-white/75 bg-white/55 text-slate-900">
                            <item.icon size={18} />
                          </div>
                        </div>
                        <p className="mt-2.5 text-3xl font-black tracking-tight text-slate-950">{item.value}</p>
                        <p className="mt-1.5 text-sm font-semibold leading-6 text-slate-600">{item.meta}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="self-start rounded-[32px] border border-white/75 bg-[linear-gradient(135deg,rgba(255,255,255,0.72),rgba(224,242,254,0.38),rgba(255,255,255,0.38))] p-4.5 shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
                  <p className="admin-section-kicker">关键刻度</p>
                  <div className="mt-3.5 grid gap-3 sm:grid-cols-2">
                    {sideSummary.map((item, index) => (
                      <div
                        key={item.label}
                        className={cn(
                          'rounded-[22px] border border-white/75 bg-white/58 px-4 py-3.5',
                          index === 0 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(56,189,248,0.12))]',
                          index === 1 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(125,211,252,0.12))]',
                          index === 2 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(244,114,182,0.1))]',
                          index === 3 && 'bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(196,181,253,0.12))]',
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-bold text-slate-500">{item.label}</span>
                          <span className="text-xl font-black tracking-tight text-slate-950">{item.value}</span>
                        </div>
                        <p className="mt-1.5 text-sm font-medium text-slate-600">{item.meta}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            {dashboardError && (
              <div className="flex items-center gap-2 rounded-[26px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}

            {isDashboardLoading && !dashboardData ? (
              <div className="flex h-80 items-center justify-center gap-3 rounded-[32px] border border-white/60 bg-white/50 text-sm font-bold text-slate-500 shadow-[0_24px_70px_rgba(15,23,42,0.08)] backdrop-blur-2xl">
                <Loader2 size={18} className="animate-spin" />
                正在汇总系统统计数据
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
      className="relative flex h-screen overflow-hidden bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] font-sans text-slate-800 selection:bg-zinc-200 selection:text-zinc-900"
    >
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute bottom-[-20%] left-[-10%] h-[70vw] w-[70vw] rounded-full bg-teal-300 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] h-[80vw] w-[80vw] rounded-full bg-blue-400 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute left-[30%] top-[10%] h-[50vw] w-[50vw] rounded-full bg-cyan-300 opacity-25 mix-blend-overlay blur-[120px]" />
        <RandomMascot size={460} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.025]" />
      </div>

      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 z-10 bg-slate-900/20 backdrop-blur-sm"
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

      <main className="relative z-10 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1540px] px-4 pb-10 pt-6 md:px-6 xl:px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 22, scale: 0.985, filter: 'blur(10px)' }}
              animate={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, y: -10, scale: 0.992, filter: 'blur(8px)' }}
              transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </motion.div>
  );
};
