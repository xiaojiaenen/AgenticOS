import React, { useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SystemSettings } from '../components/admin/SystemSettings';
import { UserManagement } from '../components/admin/UserManagement';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { getStoredUser } from '../services/authService';
import { DashboardStats as DashboardStatsData, getDashboardStats } from '../services/dashboardService';

export const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardData, setDashboardData] = useState<DashboardStatsData | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [isDashboardLoading, setIsDashboardLoading] = useState(false);
  const user = getStoredUser();

  const tabTitle: Record<string, string> = {
    dashboard: '系统概览',
    history: '对话记录',
    users: '用户管理',
    agents: '智能体配置',
    settings: '工具管理',
  };

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
    if (activeTab === 'dashboard') {
      loadDashboard();
    }
  }, [activeTab, loadDashboard]);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <div className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.25em] text-slate-500">Dashboard</p>
                <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-900">系统概览</h2>
              </div>
              <Button variant="secondary" onClick={loadDashboard} disabled={isDashboardLoading} className="gap-2 self-start md:self-auto">
                {isDashboardLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                刷新数据
              </Button>
            </div>
            {dashboardError && (
              <div className="flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}
            {isDashboardLoading && !dashboardData ? (
              <div className="flex h-80 items-center justify-center gap-3 rounded-[28px] border border-white/60 bg-white/45 text-sm font-bold text-slate-500 backdrop-blur-2xl">
                <Loader2 size={18} className="animate-spin" />
                正在汇总统计数据
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
      case 'settings':
        return <SystemSettings />;
      default:
        return null;
    }
  };

  return (
    <div className="relative flex h-screen overflow-hidden bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] font-sans text-slate-800 selection:bg-zinc-200 selection:text-zinc-900">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <RandomMascot size={700} className="absolute -bottom-40 -right-36 text-slate-900 opacity-[0.025]" />
        <div className="absolute bottom-[-20%] left-[-10%] h-[70vw] w-[70vw] rounded-full bg-teal-300 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] h-[80vw] w-[80vw] rounded-full bg-blue-400 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute left-[30%] top-[10%] h-[50vw] w-[50vw] rounded-full bg-cyan-300 opacity-25 mix-blend-overlay blur-[120px]" />
      </div>

      <AdminSidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      <div className="custom-scrollbar relative z-10 flex-1 overflow-auto">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-white/50 bg-white/55 px-6 py-4 shadow-sm backdrop-blur-2xl lg:px-10">
          <h1 className="text-xl font-black tracking-tight text-slate-900">{tabTitle[activeTab]}</h1>
          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <p className="text-xs font-black text-slate-700">{user?.name || 'Admin'}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Workspace</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border-2 border-white bg-zinc-900 text-white shadow-md">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl p-5 md:p-8 lg:p-10">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            {renderContent()}
          </motion.div>
        </main>
      </div>
    </div>
  );
};
