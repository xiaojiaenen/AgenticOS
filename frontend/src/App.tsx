import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { GlobalAnnouncementLayer } from './components/announcement/GlobalAnnouncementLayer';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { ToastContainer } from './components/ui/Toast';

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
      className="h-8 w-8 rounded-full border-4 border-sky-500 border-t-transparent"
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
            <div className="flex h-screen flex-col items-center justify-center gap-4 bg-zinc-50 text-slate-600">
              <p className="text-6xl font-black text-slate-300">404</p>
              <p className="text-lg font-bold">页面未找到</p>
              <a href="/" className="text-sm font-medium text-sky-600 hover:text-sky-700">返回首页</a>
            </div>
          } />
        </Routes>
      </AnimatePresence>
    </Suspense>
  );
};

function App() {
  return (
    <Router>
      <GlobalAnnouncementLayer />
      <AnimatedRoutes />
      <ToastContainer />
    </Router>
  );
}

export default App;
