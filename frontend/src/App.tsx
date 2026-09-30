import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalAnnouncementLayer } from './components/announcement/GlobalAnnouncementLayer';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { ToastContainer } from './components/ui/Toast';
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
const Login = lazy(() => import('./pages/Login').then((module) => ({ default: module.Login })));
const Signup = lazy(() => import('./pages/Signup').then((module) => ({ default: module.Signup })));
const AdminDashboard = lazy(() =>
  import('./pages/AdminDashboard').then((module) => ({ default: module.AdminDashboard })),
);

const LoadingPage = () => (
  <div className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-zinc-50">
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent"
    />
    <p className="text-sm font-medium text-slate-400">正在加载页面...</p>
  </div>
);

const AnimatedRoutes = () => {
  const location = useLocation();

  return (
    <Suspense fallback={<LoadingPage />}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Home />} />
          <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
          <Route path="/agents" element={<ProtectedRoute><AgentStore /></ProtectedRoute>} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
          <Route path="*" element={
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex h-screen flex-col items-center justify-center gap-4 bg-zinc-50 text-slate-600"
            >
              <p className="text-6xl font-semibold text-slate-400">404</p>
              <p className="text-lg font-semibold">页面未找到</p>
              <Link to="/" className="text-sm font-medium text-sky-600 hover:text-sky-700 underline underline-offset-4">返回首页</Link>
            </motion.div>
          } />
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
      <ToastContainer />
      {/* sonner Toaster（shadcn）— M1 起逐步替代 ToastContainer */}
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
