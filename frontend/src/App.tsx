import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalAnnouncementLayer } from './components/announcement/GlobalAnnouncementLayer';
import { FeedbackLauncher } from './components/feedback/FeedbackLauncher';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { Toaster } from '@/components/shadcn/sonner';
import { Island, IslandProvider } from '@/lib/island';
import {
  AgentRunIsland,
  AgentRunErrorIsland,
  AgentRunDoneIsland,
} from '@/features/island/AgentRunIsland';
import { ContextCompressedIsland } from '@/features/island/ContextCompressedIsland';
import { DraftTypingIsland } from '@/features/island/DraftTypingIsland';
import { IdleClockIsland } from '@/features/island/IdleClockIsland';
import { PptExportIsland } from '@/features/island/PptExportIsland';
import { FileUploadIsland } from '@/features/island/FileUploadIsland';
import { SiteDeployIsland } from '@/features/island/SiteDeployIsland';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { AppShell } from './components/layout/AppShell';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  },
});

const Home = lazy(() => import('./pages/Home').then((module) => ({ default: module.Home })));
const Chat = lazy(() => import('./pages/Chat').then((module) => ({ default: module.Chat })));
const AgentStore = lazy(() => import('./pages/AgentStore').then((module) => ({ default: module.AgentStore })));
const AgentEditor = lazy(() => import('./pages/AgentEditor').then((module) => ({ default: module.AgentEditor })));
const Login = lazy(() => import('./pages/Login').then((module) => ({ default: module.Login })));
const Signup = lazy(() => import('./pages/Signup').then((module) => ({ default: module.Signup })));
const Gallery = lazy(() => import('./pages/Gallery').then((module) => ({ default: module.GalleryPage })));
const Wrapped = lazy(() => import('./pages/Wrapped').then((module) => ({ default: module.Wrapped })));
const Feedback = lazy(() => import('./pages/Feedback').then((module) => ({ default: module.Feedback })));
const AdminDashboard = lazy(() =>
  import('./pages/AdminDashboard').then((module) => ({ default: module.AdminDashboard })),
);
// 公开发布的智能体聊天页（无需登录，嵌入 widget 指向这里）
const PublicAgentChat = lazy(() =>
  import('./pages/PublicAgentChat').then((module) => ({ default: module.PublicAgentChat })),
);
const CreativeCanvas = lazy(() =>
  import('./pages/CreativeCanvas').then((module) => ({ default: module.CreativeCanvas })),
);

const LoadingPage = () => (
  <div className="relative flex h-screen w-full flex-col items-center justify-center gap-4 overflow-hidden bg-[var(--background)]">
    <div className="aos-ambient-bg" aria-hidden="true" />
    <div className="aos-ambient-dots" aria-hidden="true" />
    <div className="aos-glass-surface relative z-10 flex flex-col items-center gap-3.5 rounded-3xl px-8 py-7">
      <svg className="h-11 w-11 animate-spin text-[var(--primary)]" viewBox="0 0 44 44" fill="none" aria-hidden="true">
        <circle cx="22" cy="22" r="18" stroke="currentColor" strokeOpacity="0.18" strokeWidth="3.5" />
        <path d="M22 4a18 18 0 0 1 18 18" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
      <p className="text-xs font-semibold tracking-wide text-[var(--muted-foreground)]">正在加载工作台...</p>
    </div>
  </div>
);

const NotFoundPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10 }}
    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    className="relative flex h-screen flex-col items-center justify-center overflow-hidden bg-[var(--background)] px-6 text-center"
  >
    <div className="aos-ambient-bg" aria-hidden="true" />
    <div className="aos-ambient-dots" aria-hidden="true" />
    <div className="aos-glass-surface relative z-10 flex max-w-md flex-col items-center gap-4 rounded-3xl px-10 py-10">
      <p className="bg-gradient-to-br from-[var(--primary)] to-violet-500 bg-clip-text text-7xl font-bold tracking-tight text-transparent">
        404
      </p>
      <div className="space-y-1.5">
        <p className="text-lg font-semibold text-[var(--foreground)]">页面未找到</p>
        <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
          这个地址可能已经失效，或者链接输入有误。
        </p>
      </div>
      <Link
        to="/"
        className="mt-1 inline-flex items-center gap-1.5 rounded-2xl bg-[var(--primary)] px-5 py-2.5 text-sm font-semibold text-[var(--primary-foreground)] shadow-md transition-all hover:opacity-90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
      >
        返回首页
      </Link>
    </div>
  </motion.div>
);

const AnimatedRoutes = () => {
  const location = useLocation();

  return (
    <Suspense fallback={<LoadingPage />}>
      <AnimatePresence mode="wait">
        <Routes location={location}>
          {/* 统一持久化工作台外壳：左侧栏常驻不重载，仅右侧主内容随路由切换 */}
          <Route element={<AppShell />}>
            <Route path="/" element={<ErrorBoundary key={`home-${location.pathname}`} title="首页出错了"><Home /></ErrorBoundary>} />
            <Route path="/chat" element={<ProtectedRoute><ErrorBoundary key={`chat-${location.pathname}`} title="对话页出错了"><Chat /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/agents" element={<ProtectedRoute><ErrorBoundary key={`agents-${location.pathname}`} title="智能体商店出错了"><AgentStore /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/agents/new" element={<ProtectedRoute><ErrorBoundary key={`agent-new-${location.pathname}`} title="智能体编辑器出错了"><AgentEditor /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/agents/:profileId/edit" element={<ProtectedRoute><ErrorBoundary key={`agent-edit-${location.pathname}`} title="智能体编辑器出错了"><AgentEditor /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/canvas" element={<ProtectedRoute><ErrorBoundary key={`canvas-${location.pathname}`} title="创作画布出错了"><CreativeCanvas /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/gallery" element={<ProtectedRoute><ErrorBoundary key={`gallery-${location.pathname}`} title="作品库出错了"><Gallery /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/feedback" element={<ProtectedRoute><ErrorBoundary key="feedback" title="反馈页出错了"><Feedback /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute requireAdmin><ErrorBoundary key={`admin-${location.pathname}`} title="管理后台出错了"><AdminDashboard /></ErrorBoundary></ProtectedRoute>} />
          </Route>

          {/* 独立全屏页面（认证、年度报告、公开应用、404） */}
          <Route path="/login" element={<ErrorBoundary key={`login-${location.pathname}`} title="登录页出错了"><Login /></ErrorBoundary>} />
          <Route path="/signup" element={<ErrorBoundary key={`signup-${location.pathname}`} title="注册页出错了"><Signup /></ErrorBoundary>} />
          <Route path="/wrapped" element={<ProtectedRoute><ErrorBoundary key="wrapped" title="年度报告出错了"><Wrapped /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/wrapped/:year" element={<ProtectedRoute><ErrorBoundary key={`wrapped-${location.pathname}`} title="年度报告出错了"><Wrapped /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/app/:slug" element={<ErrorBoundary key={`public-agent-${location.pathname}`} title="应用页出错了"><PublicAgentChat /></ErrorBoundary>} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AnimatePresence>
    </Suspense>
  );
};

function AppContent() {
  return (
    // IslandProvider 包住整个应用：它的状态（活动栈 + 时钟）必须在启动活动的
    // 组件之上。<Island placement="viewport" /> 钉在窗口顶部中央，
    // 有活动时展开成实时状态，空闲时是一条纯黑胶囊。
    <IslandProvider>
      <Island placement="viewport" />
      {/* 实时状态岛的活动源。全部按真实应用状态驱动，没有演示数据：
          - AgentRunIsland：AI 对话运行（思考/流式/生成 PPT/构建网站）
          - FileUploadIsland：文件上传（XHR 真实字节进度，多文件聚合）
          - PptExportIsland：PPTX 导出（实测 1–2 分钟，无进度回报）
          - ContextCompressedIsland：上下文压缩提醒（后端压缩发生的那一刻，
            展示真实摘要预览）
          - DraftTypingIsland：正在输入（输入框有草稿时，最长输入态不抢运行态）
          - IdleClockIsland：空闲常驻（时钟 + 时段问候），任何其它活动出现时让位 */}
      <IdleClockIsland />
      <AgentRunIsland />
      <AgentRunErrorIsland />
      <AgentRunDoneIsland />
      <ContextCompressedIsland />
      <DraftTypingIsland />
      <FileUploadIsland />
      <PptExportIsland />
      <SiteDeployIsland />
      <GlobalAnnouncementLayer />
      <ErrorBoundary>
        <AnimatedRoutes />
      </ErrorBoundary>
      <FeedbackLauncher />
      <Toaster />
    </IslandProvider>
  );
}

function App() {
  // ForesightJS：初始化意图预测（仅预取 chunk，无副作用）
  useEffect(() => {
    void import('./lib/foresight').then((m) => m.initForesight());
  }, []);
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

export default App;
