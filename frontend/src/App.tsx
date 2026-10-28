import { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalAnnouncementLayer } from './components/announcement/GlobalAnnouncementLayer';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { Toaster } from '@/components/shadcn/sonner';
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
const AdminDashboard = lazy(() =>
  import('./pages/AdminDashboard').then((module) => ({ default: module.AdminDashboard })),
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
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AnimatePresence>
    </Suspense>
  );
};

function AppContent() {
  return (
    <>
      <GlobalAnnouncementLayer />
      <ErrorBoundary>
        <AnimatedRoutes />
      </ErrorBoundary>
      <Toaster />
    </>
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
