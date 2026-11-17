import { Suspense, lazy } from 'react';
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

const LoadingPage = () => (
  <div className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-[var(--surface-0)]">
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      className="h-8 w-8 rounded-full border-4 border-[var(--border-strong)] border-t-[var(--foreground)]"
    />
    <p className="text-sm font-medium text-[var(--muted-foreground)]">正在加载页面...</p>
  </div>
);

const NotFoundPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10 }}
    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    className="flex h-screen flex-col items-center justify-center gap-4 bg-[var(--surface-0)] px-6 text-center"
  >
    <p className="text-7xl font-semibold tracking-tight text-[var(--muted-foreground)]/50">404</p>
    <div className="space-y-1">
      <p className="text-lg font-semibold text-[var(--foreground)]">页面未找到</p>
      <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
        这个地址可能已经失效，或者链接输入有误。
      </p>
    </div>
    <Link
      to="/"
      className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition-all hover:opacity-90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
    >
      返回首页
    </Link>
  </motion.div>
);

const AnimatedRoutes = () => {
  const location = useLocation();

  return (
    <Suspense fallback={<LoadingPage />}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* 每个路由单独包一层错误边界：单个页面崩了不该把整个应用（含导航）
              一起替换成错误页，用户还能换个页面继续用。 */}
          <Route path="/" element={<ErrorBoundary key={`home-${location.pathname}`} title="首页出错了"><Home /></ErrorBoundary>} />
          <Route path="/chat" element={<ProtectedRoute><ErrorBoundary key={`chat-${location.pathname}`} title="对话页出错了"><Chat /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/agents" element={<ProtectedRoute><ErrorBoundary key={`agents-${location.pathname}`} title="智能体商店出错了"><AgentStore /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/agents/new" element={<ProtectedRoute><ErrorBoundary key={`agent-new-${location.pathname}`} title="智能体编辑器出错了"><AgentEditor /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/agents/:profileId/edit" element={<ProtectedRoute><ErrorBoundary key={`agent-edit-${location.pathname}`} title="智能体编辑器出错了"><AgentEditor /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/login" element={<ErrorBoundary key={`login-${location.pathname}`} title="登录页出错了"><Login /></ErrorBoundary>} />
          <Route path="/signup" element={<ErrorBoundary key={`signup-${location.pathname}`} title="注册页出错了"><Signup /></ErrorBoundary>} />
          <Route path="/admin" element={<ProtectedRoute requireAdmin><ErrorBoundary key={`admin-${location.pathname}`} title="管理后台出错了"><AdminDashboard /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/gallery" element={<ProtectedRoute><ErrorBoundary key={`gallery-${location.pathname}`} title="作品库出错了"><Gallery /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/wrapped" element={<ProtectedRoute><ErrorBoundary key="wrapped" title="年度报告出错了"><Wrapped /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/wrapped/:year" element={<ProtectedRoute><ErrorBoundary key={`wrapped-${location.pathname}`} title="年度报告出错了"><Wrapped /></ErrorBoundary></ProtectedRoute>} />
          <Route path="/feedback" element={<ProtectedRoute><ErrorBoundary key="feedback" title="反馈页出错了"><Feedback /></ErrorBoundary></ProtectedRoute>} />
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
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

export default App;
