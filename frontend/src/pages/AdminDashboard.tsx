import React, { useState } from 'react';
import { motion } from 'motion/react';
import { AdminSidebar } from '../components/admin/AdminSidebar';
import { DashboardStats } from '../components/admin/DashboardStats';
import { DashboardCharts } from '../components/admin/DashboardCharts';
import { ChatHistory } from '../components/admin/ChatHistory';
import { UserManagement } from '../components/admin/UserManagement';
import { ModelConfig } from '../components/admin/ModelConfig';
import { SystemSettings } from '../components/admin/SystemSettings';
import { RandomMascot } from '../components/ui/RandomMascot';

export const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <div className="space-y-6">
            <h2 className="text-2xl font-display font-bold text-slate-800 mb-6">系统概览 (Dashboard)</h2>
            <DashboardStats />
            <DashboardCharts />
          </div>
        );
      case 'history':
        return <ChatHistory />;
      case 'users':
        return <UserManagement />;
      case 'models':
        return <ModelConfig />;
      case 'settings':
        return <SystemSettings />;
      default:
        return null;
    }
  };

  return (
    <div className="h-screen bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] text-slate-800 font-sans flex relative overflow-hidden selection:bg-zinc-200 selection:text-zinc-900">
      {/* Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <RandomMascot size={500} className="absolute -bottom-32 -right-32 text-slate-900 opacity-[0.02]" />
        <div className="absolute top-[-10%] left-[-10%] w-[50vw] h-[50vw] bg-cyan-200 rounded-full mix-blend-overlay filter blur-[120px] opacity-30"></div>
        <div className="absolute bottom-[-20%] right-[-10%] w-[55vw] h-[55vw] bg-blue-200 rounded-full mix-blend-overlay filter blur-[120px] opacity-30"></div>
        {/* Noise Overlay */}
        <div className="absolute inset-0 opacity-[0.04] mix-blend-overlay" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.8%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E")' }}></div>
      </div>

      {/* Sidebar */}
      <AdminSidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content */}
      <div className="flex-1 overflow-auto relative z-10 custom-scrollbar">
        <header className="bg-white/80 backdrop-blur-md border-b border-slate-200 px-10 py-5 flex justify-between items-center sticky top-0 z-20 shadow-sm">
          <h1 className="text-xl font-display font-black text-slate-800 tracking-tight">
            {activeTab === 'dashboard' && '系统概览'}
            {activeTab === 'history' && '对话记录'}
            {activeTab === 'users' && '用户列表'}
            {activeTab === 'models' && '模型参数'}
            {activeTab === 'settings' && '工具管理'}
          </h1>
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-zinc-900 rounded-2xl flex items-center justify-center text-white border-2 border-white shadow-md">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
          </div>
        </header>
        <main className="p-10 max-w-7xl mx-auto">
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
