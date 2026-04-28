import React, { useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, ArrowUpRight, Loader2, RefreshCw } from 'lucide-react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { AgentManagement } from '../components/admin/AgentManagement';
import { ChatHistory } from '../components/admin/ChatHistory';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { DashboardStats } from '../components/admin/DashboardStats';
import { SkillManagement } from '../components/admin/SkillManagement';
import { UserManagement } from '../components/admin/UserManagement';
import { Button } from '../components/ui/Button';
import { DashboardStats as DashboardStatsData, getDashboardStats } from '../services/dashboardService';

export const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardData, setDashboardData] = useState<DashboardStatsData | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [isDashboardLoading, setIsDashboardLoading] = useState(false);

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
          <div className="space-y-5">
            <section className="rounded-[42px] border border-white/60 bg-white/52 px-6 py-6 shadow-[0_24px_70px_rgba(15,23,42,0.08)] ring-1 ring-white/35 backdrop-blur-[26px] lg:px-8">
              <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
                <div className="max-w-3xl">
                  <p className="admin-section-kicker">后台管理</p>
                  <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950 lg:text-4xl">
                    抛弃常规侧栏和卡片堆砌，回到连续工作区
                  </h2>
                  <p className="mt-3 text-sm font-medium leading-7 text-slate-500 lg:text-[15px]">
                    管理后台变成一张连续展开的工作台：左侧由小精灵悬浮导航唤起，内容区保持列表与面板的连续流，不再被一格一格卡片打断。
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="rounded-full border border-white/80 bg-white/76 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-slate-500">
                    Hover Nav
                  </div>
                  <div className="rounded-full border border-white/80 bg-white/76 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-slate-500">
                    List First
                  </div>
                  <Button variant="secondary" onClick={loadDashboard} disabled={isDashboardLoading} className="gap-2">
                    {isDashboardLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                    刷新数据
                  </Button>
                </div>
              </div>

              <div className="mt-6 grid gap-3 lg:grid-cols-3">
                {[
                  '导航由小精灵 logo 触发，悬停后半圆展开，降低页面占用面积。',
                  '主页面以列表和连续面板为主，不再依赖卡片拼贴来组织信息。',
                  '工具、审批与 Skill 绑定继续集中在智能体配置弹窗里完成。',
                ].map((item) => (
                  <div
                    key={item}
                    className="rounded-[28px] border border-white/75 bg-white/68 px-4 py-4 text-sm font-semibold leading-6 text-slate-600"
                  >
                    <div className="flex items-start gap-3">
                      <span className="mt-1 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-slate-900 text-white">
                        <ArrowUpRight size={13} />
                      </span>
                      <span>{item}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {dashboardError && (
              <div className="flex items-center gap-2 rounded-[26px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                <AlertCircle size={18} />
                {dashboardError}
              </div>
            )}

            {isDashboardLoading && !dashboardData ? (
              <div className="flex h-80 items-center justify-center gap-3 rounded-[36px] border border-white/60 bg-white/45 text-sm font-bold text-slate-500 shadow-[0_24px_70px_rgba(15,23,42,0.08)] ring-1 ring-white/35 backdrop-blur-[26px]">
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
    <div className="relative min-h-screen overflow-hidden text-slate-800 selection:bg-sky-200 selection:text-slate-900">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="admin-shell-grid absolute inset-0 opacity-50" />
        <div className="absolute left-[-10%] top-[-12%] h-[34rem] w-[34rem] rounded-full bg-cyan-200/48 blur-[120px]" />
        <div className="absolute right-[-8%] top-[4%] h-[32rem] w-[32rem] rounded-full bg-sky-100/76 blur-[120px]" />
        <div className="absolute bottom-[-16%] right-[8%] h-[38rem] w-[38rem] rounded-full bg-emerald-100/72 blur-[140px]" />
        <div className="absolute left-[34%] top-[24%] h-[26rem] w-[26rem] rounded-full bg-white/40 blur-[120px]" />
      </div>

      <AdminSidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="relative z-10 mx-auto min-h-screen w-full max-w-[1700px] px-4 pb-6 pt-5 lg:px-6 lg:pb-8 lg:pl-[7.5rem]">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        >
          {renderContent()}
        </motion.div>
      </main>
    </div>
  );
};
